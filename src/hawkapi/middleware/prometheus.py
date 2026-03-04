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

    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics_path: str = "/metrics",
        registry: Any = None,
    ) -> None:
        super().__init__(app)
        from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

        self._metrics_path = metrics_path
        self._registry: CollectorRegistry = registry or CollectorRegistry()

        self._requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
            registry=self._registry,
        )
        self._request_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "path"],
            registry=self._registry,
        )
        self._in_progress = Gauge(
            "http_requests_in_progress",
            "HTTP requests currently in progress",
            ["method"],
            registry=self._registry,
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
        from prometheus_client import generate_latest

        body = generate_latest(self._registry)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain; version=0.0.4; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
