"""Structured logging middleware using structlog."""

from __future__ import annotations

import time
import uuid
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class StructuredLoggingMiddleware(Middleware):
    """Emit JSON-structured request/response logs with request ID tracking.

    Usage::

        from hawkapi.middleware.structured_logging import StructuredLoggingMiddleware
        app.add_middleware(StructuredLoggingMiddleware)

    Requires: ``pip install hawkapi[logging]``
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        request_id_header: str = "x-request-id",
        log_level: str = "info",
        configure_structlog: bool = True,
    ) -> None:
        super().__init__(app)
        import structlog  # pyright: ignore[reportMissingImports]

        self._request_id_header = request_id_header.lower().encode("latin-1")
        self._log_level = log_level

        if configure_structlog and not structlog.is_configured():  # pyright: ignore[reportUnknownMemberType]
            structlog.configure(  # pyright: ignore[reportUnknownMemberType]
                processors=[
                    structlog.processors.TimeStamper(fmt="iso"),  # pyright: ignore[reportUnknownMemberType]
                    structlog.processors.add_log_level,  # pyright: ignore[reportUnknownMemberType]
                    structlog.processors.JSONRenderer(),  # pyright: ignore[reportUnknownMemberType]
                ],
                wrapper_class=structlog.BoundLogger,  # pyright: ignore[reportUnknownMemberType]
                logger_factory=structlog.PrintLoggerFactory(),  # pyright: ignore[reportUnknownMemberType]
                cache_logger_on_first_use=True,
            )
        self._logger: Any = structlog.get_logger("hawkapi")  # pyright: ignore[reportUnknownMemberType]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
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

        start = time.monotonic()
        status_code = 500

        async def logging_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((self._request_id_header, request_id.encode("latin-1")))  # type: ignore[union-attr]
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, logging_send)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 3)
            log_fn = getattr(self._logger, self._log_level)
            log_fn(
                "request",
                method=method,
                path=path,
                status=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )
