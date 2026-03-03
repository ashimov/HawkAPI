"""Request metrics collection (in-memory fallback)."""

from __future__ import annotations

from collections import deque

# Keep last N durations to prevent unbounded memory growth
_MAX_DURATIONS = 10_000


class InMemoryMetrics:
    """Simple in-memory metrics collector."""

    __slots__ = ("request_count", "error_count", "_durations")

    def __init__(self) -> None:
        """Initialize empty metrics."""
        self.request_count: int = 0
        self.error_count: int = 0
        self._durations: deque[float] = deque(maxlen=_MAX_DURATIONS)

    def record_request(self, method: str, path: str, status: int, duration: float) -> None:
        """Record a completed request."""
        self.request_count += 1
        if status >= 500:
            self.error_count += 1
        self._durations.append(duration)

    @property
    def avg_duration_ms(self) -> float:
        """Average request duration in milliseconds."""
        if not self._durations:
            return 0.0
        return sum(self._durations) / len(self._durations) * 1000
