"""Prometheus metrics middleware for HawkAPI."""

from __future__ import annotations

import time
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class PrometheusMiddleware(Middleware):
    """Collect HTTP metrics and expose a /metrics endpoint.

    Tracks:
    - http_requests_total{method, path, status} counter
    - http_request_duration_seconds{method, path} histogram
    - http_requests_in_progress{method} gauge

    Usage::

        from hawkapi.middleware.prometheus import PrometheusMiddleware
        app.add_middleware(PrometheusMiddleware)

    Requires: ``pip install hawkapi[metrics]``
    """

    # Typed as Any because prometheus_client is an optional dependency; its
    # stubs are not available at type-check time.
    _registry: Any
    _requests_total: Any
    _request_duration: Any
    _in_progress: Any

    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics_path: str = "/metrics",
        registry: Any = None,
    ) -> None:
        super().__init__(app)
        from prometheus_client import (  # pyright: ignore[reportMissingImports]
            CollectorRegistry,  # pyright: ignore[reportUnknownVariableType]
            Counter,  # pyright: ignore[reportUnknownVariableType]
            Gauge,  # pyright: ignore[reportUnknownVariableType]
            Histogram,  # pyright: ignore[reportUnknownVariableType]
        )

        self._metrics_path = metrics_path
        self._registry = registry or CollectorRegistry()  # pyright: ignore[reportUnknownVariableType]

        self._requests_total = Counter(  # pyright: ignore[reportUnknownVariableType]
            "http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
            registry=self._registry,  # pyright: ignore[reportUnknownMemberType]
        )
        self._request_duration = Histogram(  # pyright: ignore[reportUnknownVariableType]
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "path"],
            registry=self._registry,  # pyright: ignore[reportUnknownMemberType]
        )
        self._in_progress = Gauge(  # pyright: ignore[reportUnknownVariableType]
            "http_requests_in_progress",
            "HTTP requests currently in progress",
            ["method"],
            registry=self._registry,  # pyright: ignore[reportUnknownMemberType]
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]

        # Serve /metrics endpoint
        if path == self._metrics_path:
            await self._serve_metrics(scope, receive, send)
            return

        method: str = scope["method"]

        self._in_progress.labels(method=method).inc()
        start = time.monotonic()
        status_code = 500

        async def metrics_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, metrics_send)
        finally:
            duration = time.monotonic() - start
            self._requests_total.labels(method=method, path=path, status=str(status_code)).inc()
            self._request_duration.labels(method=method, path=path).observe(duration)
            self._in_progress.labels(method=method).dec()

    async def _serve_metrics(self, scope: Scope, receive: Receive, send: Send) -> None:
        from prometheus_client import (  # pyright: ignore[reportMissingImports]
            generate_latest,  # pyright: ignore[reportUnknownVariableType]
        )

        body: bytes = generate_latest(self._registry)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain; version=0.0.4; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("latin-1")),  # pyright: ignore[reportUnknownArgumentType]
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
