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
