"""Tests for the Bulkhead primitive and its local backend."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from hawkapi.middleware.bulkhead import (
    BulkheadFullError,
    LocalBulkheadBackend,
)


async def test_local_backend_acquire_release_returns_none_token() -> None:
    backend = LocalBulkheadBackend()
    token = await backend.acquire("x", limit=2, max_wait=0.0)
    assert token is None
    await backend.release("x", token)


async def test_local_backend_fail_fast_when_full() -> None:
    backend = LocalBulkheadBackend()
    await backend.acquire("x", limit=2, max_wait=0.0)
    await backend.acquire("x", limit=2, max_wait=0.0)
    with pytest.raises(BulkheadFullError) as excinfo:
        await backend.acquire("x", limit=2, max_wait=0.0)
    assert excinfo.value.name == "x"
    assert excinfo.value.limit == 2
    assert excinfo.value.waited == pytest.approx(0.0, abs=0.05)


async def test_local_backend_queue_then_release_unblocks_waiter() -> None:
    backend = LocalBulkheadBackend()
    await backend.acquire("x", limit=1, max_wait=0.0)

    async def release_after(delay: float) -> None:
        await asyncio.sleep(delay)
        await backend.release("x", None)

    release_task = asyncio.create_task(release_after(0.02))
    try:
        await backend.acquire("x", limit=1, max_wait=0.5)
    finally:
        await release_task


async def test_local_backend_queue_timeout_raises() -> None:
    backend = LocalBulkheadBackend()
    await backend.acquire("x", limit=1, max_wait=0.0)
    with pytest.raises(BulkheadFullError) as excinfo:
        await backend.acquire("x", limit=1, max_wait=0.05)
    assert excinfo.value.waited >= 0.05
    assert excinfo.value.waited < 0.5


async def test_local_backend_isolates_by_name() -> None:
    backend = LocalBulkheadBackend()
    await backend.acquire("x", limit=1, max_wait=0.0)
    token = await backend.acquire("y", limit=1, max_wait=0.0)
    assert token is None


async def test_local_backend_rejects_colliding_limits() -> None:
    backend = LocalBulkheadBackend()
    await backend.acquire("x", limit=5, max_wait=0.0)
    with pytest.raises(ValueError, match="limit"):
        await backend.acquire("x", limit=10, max_wait=0.0)


async def test_local_backend_concurrent_acquires_never_exceed_limit() -> None:
    backend = LocalBulkheadBackend()
    limit = 3
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal in_flight, max_in_flight
        await backend.acquire("x", limit=limit, max_wait=2.0)
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        async with lock:
            in_flight -= 1
        await backend.release("x", None)

    await asyncio.gather(*(worker() for _ in range(20)))
    assert max_in_flight == limit


from hawkapi.middleware.bulkhead import Bulkhead


async def test_bulkhead_context_manager_basic() -> None:
    bh = Bulkhead("x", limit=2)
    async with bh:
        async with bh:
            pass
    async with bh:
        pass


async def test_bulkhead_context_manager_fail_fast_when_full() -> None:
    bh = Bulkhead("x_ff", limit=1, max_wait=0.0)

    async def hold_forever(ready: asyncio.Event, done: asyncio.Event) -> None:
        async with bh:
            ready.set()
            await done.wait()

    ready = asyncio.Event()
    done = asyncio.Event()
    holder = asyncio.create_task(hold_forever(ready, done))
    try:
        await ready.wait()
        with pytest.raises(BulkheadFullError):
            async with bh:
                pytest.fail("should not enter")
    finally:
        done.set()
        await holder


async def test_bulkhead_context_manager_release_on_exception() -> None:
    bh = Bulkhead("x_exc", limit=1)
    with pytest.raises(RuntimeError, match="boom"):
        async with bh:
            raise RuntimeError("boom")
    async with bh:
        pass


async def test_bulkhead_context_manager_release_on_cancel() -> None:
    bh = Bulkhead("x_cancel", limit=1, max_wait=0.0)

    async def hold_then_cancel(started: asyncio.Event) -> None:
        async with bh:
            started.set()
            await asyncio.sleep(1.0)

    started = asyncio.Event()
    task = asyncio.create_task(hold_then_cancel(started))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with bh:
        pass


async def test_bulkhead_concurrent_tasks_share_one_instance() -> None:
    bh = Bulkhead("x_conc", limit=2, max_wait=1.0)
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal in_flight, max_in_flight
        async with bh:
            async with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            async with lock:
                in_flight -= 1

    await asyncio.gather(*(worker() for _ in range(10)))
    assert max_in_flight == 2


async def test_bulkhead_different_names_dont_share_capacity() -> None:
    bh1 = Bulkhead("a", limit=1, max_wait=0.0)
    bh2 = Bulkhead("b", limit=1, max_wait=0.0)
    async with bh1:
        async with bh2:
            pass


from hawkapi.exceptions import HTTPException
from hawkapi.middleware.bulkhead import bulkhead


async def test_bulkhead_decorator_passthrough_when_under_limit() -> None:
    @bulkhead("pay", limit=2)
    async def handler() -> str:
        return "ok"

    assert await handler() == "ok"


async def test_bulkhead_decorator_raises_http_exception_when_full() -> None:
    hold_event = asyncio.Event()
    started = asyncio.Event()

    @bulkhead("pay2", limit=1, max_wait=0.0)
    async def handler() -> str:
        started.set()
        await hold_event.wait()
        return "ok"

    holder = asyncio.create_task(handler())
    try:
        await started.wait()
        with pytest.raises(HTTPException) as excinfo:
            await handler()
        assert excinfo.value.status_code == 503
        assert excinfo.value.headers is not None
        assert excinfo.value.headers.get("Retry-After") == "1"
    finally:
        hold_event.set()
        await holder


async def test_bulkhead_decorator_configurable_status_and_retry_after() -> None:
    started = asyncio.Event()
    hold_event = asyncio.Event()

    @bulkhead("pay3", limit=1, max_wait=0.0, status_code=429, retry_after=2.5)
    async def handler() -> str:
        started.set()
        await hold_event.wait()
        return "ok"

    holder = asyncio.create_task(handler())
    try:
        await started.wait()
        with pytest.raises(HTTPException) as excinfo:
            await handler()
        assert excinfo.value.status_code == 429
        # retry_after=2.5 rounds up to "3" per RFC 9110 integer seconds.
        assert excinfo.value.headers is not None
        assert excinfo.value.headers.get("Retry-After") == "3"
    finally:
        hold_event.set()
        await holder


async def test_bulkhead_decorator_preserves_handler_args() -> None:
    @bulkhead("pay4", limit=2)
    async def handler(x: int, *, y: int = 0) -> int:
        return x + y

    assert await handler(1, y=2) == 3
