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
        super().__init__(f"bulkhead {name!r} full (limit={limit}, waited={waited:.3f}s)")
        self.name = name
        self.limit = limit
        self.waited = waited


class BulkheadBackend(Protocol):
    """Pluggable concurrency backend."""

    async def acquire(self, name: str, limit: int, max_wait: float) -> object | None: ...

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

    async def acquire(self, name: str, limit: int, max_wait: float) -> object | None:
        sem = await self._get_semaphore(name, limit)
        if max_wait <= 0.0:
            # Non-blocking acquire: ``asyncio.timeout(0)`` yields control once,
            # then fails if the semaphore is still blocked.
            try:
                async with asyncio.timeout(0):
                    await sem.acquire()
            except TimeoutError:
                raise BulkheadFullError(name, limit, waited=0.0) from None
            return None
        start = time.monotonic()
        try:
            async with asyncio.timeout(max_wait):
                await sem.acquire()
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
