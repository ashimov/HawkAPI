"""Observability middleware — tracing, structured logs, metrics in one middleware."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.observability.config import ObservabilityConfig
from hawkapi.observability.logger import setup_structured_logging
from hawkapi.observability.metrics import InMemoryMetrics

logger = logging.getLogger("hawkapi")


class ObservabilityMiddleware(Middleware):
    """All-in-one observability: tracing, structured logs, metrics.

    Usage:
        app.add_middleware(ObservabilityMiddleware)
        app.add_middleware(ObservabilityMiddleware, config=ObservabilityConfig(...))
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        config: ObservabilityConfig | None = None,
    ) -> None:
        """Create the observability middleware with optional config."""
        super().__init__(app)
        self.config = config or ObservabilityConfig()

        if self.config.enable_logging:
            setup_structured_logging(self.config.log_level)

        self.metrics = InMemoryMetrics()
        self._request_id_header = self.config.request_id_header.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entrypoint — adds tracing, logging, and metrics to HTTP requests."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope["method"]
        path: str = scope["path"]

        # Extract or generate request ID
        request_id: str | None = None
        raw_headers: list[Any] = scope.get("headers", [])
        for key, value in raw_headers:
            if key == self._request_id_header:
                request_id = value.decode("latin-1")
                break
        if request_id is None:
            request_id = str(uuid.uuid4())

        scope["request_id"] = request_id

        # Extract W3C trace context from incoming headers
        trace_ctx: dict[str, Any] = {}
        if self.config.enable_tracing:
            try:
                from hawkapi.observability.tracing import extract_context

                trace_ctx = extract_context(raw_headers)
                scope["trace_id"] = trace_ctx.get("trace_id", "")
                scope["span_id"] = trace_ctx.get("span_id", "")
            except Exception:
                logger.debug("Trace context extraction error", exc_info=True)

        start = time.monotonic()
        status_code = 500

        async def observability_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((self._request_id_header, request_id.encode("latin-1")))

                # Inject W3C trace context into response headers
                if self.config.enable_tracing and trace_ctx:
                    try:
                        from hawkapi.observability.tracing import inject_context

                        headers = inject_context(
                            headers,
                            trace_id=trace_ctx.get("trace_id", ""),
                            span_id=trace_ctx.get("span_id", ""),
                            trace_flags=trace_ctx.get("trace_flags", "01"),
                            tracestate=trace_ctx.get("tracestate", ""),
                        )
                    except Exception:
                        logger.debug("Trace context injection error", exc_info=True)

                message = {**message, "headers": headers}
            await send(message)

        # Tracing — only catch span setup errors, never swallow app errors
        try:
            if self.config.enable_tracing:
                try:
                    from hawkapi.observability.tracing import start_span

                    ctx = start_span(
                        f"{method} {path}",
                        attributes={"http.method": method, "http.target": path},
                    )
                except Exception:
                    logger.debug("Tracing setup error, falling back", exc_info=True)
                    ctx = None

                if ctx is not None:
                    with ctx:
                        await self.app(scope, receive, observability_send)
                else:
                    await self.app(scope, receive, observability_send)
            else:
                await self.app(scope, receive, observability_send)
        finally:
            duration = time.monotonic() - start

            # Metrics — wrapped so failures don't affect the response
            if self.config.enable_metrics:
                try:
                    self.metrics.record_request(method, path, status_code, duration)
                except Exception:
                    logger.debug("Metrics recording error", exc_info=True)

            # Structured log — wrapped for safety
            if self.config.enable_logging:
                try:
                    logger.info(
                        "%s %s %d %.3fms",
                        method,
                        path,
                        status_code,
                        duration * 1000,
                        extra={
                            "request_id": request_id,
                            "trace_id": trace_ctx.get("trace_id", ""),
                            "method": method,
                            "path": path,
                            "status_code": status_code,
                            "duration_ms": round(duration * 1000, 3),
                        },
                    )
                except Exception:
                    logger.debug("Structured logging error", exc_info=True)
