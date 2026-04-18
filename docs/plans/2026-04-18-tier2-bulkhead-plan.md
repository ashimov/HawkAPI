# Tier 2 — Bulkhead — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Hystrix-style bulkhead primitive: a named, size-limited async concurrency isolator usable as an `async with` context manager or a route decorator, with a pluggable local/Redis backend.

**Architecture:** A single `Bulkhead` class wraps a `BulkheadBackend` protocol. The default `LocalBulkheadBackend` uses `asyncio.Semaphore` per name. `RedisBulkheadBackend` uses a Redis hash per name with per-field lease IDs and a TTL-based reaper for crash safety. Per-acquire tokens flow through a ContextVar-backed stack so one shared `Bulkhead` instance is safe for concurrent tasks. A thin decorator converts `BulkheadFullError` into an `HTTPException(503)` with `Retry-After` for route handlers.

**Tech Stack:** Python 3.12+, asyncio, `contextvars`, `redis>=5.0` (optional), `prometheus-client>=0.20` (optional), `fakeredis[lua]>=2.0` (new dev dep), pytest + pytest-benchmark, MkDocs Material.

**Spec:** [docs/plans/2026-04-18-tier2-bulkhead-design.md](2026-04-18-tier2-bulkhead-design.md)

---

## File Structure

| File | Responsibility | New/Modified |
|---|---|---|
| `src/hawkapi/middleware/bulkhead.py` | Protocol, `BulkheadFullError`, `LocalBulkheadBackend`, `Bulkhead`, `bulkhead` decorator, ContextVar token stack | New |
| `src/hawkapi/middleware/bulkhead_redis.py` | `RedisBulkheadBackend` — hash per name + per-field lease IDs | New |
| `src/hawkapi/middleware/__init__.py` | Re-export `Bulkhead`, `bulkhead`, `BulkheadFullError` | Modified |
| `tests/unit/test_bulkhead.py` | Core + local backend + decorator + metrics | New |
| `tests/unit/test_bulkhead_redis.py` | fakeredis-backed Redis backend tests | New |
| `tests/perf/test_bulkhead_perf.py` | `acquire/release` throughput benchmark | New |
| `tests/perf/.benchmark_baseline.json` | Add bulkhead entry | Modified |
| `pyproject.toml` | Add `fakeredis[lua]>=2.0` to `dev` extra | Modified |
| `docs/guide/bulkhead.md` | User guide | New |
| `mkdocs.yml` | Nav entry | Modified |
| `CHANGELOG.md` | `[Unreleased]` `### Added` entries | Modified |

---

## Task 1: Scaffold `bulkhead.py` with `BulkheadFullError` + Protocol

**Files:**
- Create: `src/hawkapi/middleware/bulkhead.py`

- [ ] **Step 1: Write the minimal module**

Create `src/hawkapi/middleware/bulkhead.py`:

```python
"""Hystrix-style bulkhead — named, size-limited async concurrency isolator.

Complement to ``AdaptiveConcurrencyMiddleware`` (global auto-tuned cap) and
``RateLimit*`` middleware (time-windowed budget). A ``Bulkhead`` partitions
capacity across *named* resource pools so saturation of one pool does not
starve others.

Two public forms share one implementation:

* Context manager ``async with Bulkhead("stripe", limit=10): ...``
* Decorator ``@bulkhead("payments", limit=10)`` — rejects over-limit
  requests with HTTP 503 + ``Retry-After``.
"""

from __future__ import annotations

from typing import Protocol


class BulkheadFullError(Exception):
    """Raised when a Bulkhead has no free slot within the wait budget."""

    def __init__(self, name: str, limit: int, waited: float) -> None:
        super().__init__(
            f"bulkhead {name!r} full (limit={limit}, waited={waited:.3f}s)"
        )
        self.name = name
        self.limit = limit
        self.waited = waited


class BulkheadBackend(Protocol):
    """Pluggable concurrency backend.

    Implementations must be safe to share across tasks. ``acquire`` returns an
    opaque token the caller passes back to ``release``; backends that do not
    need per-acquire state (for example the local semaphore) return ``None``.
    """

    async def acquire(
        self, name: str, limit: int, max_wait: float
    ) -> object | None:
        """Acquire a slot. Raise ``BulkheadFullError`` on no capacity."""

    async def release(self, name: str, token: object | None) -> None:
        """Release the slot previously returned by ``acquire``."""


__all__ = ["BulkheadBackend", "BulkheadFullError"]
```

- [ ] **Step 2: Smoke-check imports**

Run: `uv run python -c "from hawkapi.middleware.bulkhead import BulkheadFullError, BulkheadBackend; print('ok')"`

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/hawkapi/middleware/bulkhead.py
git commit -m "feat(bulkhead): scaffold module with BulkheadFullError and backend Protocol"
```

---

## Task 2: Write failing tests for `LocalBulkheadBackend`

**Files:**
- Create: `tests/unit/test_bulkhead.py`

- [ ] **Step 1: Create the test file**

```python
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
```

- [ ] **Step 2: Run tests — confirm they fail with ImportError**

Run: `uv run pytest tests/unit/test_bulkhead.py -v`

Expected: every test errors with `ImportError: cannot import name 'LocalBulkheadBackend'`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_bulkhead.py
git commit -m "test(bulkhead): failing tests for LocalBulkheadBackend"
```

---

## Task 3: Implement `LocalBulkheadBackend`

**Files:**
- Modify: `src/hawkapi/middleware/bulkhead.py`

- [ ] **Step 1: Extend the module**

Replace the whole file with:

```python
"""Hystrix-style bulkhead — named, size-limited async concurrency isolator.

Complement to ``AdaptiveConcurrencyMiddleware`` (global auto-tuned cap) and
``RateLimit*`` middleware (time-windowed budget). A ``Bulkhead`` partitions
capacity across *named* resource pools so saturation of one pool does not
starve others.

Two public forms share one implementation:

* Context manager ``async with Bulkhead("stripe", limit=10): ...``
* Decorator ``@bulkhead("payments", limit=10)`` — rejects over-limit
  requests with HTTP 503 + ``Retry-After``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol


class BulkheadFullError(Exception):
    """Raised when a Bulkhead has no free slot within the wait budget."""

    def __init__(self, name: str, limit: int, waited: float) -> None:
        super().__init__(
            f"bulkhead {name!r} full (limit={limit}, waited={waited:.3f}s)"
        )
        self.name = name
        self.limit = limit
        self.waited = waited


class BulkheadBackend(Protocol):
    """Pluggable concurrency backend."""

    async def acquire(
        self, name: str, limit: int, max_wait: float
    ) -> object | None: ...

    async def release(self, name: str, token: object | None) -> None: ...


class LocalBulkheadBackend:
    """In-process backend — one ``asyncio.Semaphore`` per name.

    Safe for concurrent use across tasks. Collisions (same name, different
    ``limit``) raise ``ValueError`` at acquire time — the first ``limit`` wins.
    """

    def __init__(self) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._limits: dict[str, int] = {}
        # Guards the two dicts during first-time registration only. After a
        # name is registered, ``acquire`` takes the lock-free fast path.
        self._register_lock = asyncio.Lock()

    async def _get_semaphore(self, name: str, limit: int) -> asyncio.Semaphore:
        sem = self._semaphores.get(name)
        if sem is not None:
            if self._limits[name] != limit:
                raise ValueError(
                    f"bulkhead {name!r} already registered with "
                    f"limit={self._limits[name]}, got limit={limit}"
                )
            return sem
        async with self._register_lock:
            sem = self._semaphores.get(name)
            if sem is not None:
                if self._limits[name] != limit:
                    raise ValueError(
                        f"bulkhead {name!r} already registered with "
                        f"limit={self._limits[name]}, got limit={limit}"
                    )
                return sem
            sem = asyncio.Semaphore(limit)
            self._semaphores[name] = sem
            self._limits[name] = limit
            return sem

    async def acquire(
        self, name: str, limit: int, max_wait: float
    ) -> object | None:
        sem = await self._get_semaphore(name, limit)
        if max_wait <= 0.0:
            # Non-blocking acquire: ``asyncio.wait_for`` with timeout=0 yields
            # control once, then fails if still blocked.
            try:
                await asyncio.wait_for(sem.acquire(), timeout=0)
            except TimeoutError:
                raise BulkheadFullError(name, limit, waited=0.0) from None
            return None
        start = time.monotonic()
        try:
            await asyncio.wait_for(sem.acquire(), timeout=max_wait)
        except TimeoutError:
            waited = time.monotonic() - start
            raise BulkheadFullError(name, limit, waited=waited) from None
        return None

    async def release(self, name: str, token: object | None) -> None:
        sem = self._semaphores.get(name)
        if sem is None:
            raise RuntimeError(f"release of unregistered bulkhead {name!r}")
        sem.release()


__all__ = ["BulkheadBackend", "BulkheadFullError", "LocalBulkheadBackend"]
```

- [ ] **Step 2: Run tests — all should pass**

Run: `uv run pytest tests/unit/test_bulkhead.py -v`

Expected: 7 tests pass.

- [ ] **Step 3: Lint + format**

```bash
uv run ruff check src/hawkapi/middleware/bulkhead.py tests/unit/test_bulkhead.py
uv run ruff format --check src/hawkapi/middleware/bulkhead.py tests/unit/test_bulkhead.py
```

If drift: `uv run ruff format src/hawkapi/middleware/bulkhead.py tests/unit/test_bulkhead.py`.

- [ ] **Step 4: Commit**

```bash
git add src/hawkapi/middleware/bulkhead.py
git commit -m "feat(bulkhead): LocalBulkheadBackend — asyncio.Semaphore per name"
```

---

## Task 4: Write failing tests for `Bulkhead` context manager

**Files:**
- Modify: `tests/unit/test_bulkhead.py` (append)

- [ ] **Step 1: Append tests**

Add `import contextlib` at the top of the file (after `import asyncio`). Append after the existing tests:

```python
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
```

- [ ] **Step 2: Run tests — expect 6 new failures**

Run: `uv run pytest tests/unit/test_bulkhead.py -v -k "test_bulkhead_"`

Expected: 6 new tests fail with `ImportError: cannot import name 'Bulkhead'`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_bulkhead.py
git commit -m "test(bulkhead): failing tests for Bulkhead context manager"
```

---

## Task 5: Implement `Bulkhead` with ContextVar token stack

**Files:**
- Modify: `src/hawkapi/middleware/bulkhead.py`

The ContextVar stack stores `name → list[token]`. Per-task context isolation (asyncio tasks each get their own context) means concurrent tasks holding the same Bulkhead each have their own stack; nested same-name acquires in one task push/pop on a single stack.

- [ ] **Step 1: Add imports and helpers**

At the top of `src/hawkapi/middleware/bulkhead.py`, add after the existing imports:

```python
from contextvars import ContextVar
```

Before the `__all__` line at the bottom of the current file, insert:

```python
# Module-level default backend shared across all Bulkhead instances that do
# not explicitly pass their own.
_DEFAULT_LOCAL_BACKEND: LocalBulkheadBackend = LocalBulkheadBackend()

# Per-task stack of acquired tokens, keyed by bulkhead name. A list — not a
# single token — so nested same-name acquires in one task work correctly.
_TOKEN_STACKS: ContextVar[dict[str, list[object | None]] | None] = ContextVar(
    "hawkapi_bulkhead_tokens", default=None
)


def _push_token(name: str, token: object | None) -> None:
    stacks = _TOKEN_STACKS.get()
    if stacks is None:
        stacks = {}
        _TOKEN_STACKS.set(stacks)
    stacks.setdefault(name, []).append(token)


def _pop_token(name: str) -> object | None:
    stacks = _TOKEN_STACKS.get()
    if stacks is None or not stacks.get(name):
        raise RuntimeError(
            f"unpaired bulkhead release for {name!r} — this usually means "
            "release was called outside the task that acquired the slot"
        )
    return stacks[name].pop()


class Bulkhead:
    """Named, size-limited async concurrency isolator.

    Usage::

        bh = Bulkhead("stripe", limit=10, max_wait=0.5)
        async with bh:
            await stripe_client.charge(...)

    The same instance is safe to share across tasks; per-acquire state lives
    in a task-local ``ContextVar``.
    """

    __slots__ = ("_name", "_limit", "_max_wait", "_backend")

    def __init__(
        self,
        name: str,
        limit: int,
        max_wait: float = 0.0,
        *,
        backend: BulkheadBackend | None = None,
    ) -> None:
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        if max_wait < 0:
            raise ValueError(f"max_wait must be >= 0, got {max_wait}")
        self._name = name
        self._limit = limit
        self._max_wait = max_wait
        self._backend: BulkheadBackend = backend or _DEFAULT_LOCAL_BACKEND

    async def __aenter__(self) -> "Bulkhead":
        token = await self._backend.acquire(
            self._name, self._limit, self._max_wait
        )
        _push_token(self._name, token)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        token = _pop_token(self._name)
        await self._backend.release(self._name, token)

    @property
    def name(self) -> str:
        return self._name

    @property
    def limit(self) -> int:
        return self._limit
```

Update `__all__` at the bottom:

```python
__all__ = [
    "Bulkhead",
    "BulkheadBackend",
    "BulkheadFullError",
    "LocalBulkheadBackend",
]
```

- [ ] **Step 2: Run all bulkhead tests**

Run: `uv run pytest tests/unit/test_bulkhead.py -v`

Expected: 13 tests pass (7 backend + 6 Bulkhead).

- [ ] **Step 3: Lint + format**

```bash
uv run ruff check src/hawkapi/middleware/bulkhead.py
uv run ruff format --check src/hawkapi/middleware/bulkhead.py
```

- [ ] **Step 4: Commit**

```bash
git add src/hawkapi/middleware/bulkhead.py
git commit -m "feat(bulkhead): Bulkhead class with ContextVar token stack"
```

---

## Task 6: Write failing tests for `bulkhead` decorator

**Files:**
- Modify: `tests/unit/test_bulkhead.py` (append)

- [ ] **Step 1: Append decorator tests**

Append:

```python
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
```

- [ ] **Step 2: Run tests — expect 4 new failures**

Run: `uv run pytest tests/unit/test_bulkhead.py -v -k "decorator"`

Expected: 4 tests fail with `ImportError: cannot import name 'bulkhead'`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_bulkhead.py
git commit -m "test(bulkhead): failing tests for @bulkhead decorator"
```

---

## Task 7: Implement `bulkhead` decorator

**Files:**
- Modify: `src/hawkapi/middleware/bulkhead.py`

- [ ] **Step 1: Add imports and decorator**

Add these imports near the top (after the existing ones):

```python
import math
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from hawkapi.exceptions import HTTPException
```

After the `Bulkhead` class, add:

```python
F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def bulkhead(
    name: str,
    limit: int,
    max_wait: float = 0.0,
    *,
    backend: BulkheadBackend | None = None,
    status_code: int = 503,
    retry_after: float = 1.0,
) -> Callable[[F], F]:
    """Decorate an async handler so it acquires a bulkhead slot per call.

    On rejection, the wrapped handler raises ``HTTPException`` with the
    configured ``status_code`` (default 503) and a ``Retry-After`` header
    (default 1.0 s, rounded up to an integer per RFC 9110).
    """
    if retry_after < 0:
        raise ValueError(f"retry_after must be >= 0, got {retry_after}")
    retry_after_header = str(max(1, math.ceil(retry_after)))
    bh = Bulkhead(name, limit, max_wait=max_wait, backend=backend)

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                async with bh:
                    return await func(*args, **kwargs)
            except BulkheadFullError as exc:
                raise HTTPException(
                    status_code=status_code,
                    detail="bulkhead_full",
                    headers={"Retry-After": retry_after_header},
                ) from exc

        return wrapper  # type: ignore[return-value]

    return decorator
```

Update `__all__`:

```python
__all__ = [
    "Bulkhead",
    "BulkheadBackend",
    "BulkheadFullError",
    "LocalBulkheadBackend",
    "bulkhead",
]
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/test_bulkhead.py -v`

Expected: 17 tests pass.

- [ ] **Step 3: Lint + format**

```bash
uv run ruff check src/hawkapi/middleware/bulkhead.py tests/unit/test_bulkhead.py
uv run ruff format --check src/hawkapi/middleware/bulkhead.py tests/unit/test_bulkhead.py
```

- [ ] **Step 4: Commit**

```bash
git add src/hawkapi/middleware/bulkhead.py
git commit -m "feat(bulkhead): @bulkhead decorator with HTTPException mapping"
```

---

## Task 8: Write failing tests for opt-in metrics

**Files:**
- Modify: `tests/unit/test_bulkhead.py`

- [ ] **Step 1: Append metrics tests**

Append:

```python
prom = pytest.importorskip("prometheus_client")


async def test_metrics_disabled_by_default_no_prometheus_attr() -> None:
    import hawkapi.middleware.bulkhead as bh_mod

    bh = Bulkhead("metrics_off", limit=1)
    async with bh:
        pass
    # The lazy-loaded metric globals stay None until metrics=True triggers init.
    assert bh_mod._metric_in_flight is None or bh_mod._metrics_registered is False


async def test_metrics_enabled_emits_gauge_and_counter() -> None:
    bh = Bulkhead("metrics_on", limit=1, max_wait=0.0, metrics=True)
    from prometheus_client import REGISTRY

    async with bh:
        samples = {
            m.name: m
            for m in REGISTRY.collect()
            if m.name.startswith("hawkapi_bulkhead")
        }
        in_flight = next(
            s
            for s in samples["hawkapi_bulkhead_in_flight"].samples
            if s.labels.get("name") == "metrics_on"
        )
        assert in_flight.value == 1.0

    # Trigger a rejection and check the counter.
    started = asyncio.Event()
    hold_done = asyncio.Event()

    async def hold() -> None:
        async with bh:
            started.set()
            await hold_done.wait()

    holder = asyncio.create_task(hold())
    try:
        await started.wait()
        with pytest.raises(BulkheadFullError):
            async with bh:
                pass
    finally:
        hold_done.set()
        await holder

    samples = {
        m.name: m
        for m in REGISTRY.collect()
        if m.name.startswith("hawkapi_bulkhead_rejections_total")
    }
    rejections = [
        s
        for s in samples["hawkapi_bulkhead_rejections_total"].samples
        if s.labels.get("name") == "metrics_on"
        and s.labels.get("reason") == "fail_fast"
    ]
    assert rejections and rejections[0].value >= 1.0
```

- [ ] **Step 2: Run tests — expect failures**

Run: `uv run pytest tests/unit/test_bulkhead.py -v -k "metrics"`

Expected: both tests fail because `Bulkhead` does not accept `metrics=` yet and the metric globals are absent.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_bulkhead.py
git commit -m "test(bulkhead): failing tests for opt-in Prometheus metrics"
```

---

## Task 9: Implement opt-in metrics

**Files:**
- Modify: `src/hawkapi/middleware/bulkhead.py`

- [ ] **Step 1: Add lazy metrics plumbing**

After the `_pop_token` function and before the `Bulkhead` class, add:

```python
# Lazily initialised on first Bulkhead(metrics=True) construction.
_metrics_registered: bool = False
_metric_in_flight: Any = None
_metric_capacity: Any = None
_metric_rejections: Any = None
_metric_acquire_latency: Any = None


def _ensure_metrics() -> None:
    global _metrics_registered, _metric_in_flight, _metric_capacity
    global _metric_rejections, _metric_acquire_latency
    if _metrics_registered:
        return
    from prometheus_client import Counter, Gauge, Histogram  # noqa: PLC0415

    _metric_in_flight = Gauge(
        "hawkapi_bulkhead_in_flight",
        "Currently-occupied bulkhead slots.",
        ["name"],
    )
    _metric_capacity = Gauge(
        "hawkapi_bulkhead_capacity",
        "Configured bulkhead capacity.",
        ["name"],
    )
    _metric_rejections = Counter(
        "hawkapi_bulkhead_rejections_total",
        "Bulkhead acquire rejections.",
        ["name", "reason"],
    )
    _metric_acquire_latency = Histogram(
        "hawkapi_bulkhead_acquire_latency_seconds",
        "Time spent waiting for a bulkhead slot.",
        ["name"],
    )
    _metrics_registered = True
```

Replace the existing `Bulkhead` class with this extended version (keeps the same public behavior, adds `metrics=` kwarg and instrumentation):

```python
class Bulkhead:
    """Named, size-limited async concurrency isolator."""

    __slots__ = ("_name", "_limit", "_max_wait", "_backend", "_metrics")

    def __init__(
        self,
        name: str,
        limit: int,
        max_wait: float = 0.0,
        *,
        backend: BulkheadBackend | None = None,
        metrics: bool = False,
    ) -> None:
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        if max_wait < 0:
            raise ValueError(f"max_wait must be >= 0, got {max_wait}")
        self._name = name
        self._limit = limit
        self._max_wait = max_wait
        self._backend: BulkheadBackend = backend or _DEFAULT_LOCAL_BACKEND
        self._metrics = metrics
        if metrics:
            _ensure_metrics()
            _metric_capacity.labels(name=name).set(float(limit))

    async def __aenter__(self) -> "Bulkhead":
        start = time.monotonic()
        try:
            token = await self._backend.acquire(
                self._name, self._limit, self._max_wait
            )
        except BulkheadFullError as exc:
            if self._metrics:
                reason = "timeout" if self._max_wait > 0 else "fail_fast"
                _metric_rejections.labels(name=self._name, reason=reason).inc()
                _metric_acquire_latency.labels(name=self._name).observe(
                    exc.waited
                )
            raise
        if self._metrics:
            _metric_acquire_latency.labels(name=self._name).observe(
                time.monotonic() - start
            )
            _metric_in_flight.labels(name=self._name).inc()
        _push_token(self._name, token)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        token = _pop_token(self._name)
        await self._backend.release(self._name, token)
        if self._metrics:
            _metric_in_flight.labels(name=self._name).dec()

    @property
    def name(self) -> str:
        return self._name

    @property
    def limit(self) -> int:
        return self._limit
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/test_bulkhead.py -v`

Expected: all 19 tests pass (17 existing + 2 metrics).

- [ ] **Step 3: Lint + format**

```bash
uv run ruff check src/hawkapi/middleware/bulkhead.py tests/unit/test_bulkhead.py
uv run ruff format --check src/hawkapi/middleware/bulkhead.py tests/unit/test_bulkhead.py
```

- [ ] **Step 4: Commit**

```bash
git add src/hawkapi/middleware/bulkhead.py
git commit -m "feat(bulkhead): opt-in Prometheus metrics (lazy registration)"
```

---

## Task 10: Re-export from `hawkapi.middleware`

**Files:**
- Modify: `src/hawkapi/middleware/__init__.py`

- [ ] **Step 1: Add imports and exports**

After the last middleware import (currently `from hawkapi.middleware.trusted_host import TrustedHostMiddleware`), add:

```python
from hawkapi.middleware.bulkhead import (
    Bulkhead,
    BulkheadBackend,
    BulkheadFullError,
    bulkhead,
)
```

In the existing `__all__` list, insert `"Bulkhead"`, `"BulkheadBackend"`, `"BulkheadFullError"` in alphabetical order (after `"AdaptiveConcurrencyMiddleware"`), and `"bulkhead"` (the decorator, lowercase — most codebases group lowercase entries together; place it alphabetically among any other lowercase names or at the end if none).

- [ ] **Step 2: Smoke-test import**

Run: `uv run python -c "from hawkapi.middleware import Bulkhead, bulkhead, BulkheadFullError; print('ok')"`

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/hawkapi/middleware/__init__.py
git commit -m "feat(bulkhead): re-export Bulkhead, bulkhead, BulkheadFullError"
```

---

## Task 11: Add `fakeredis[lua]` dev dep + failing Redis tests

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/unit/test_bulkhead_redis.py`

- [ ] **Step 1: Add `fakeredis[lua]>=2.0` to the `dev` extra**

In `pyproject.toml`, in `[project.optional-dependencies]` → `dev = [ ... ]`, append:

```toml
    "fakeredis[lua]>=2.0",
```

(Inside the existing list; maintain the existing trailing-comma style.)

- [ ] **Step 2: Install the new dep**

Run: `uv sync --extra dev --extra redis`

Expected: fakeredis installs cleanly.

- [ ] **Step 3: Create the failing test file**

Create `tests/unit/test_bulkhead_redis.py`:

```python
"""Tests for the Redis-backed bulkhead backend.

Uses fakeredis so the suite runs without a live Redis instance.
"""

from __future__ import annotations

import asyncio

import pytest

redis_pkg = pytest.importorskip("redis")
fakeredis = pytest.importorskip("fakeredis")

from hawkapi.middleware.bulkhead import BulkheadFullError  # noqa: E402
from hawkapi.middleware.bulkhead_redis import RedisBulkheadBackend  # noqa: E402


@pytest.fixture
async def redis_client():
    """Yield a fresh fakeredis.aioredis.FakeRedis per test."""
    client = fakeredis.aioredis.FakeRedis()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


async def test_redis_backend_acquire_release_round_trip(redis_client) -> None:
    backend = RedisBulkheadBackend(redis_client)
    token = await backend.acquire("x", limit=2, max_wait=0.0)
    assert isinstance(token, str)
    await backend.release("x", token)


async def test_redis_backend_fail_fast_when_full(redis_client) -> None:
    backend = RedisBulkheadBackend(redis_client)
    await backend.acquire("x", limit=2, max_wait=0.0)
    await backend.acquire("x", limit=2, max_wait=0.0)
    with pytest.raises(BulkheadFullError):
        await backend.acquire("x", limit=2, max_wait=0.0)


async def test_redis_backend_queue_then_release(redis_client) -> None:
    backend = RedisBulkheadBackend(redis_client)
    t1 = await backend.acquire("x", limit=1, max_wait=0.0)

    async def release_after(delay: float) -> None:
        await asyncio.sleep(delay)
        await backend.release("x", t1)

    releaser = asyncio.create_task(release_after(0.05))
    try:
        t2 = await backend.acquire("x", limit=1, max_wait=0.5)
        await backend.release("x", t2)
    finally:
        await releaser


async def test_redis_backend_two_clients_share_capacity(redis_client) -> None:
    b1 = RedisBulkheadBackend(redis_client)
    b2 = RedisBulkheadBackend(redis_client)
    await b1.acquire("x", limit=1, max_wait=0.0)
    with pytest.raises(BulkheadFullError):
        await b2.acquire("x", limit=1, max_wait=0.0)


async def test_redis_backend_lease_ttl_reclaims_after_crash(redis_client) -> None:
    backend = RedisBulkheadBackend(redis_client, lease_ttl=0.05)
    await backend.acquire("x", limit=1, max_wait=0.0)
    await asyncio.sleep(0.1)
    reaped = await backend.reap_expired_leases("x")
    assert reaped == 1
    token = await backend.acquire("x", limit=1, max_wait=0.0)
    assert token is not None
    await backend.release("x", token)
```

- [ ] **Step 4: Run tests — expect import failure**

Run: `uv run pytest tests/unit/test_bulkhead_redis.py -v`

Expected: collection/import error because `RedisBulkheadBackend` does not exist.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/unit/test_bulkhead_redis.py
git commit -m "test(bulkhead): failing fakeredis tests for RedisBulkheadBackend"
```

---

## Task 12: Implement `RedisBulkheadBackend`

**Files:**
- Create: `src/hawkapi/middleware/bulkhead_redis.py`

Uses a Redis hash per bulkhead name. Each held slot is one field in the hash (field name = lease ID, value = acquisition timestamp). `HLEN` reports occupancy. `HDEL` releases. The reaper deletes fields older than `lease_ttl`.

- [ ] **Step 1: Create the file**

```python
"""Redis-backed bulkhead backend — distributed capacity control.

Implementation: one Redis hash per bulkhead name. Each acquired slot is one
field in the hash; field name is a random lease ID, field value is the
acquisition timestamp (seconds, float). ``HLEN`` gives the current occupancy.
``HDEL`` releases. A reaper deletes fields whose timestamp is older than
``lease_ttl``.

This is a "sloppy distributed semaphore": if a worker crashes mid-hold, its
lease survives until the reaper runs, allowing a bounded over-capacity window
up to ``lease_ttl``. Redlock-level correctness is explicitly not a goal.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING

from hawkapi.middleware.bulkhead import BulkheadFullError

if TYPE_CHECKING:
    import redis.asyncio as aioredis


class RedisBulkheadBackend:
    """Distributed bulkhead backend using a Redis hash + lease fields."""

    def __init__(
        self,
        client: "aioredis.Redis",
        *,
        key_prefix: str = "hawkapi:bulkhead",
        lease_ttl: float = 30.0,
        poll_interval: float = 0.01,
    ) -> None:
        if lease_ttl <= 0:
            raise ValueError("lease_ttl must be > 0")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")
        self._client = client
        self._key_prefix = key_prefix
        self._lease_ttl = lease_ttl
        self._poll_interval = poll_interval

    def _key(self, name: str) -> str:
        return f"{self._key_prefix}:{name}"

    async def _try_acquire_once(self, name: str, limit: int) -> str | None:
        """Single acquire attempt. Return lease_id on success, None on full."""
        lease_id = uuid.uuid4().hex
        key = self._key(name)
        now_s = time.time()
        pipe = self._client.pipeline()
        pipe.hset(key, lease_id, f"{now_s:.6f}")
        pipe.hlen(key)
        # Keep the hash-wide TTL well above lease_ttl so an idle key eventually
        # expires but the reaper is the primary cleanup mechanism.
        pipe.pexpire(key, int(self._lease_ttl * 1000 * 10))
        results = await pipe.execute()
        occupancy = int(results[1])
        if occupancy <= limit:
            return lease_id
        # Too many holders — roll back our field.
        await self._client.hdel(key, lease_id)
        return None

    async def acquire(
        self, name: str, limit: int, max_wait: float
    ) -> object | None:
        start = time.monotonic()
        lease_id = await self._try_acquire_once(name, limit)
        if lease_id is not None:
            return lease_id
        if max_wait <= 0.0:
            raise BulkheadFullError(name, limit, waited=0.0)
        deadline = start + max_wait
        while time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval)
            lease_id = await self._try_acquire_once(name, limit)
            if lease_id is not None:
                return lease_id
        raise BulkheadFullError(
            name, limit, waited=time.monotonic() - start
        )

    async def release(self, name: str, token: object | None) -> None:
        if not isinstance(token, str):
            raise TypeError(
                "RedisBulkheadBackend.release expected lease_id str, "
                f"got {type(token).__name__}"
            )
        await self._client.hdel(self._key(name), token)

    async def reap_expired_leases(self, name: str) -> int:
        """Delete lease fields older than ``lease_ttl``. Return count reaped."""
        key = self._key(name)
        cutoff = time.time() - self._lease_ttl
        fields: dict[bytes, bytes] = await self._client.hgetall(key)
        stale: list[bytes] = []
        for lease_id, ts_bytes in fields.items():
            try:
                ts = float(ts_bytes)
            except (TypeError, ValueError):
                stale.append(lease_id)
                continue
            if ts < cutoff:
                stale.append(lease_id)
        if not stale:
            return 0
        await self._client.hdel(key, *stale)
        return len(stale)


__all__ = ["RedisBulkheadBackend"]
```

- [ ] **Step 2: Run Redis tests**

Run: `uv run pytest tests/unit/test_bulkhead_redis.py -v`

Expected: 5 tests pass.

- [ ] **Step 3: Lint + format**

```bash
uv run ruff check src/hawkapi/middleware/bulkhead_redis.py tests/unit/test_bulkhead_redis.py
uv run ruff format --check src/hawkapi/middleware/bulkhead_redis.py tests/unit/test_bulkhead_redis.py
```

- [ ] **Step 4: Commit**

```bash
git add src/hawkapi/middleware/bulkhead_redis.py
git commit -m "feat(bulkhead): RedisBulkheadBackend with lease-TTL reaper"
```

---

## Task 13: Performance benchmark for local backend

**Files:**
- Create: `tests/perf/test_bulkhead_perf.py`
- Modify: `tests/perf/.benchmark_baseline.json`

- [ ] **Step 1: Create `tests/perf/test_bulkhead_perf.py`**

```python
"""Bulkhead performance benchmark — local backend acquire/release overhead."""

from __future__ import annotations

import asyncio

import pytest

from hawkapi.middleware.bulkhead import Bulkhead


@pytest.mark.perf
@pytest.mark.benchmark(group="bulkhead")
def test_bulkhead_acquire_release_local(benchmark) -> None:
    bh = Bulkhead("perf", limit=100)

    async def one_round_trip() -> None:
        async with bh:
            pass

    def run() -> None:
        asyncio.run(one_round_trip())

    benchmark(run)
```

- [ ] **Step 2: Generate a baseline run**

```bash
uv run pytest tests/perf/test_bulkhead_perf.py -m perf --benchmark-only \
    --benchmark-json=/tmp/bulkhead-baseline.json -q
```

Expected: one benchmark runs; mean is on the order of single-digit microseconds per iteration.

- [ ] **Step 3: Merge the entry into the committed baseline**

Open `/tmp/bulkhead-baseline.json` — it contains a JSON object with a top-level `benchmarks` list of one entry (structure: `{"name", "fullname", "params", "stats": {"min", "max", "mean", "stddev", "rounds", ...}, ...}`).

Open `tests/perf/.benchmark_baseline.json` — same structure, with existing entries. Append the new entry to its `benchmarks` list. Preserve every existing entry byte-for-byte. Preserve top-level keys (`datetime`, `version`, `machine_info`, etc.) as they were — do not replace them with fields from `/tmp/...`.

Sanity check:

```bash
grep test_bulkhead_acquire_release_local tests/perf/.benchmark_baseline.json
```

Expected: one match.

- [ ] **Step 4: Verify the regression gate is happy with itself**

```bash
uv run pytest tests/perf/test_bulkhead_perf.py -m perf --benchmark-only \
    --benchmark-compare=tests/perf/.benchmark_baseline.json \
    --benchmark-compare-fail=mean:5% -q
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add tests/perf/test_bulkhead_perf.py tests/perf/.benchmark_baseline.json
git commit -m "perf(bulkhead): add acquire/release benchmark + baseline"
```

---

## Task 14: User guide

**Files:**
- Create: `docs/guide/bulkhead.md`

- [ ] **Step 1: Write the guide**

Create `docs/guide/bulkhead.md`:

```markdown
# Bulkhead

A **bulkhead** is a named, size-limited concurrency isolator. It partitions
capacity across resource pools so one saturated downstream cannot starve
others.

## When to use which pattern

HawkAPI ships three related concurrency-control tools:

| Pattern | What it caps | When to reach for it |
|---|---|---|
| `RateLimitMiddleware` | Requests per time window | Per-client quotas; DDoS protection |
| `AdaptiveConcurrencyMiddleware` | Total in-flight requests (auto-tuned) | Whole-service overload protection |
| `Bulkhead` | Named pool of concurrent slots | Protect a specific downstream or endpoint |

If you need all three, compose them — they do different things.

## Context-manager form

Protect a specific downstream:

```python
from hawkapi.middleware import Bulkhead, BulkheadFullError

stripe_bulkhead = Bulkhead("stripe", limit=10, max_wait=0.5)

async def charge(card: str, amount: int) -> str:
    try:
        async with stripe_bulkhead:
            return await stripe_client.charge(card, amount)
    except BulkheadFullError:
        return await queue_for_async_charge(card, amount)
```

- `limit=10` — at most 10 concurrent calls to Stripe.
- `max_wait=0.5` — wait up to 500 ms for a slot; raise on timeout.
- `max_wait=0.0` (default) — fail fast.

## Decorator form

Cap an endpoint's concurrency:

```python
from hawkapi.middleware import bulkhead

@bulkhead("payments", limit=10, status_code=503, retry_after=1.0)
async def pay(request: Request) -> Response:
    ...
```

On rejection the handler raises `HTTPException(503)` with a `Retry-After`
header. Override `status_code=429` if your clients already implement
rate-limit backoff.

## Distributed bulkheads

For multi-process capacity control, swap in the Redis backend:

```python
import redis.asyncio as aioredis
from hawkapi.middleware import Bulkhead
from hawkapi.middleware.bulkhead_redis import RedisBulkheadBackend

redis_client = aioredis.from_url("redis://localhost")
redis_backend = RedisBulkheadBackend(redis_client, lease_ttl=30.0)

stripe_bulkhead = Bulkhead(
    "stripe", limit=10, max_wait=0.5, backend=redis_backend
)
```

**Tradeoffs**:

- Each `acquire` and `release` is a Redis round-trip (~0.3–1 ms typical).
- If a worker crashes mid-hold, its lease expires after `lease_ttl` (default
  30 s); until then the slot counts as held — a bounded over-capacity window.
- Call `RedisBulkheadBackend.reap_expired_leases(name)` periodically (for
  example from a lifespan background task) to actively reclaim stale slots.

## Metrics

Enable Prometheus metrics per bulkhead:

```python
stripe_bulkhead = Bulkhead("stripe", limit=10, metrics=True)
```

Exposed series:

- `hawkapi_bulkhead_in_flight{name}` — gauge of currently-held slots.
- `hawkapi_bulkhead_capacity{name}` — gauge = configured `limit`.
- `hawkapi_bulkhead_rejections_total{name, reason}` — counter;
  `reason ∈ {"fail_fast", "timeout"}`.
- `hawkapi_bulkhead_acquire_latency_seconds{name}` — histogram.

Metrics are off by default — the hot path does not import `prometheus_client`
unless at least one `Bulkhead(metrics=True)` is constructed.

## Limitations

- Same name with different `limit` raises `ValueError` — pick one.
- Fairness is not guaranteed — waiters are not served strictly FIFO.
- Nested same-name acquires in the same task work, but can deadlock if
  `limit` is too small; avoid them.
- The Redis backend does not provide Redlock-strength guarantees — if that
  matters, wrap a strict-mode lock around the call yourself.
```

- [ ] **Step 2: mkdocs smoke**

Run: `uv run mkdocs build --strict 2>&1 | tail -10`

Expected: build succeeds; INFO about `guide/bulkhead.md` missing from nav is acceptable at this step (fixed in Task 15).

- [ ] **Step 3: Commit**

```bash
git add docs/guide/bulkhead.md
git commit -m "docs(guide): add Bulkhead user guide"
```

---

## Task 15: Add `mkdocs.yml` nav entry

**Files:**
- Modify: `mkdocs.yml`

- [ ] **Step 1: Insert nav entry after Performance**

Find:

```yaml
      - Performance: guide/performance.md
      - Free-threaded Python (PEP 703): guide/free-threaded.md
```

Replace with:

```yaml
      - Performance: guide/performance.md
      - Bulkhead: guide/bulkhead.md
      - Free-threaded Python (PEP 703): guide/free-threaded.md
```

- [ ] **Step 2: Verify strict build**

Run: `uv run mkdocs build --strict 2>&1 | tail -10`

Expected: no WARNING or ERROR for `guide/bulkhead.md`.

- [ ] **Step 3: Commit**

```bash
git add mkdocs.yml
git commit -m "docs(nav): link Bulkhead guide under Guide section"
```

---

## Task 16: CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Append bulkhead bullets**

In `CHANGELOG.md` find the `[Unreleased]` → `### Added` list (created during Tier 1 polish). Append these four bullets at the end of the list, before the next `### Added` or `## [0.1.2]` heading:

```markdown
- Bulkhead primitive (`hawkapi.middleware.Bulkhead`) — Hystrix-style named async concurrency isolator with context-manager and `@bulkhead(...)` decorator forms
- `LocalBulkheadBackend` (default, `asyncio.Semaphore` per name) and `RedisBulkheadBackend` (distributed, hash + lease-TTL) implementations
- Opt-in Prometheus metrics for bulkheads (`hawkapi_bulkhead_in_flight`, `_capacity`, `_rejections_total`, `_acquire_latency_seconds`)
- User guide: `docs/guide/bulkhead.md`
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add Bulkhead entries under [Unreleased]"
```

---

## Task 17: Final verification sweep

- [ ] **Step 1: Full unit test suite**

Run: `uv run pytest tests/unit -q`

Expected: all tests pass (prior total + 19 new `test_bulkhead.py` + 5 new `test_bulkhead_redis.py` = 24 new tests).

- [ ] **Step 2: Ruff lint + format**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Both exit 0. If drift reported, run `uv run ruff format` on the specific bulkhead files only:

```bash
uv run ruff format src/hawkapi/middleware/bulkhead.py src/hawkapi/middleware/bulkhead_redis.py src/hawkapi/middleware/__init__.py tests/unit/test_bulkhead.py tests/unit/test_bulkhead_redis.py tests/perf/test_bulkhead_perf.py
git add -u
git commit -m "style: ruff format"
```

Do not format unrelated files.

- [ ] **Step 3: Pyright**

Run: `uv run pyright src/`

Expected: no new errors originating in `bulkhead.py` or `bulkhead_redis.py`. Pre-existing errors in `structured_logging.py` are not in scope.

- [ ] **Step 4: Perf gate**

```bash
uv run pytest tests/perf/ -m perf --benchmark-only \
    --benchmark-compare=tests/perf/.benchmark_baseline.json \
    --benchmark-compare-fail=mean:5% -q
```

Expected: exit 0.

- [ ] **Step 5: mkdocs strict build**

Run: `uv run mkdocs build --strict 2>&1 | tail -5`

Expected: clean build.

- [ ] **Step 6: Structural checks**

```bash
grep -n "class Bulkhead" src/hawkapi/middleware/bulkhead.py
grep -n "class RedisBulkheadBackend" src/hawkapi/middleware/bulkhead_redis.py
grep -n "Bulkhead\|bulkhead" src/hawkapi/middleware/__init__.py
grep -n "Bulkhead:" mkdocs.yml
test -f docs/guide/bulkhead.md && echo "guide exists"
```

All five must produce expected output.

If Step 2 produced a style commit, that is the only commit from this task. Otherwise no commit.

---

## Verification summary

After all 17 tasks:

- `src/hawkapi/middleware/bulkhead.py` provides `Bulkhead`, `bulkhead`, `BulkheadFullError`, `BulkheadBackend`, `LocalBulkheadBackend`.
- `src/hawkapi/middleware/bulkhead_redis.py` provides `RedisBulkheadBackend` with `reap_expired_leases`.
- `Bulkhead` is safe for concurrent use across tasks via ContextVar token stack.
- Metrics lazy-load `prometheus_client` only when `metrics=True` is used at least once.
- 24 new unit tests cover core, decorator, metrics, and Redis backend; local backend perf benchmark in CI under the 5 % regression gate.
- User guide + nav entry + CHANGELOG entry.
- Full lint/format/type/perf/docs gates green.
