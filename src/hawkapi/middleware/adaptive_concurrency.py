"""Adaptive concurrency control middleware (Netflix gradient2 algorithm).

Auto-tunes the maximum number of concurrent in-flight requests based on the
observed RTT relative to a target. The limit grows when latency stays near the
ideal floor (``min_rtt``) and shrinks when latency degrades, preventing
overload without manual tuning.

Algorithm (simplified gradient2):

    gradient   = clamp(min_rtt / avg_rtt, 0.5, 1.0)
    new_limit  = current_limit * gradient + queue_size_buffer
    limit      = limit * smoothing + new_limit * (1 - smoothing)
    limit      = clamp(limit, min_limit, max_limit)

When ``in_flight >= limit`` the request is rejected with a 503 response and a
``Retry-After`` header. State mutations are guarded by an ``asyncio.Lock`` —
the lock is only held around tiny synchronous critical sections, never around
``await self.app(...)``.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.serialization.encoder import encode_response


class _PathState:
    """Per-path mutable state for the adaptive concurrency limiter."""

    __slots__ = ("limit", "in_flight", "min_rtt", "samples", "last_min_rtt_reset")

    def __init__(self, initial_limit: float) -> None:
        self.limit: float = float(initial_limit)
        self.in_flight: int = 0
        # Use +inf so the first observation always becomes min_rtt
        self.min_rtt: float = math.inf
        # Recent RTT samples (sliding window). Append + maxlen for FIFO.
        self.samples: deque[float] = deque(maxlen=100)
        self.last_min_rtt_reset: float = time.monotonic()


class AdaptiveConcurrencyMiddleware(Middleware):
    """Adaptive concurrency limiter using a simplified Netflix gradient2.

    Per-path state tracks the current concurrent request limit and adjusts it
    based on the ratio of the minimum observed RTT to the recent average RTT.
    When the recent average drifts above the floor, the gradient shrinks and
    the limit contracts; when latency stays near the floor, the limit grows.

    Args:
        app: Inner ASGI application.
        initial_limit: Starting concurrent request limit.
        min_limit: Floor for the dynamic limit.
        max_limit: Ceiling for the dynamic limit.
        target_p99_ms: Target p99 RTT in milliseconds; used as a soft anchor
            when no RTT samples have been observed yet (``min_rtt = target``).
        smoothing: EWMA smoothing factor in ``[0, 1)`` — higher = more inertia.
        min_rtt_reset_interval: Seconds between forced ``min_rtt`` resets so
            the floor tracks long-term changes (e.g. autoscaling, GC pauses).
        queue_size_buffer: Additive constant in the new-limit formula
            (``new_limit = limit * gradient + queue_size_buffer``). The
            default ``sqrt(initial_limit)`` mirrors Netflix's recommendation.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        initial_limit: int = 50,
        min_limit: int = 10,
        max_limit: int = 1000,
        target_p99_ms: float = 100.0,
        smoothing: float = 0.9,
        min_rtt_reset_interval: float = 30.0,
        queue_size_buffer: float | None = None,
    ) -> None:
        super().__init__(app)
        if initial_limit < 1:
            msg = "initial_limit must be >= 1"
            raise ValueError(msg)
        if min_limit < 1:
            msg = "min_limit must be >= 1"
            raise ValueError(msg)
        if max_limit < min_limit:
            msg = "max_limit must be >= min_limit"
            raise ValueError(msg)
        if not 0.0 <= smoothing < 1.0:
            msg = "smoothing must be in [0, 1)"
            raise ValueError(msg)
        if target_p99_ms <= 0.0:
            msg = "target_p99_ms must be > 0"
            raise ValueError(msg)

        self.initial_limit = float(initial_limit)
        self.min_limit = float(min_limit)
        self.max_limit = float(max_limit)
        self.target_rtt = target_p99_ms / 1000.0  # seconds
        self.smoothing = smoothing
        self.min_rtt_reset_interval = min_rtt_reset_interval
        self.queue_size_buffer = (
            queue_size_buffer if queue_size_buffer is not None else math.sqrt(initial_limit)
        )

        self._states: dict[str, _PathState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # ASGI entry point
    # ------------------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "/")

        # ---- Admission decision (state mutation only) ----
        admitted = False
        retry_after: float = 0.0
        async with self._lock:
            state = self._states.get(path)
            if state is None:
                state = _PathState(self.initial_limit)
                self._states[path] = state

            # Periodic min_rtt reset so the floor follows long-term shifts
            now = time.monotonic()
            if now - state.last_min_rtt_reset >= self.min_rtt_reset_interval:
                state.min_rtt = math.inf
                state.last_min_rtt_reset = now

            if state.in_flight < state.limit:
                state.in_flight += 1
                admitted = True
            else:
                # Suggest a Retry-After proportional to current target latency
                retry_after = max(self.target_rtt, 1.0)

        if not admitted:
            await _send_503(send, retry_after, path)
            return

        # ---- Forward request OUTSIDE the lock and measure RTT ----
        started = time.monotonic()
        try:
            await self.app(scope, receive, send)
        finally:
            rtt = time.monotonic() - started
            async with self._lock:
                state.in_flight -= 1
                self._record_sample(state, rtt)

    # ------------------------------------------------------------------
    # Internal helpers (must only run under self._lock)
    # ------------------------------------------------------------------

    def _record_sample(self, state: _PathState, rtt: float) -> None:
        # Treat absurdly small RTTs (clock jitter) as a tiny positive value
        observed = max(rtt, 1e-6)
        state.samples.append(observed)
        # Update the minimum RTT floor
        if observed < state.min_rtt:
            state.min_rtt = observed

        # Compute average RTT over the recent window. Avoid division by zero.
        avg_rtt = sum(state.samples) / len(state.samples)
        if avg_rtt <= 0.0:
            return

        # Use the target_rtt as a soft anchor before any min observation
        floor = state.min_rtt if math.isfinite(state.min_rtt) else self.target_rtt

        # Gradient bounded to [0.5, 1.0]: caps how aggressively we shrink/grow
        gradient = max(0.5, min(1.0, floor / avg_rtt))

        new_limit = state.limit * gradient + self.queue_size_buffer
        # EWMA smoothing
        smoothed = state.limit * self.smoothing + new_limit * (1.0 - self.smoothing)
        # Clamp
        state.limit = max(self.min_limit, min(self.max_limit, smoothed))


# ----------------------------------------------------------------------
# 503 response helper
# ----------------------------------------------------------------------


async def _send_503(send: Send, retry_after: float, path: str) -> None:
    """Send a 503 problem+json response with a Retry-After header."""
    body = encode_response(
        {
            "type": "https://hawkapi.ashimov.com/errors/concurrency-limit",
            "title": "Service Unavailable",
            "status": 503,
            "detail": f"Concurrency limit reached for {path}",
        }
    )
    retry_seconds = max(1, int(math.ceil(retry_after)))
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/problem+json"),
        (b"content-length", str(len(body)).encode("latin-1")),
        (b"retry-after", str(retry_seconds).encode("latin-1")),
    ]
    start_message: dict[str, Any] = {
        "type": "http.response.start",
        "status": 503,
        "headers": headers,
    }
    await send(start_message)
    await send({"type": "http.response.body", "body": body})
