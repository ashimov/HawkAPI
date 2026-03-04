"""Circuit breaker middleware — three-state pattern (CLOSED / OPEN / HALF_OPEN).

Tracks failures per path.  When *failure_threshold* consecutive failures occur
the circuit opens and subsequent requests are rejected with 503 immediately
(without calling the inner application).  After *recovery_timeout* seconds the
circuit transitions to HALF_OPEN and allows a single probe request through.
If the probe succeeds the circuit closes; if it fails the circuit re-opens.
"""

from __future__ import annotations

import time
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.serialization.encoder import encode_response


class _CircuitState:
    """Per-path mutable state for the circuit breaker."""

    __slots__ = ("state", "failure_count", "opened_at", "half_open_calls")

    def __init__(self) -> None:
        self.state: str = "CLOSED"
        self.failure_count: int = 0
        self.opened_at: float = 0.0
        self.half_open_calls: int = 0


class CircuitBreakerMiddleware(Middleware):
    """Three-state circuit breaker middleware."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        super().__init__(app)
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._circuits: dict[str, _CircuitState] = {}

    # ------------------------------------------------------------------
    # ASGI entry point
    # ------------------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "/")
        circuit = self._circuits.get(path)
        if circuit is None:
            circuit = _CircuitState()
            self._circuits[path] = circuit

        # --- OPEN state ---
        if circuit.state == "OPEN":
            elapsed = time.monotonic() - circuit.opened_at
            if elapsed >= self.recovery_timeout:
                # Transition to HALF_OPEN — allow a probe request
                circuit.state = "HALF_OPEN"
                circuit.half_open_calls = 0
            else:
                await self._send_503(scope, receive, send, path)
                return

        # --- HALF_OPEN state: limit concurrent probes ---
        if circuit.state == "HALF_OPEN":
            if circuit.half_open_calls >= self.half_open_max_calls:
                await self._send_503(scope, receive, send, path)
                return
            circuit.half_open_calls += 1

        # --- Forward to inner app, capturing the status code ---
        status_code: int | None = None

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            self._record_failure(circuit)
            raise

        # --- Evaluate result ---
        if status_code is not None and status_code >= 500:
            self._record_failure(circuit)
        elif status_code is not None:
            self._record_success(circuit)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_failure(self, circuit: _CircuitState) -> None:
        if circuit.state == "HALF_OPEN":
            # Probe failed — re-open
            circuit.state = "OPEN"
            circuit.opened_at = time.monotonic()
            circuit.half_open_calls = 0
            return

        circuit.failure_count += 1
        if circuit.failure_count >= self.failure_threshold:
            circuit.state = "OPEN"
            circuit.opened_at = time.monotonic()

    def _record_success(self, circuit: _CircuitState) -> None:
        circuit.state = "CLOSED"
        circuit.failure_count = 0
        circuit.half_open_calls = 0

    async def _send_503(self, scope: Scope, receive: Receive, send: Send, path: str) -> None:
        body = encode_response(
            {
                "type": "https://hawkapi.ashimov.com/errors/circuit-open",
                "title": "Service Unavailable",
                "status": 503,
                "detail": f"Circuit breaker is open for {path}",
            }
        )
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
