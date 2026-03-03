"""Rate limiting middleware using token bucket algorithm."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class RateLimitMiddleware(Middleware):
    """In-memory per-client rate limiter using token bucket algorithm.

    Usage:
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_second=10.0,
            burst=20,
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests_per_second: float = 10.0,
        burst: int = 0,
        key_func: Callable[[Scope], str] | None = None,
        cleanup_interval: int = 60,
    ) -> None:
        super().__init__(app)
        self.rate = requests_per_second
        self.burst = burst if burst > 0 else int(requests_per_second)
        self.key_func = key_func or _default_key_func
        self.cleanup_interval = cleanup_interval
        # State: {key: [tokens, last_refill_time]}
        self._buckets: dict[str, list[float]] = {}
        self._last_cleanup = time.monotonic()
        self._lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        key = self.key_func(scope)

        async with self._lock:
            now = time.monotonic()

            # Periodic cleanup of stale entries
            if now - self._last_cleanup > self.cleanup_interval:
                self._cleanup(now)

            # Token bucket logic
            if key not in self._buckets:
                self._buckets[key] = [float(self.burst), now]

            bucket = self._buckets[key]
            elapsed = now - bucket[1]
            bucket[1] = now
            # Refill tokens
            bucket[0] = min(float(self.burst), bucket[0] + elapsed * self.rate)

            allowed = bucket[0] >= 1.0
            retry_after = 0.0
            if allowed:
                bucket[0] -= 1.0
            else:
                retry_after = (1.0 - bucket[0]) / self.rate

        if allowed:
            await self.app(scope, receive, send)
        else:
            await _send_429(send, retry_after)

    def _cleanup(self, now: float) -> None:
        """Remove stale entries that haven't been seen recently."""
        stale_threshold = now - self.cleanup_interval
        stale_keys = [k for k, v in self._buckets.items() if v[1] < stale_threshold]
        for k in stale_keys:
            del self._buckets[k]
        self._last_cleanup = now


async def _send_429(send: Send, retry_after: float) -> None:
    """Send a 429 Too Many Requests response."""
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", str(int(retry_after) + 1).encode("latin-1")),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b'{"detail":"Too Many Requests"}',
        }
    )


def _default_key_func(scope: Scope) -> str:
    """Default key: client IP address."""
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"
