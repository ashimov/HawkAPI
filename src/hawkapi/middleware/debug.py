"""Debug endpoints middleware — exposes /_debug/* for development."""

from __future__ import annotations

import inspect
import time
from collections import defaultdict
from typing import Any

import msgspec

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class DebugMiddleware(Middleware):
    """Expose ``/_debug/routes`` and ``/_debug/stats`` endpoints.

    ``/_debug/routes`` returns a JSON list of all registered routes.
    ``/_debug/stats`` returns per-path request count, average latency, and error count.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        prefix: str = "/_debug",
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self._prefix = prefix
        self._enabled = enabled
        self._stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_time": 0.0, "errors": 0}
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]

        if self._enabled and path == f"{self._prefix}/routes":
            await self._serve_routes(scope, receive, send)
            return

        if self._enabled and path == f"{self._prefix}/stats":
            await self._serve_stats(scope, receive, send)
            return

        # Track stats for all other requests
        start = time.monotonic()
        status_code = 500

        async def stats_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, stats_send)
        finally:
            duration = time.monotonic() - start
            entry = self._stats[path]
            entry["count"] += 1
            entry["total_time"] += duration
            if status_code >= 500:
                entry["errors"] += 1

    # ------------------------------------------------------------------
    # Debug endpoints
    # ------------------------------------------------------------------

    async def _serve_routes(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Return a JSON list describing every registered route."""
        inner: Any = self.app
        while hasattr(inner, "app"):
            inner = inner.app

        # The innermost app may be a bound method whose __self__ is the HawkAPI
        target: Any = inner
        if not hasattr(target, "routes") and inspect.ismethod(target):
            target = target.__self__

        routes: list[dict[str, Any]] = []
        if hasattr(target, "routes"):
            for route in target.routes:
                routes.append(
                    {
                        "path": route.path,
                        "methods": sorted(route.methods),
                        "name": route.name,
                        "deprecated": route.deprecated,
                    }
                )

        body = msgspec.json.encode(routes)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def _serve_stats(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Return a JSON object with per-path request statistics."""
        stats: dict[str, dict[str, Any]] = {}
        for p, data in self._stats.items():
            count: int = data["count"]
            stats[p] = {
                "count": count,
                "avg_latency_ms": round((data["total_time"] / count) * 1000, 2) if count > 0 else 0,
                "errors": data["errors"],
            }

        body = msgspec.json.encode(stats)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
