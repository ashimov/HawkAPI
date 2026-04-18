"""Tests for the Bulkhead primitive and its local backend."""

from __future__ import annotations

import asyncio

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
    assert excinfo.value.waited == pytest.approx(0.0, abs=0.005)


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
