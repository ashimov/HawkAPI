"""Request timing middleware — adds X-Process-Time header."""

from __future__ import annotations

import time
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class TimingMiddleware(Middleware):
    """Add X-Process-Time header to responses."""

    def __init__(self, app: ASGIApp, *, header_name: str = "x-process-time") -> None:
        super().__init__(app)
        self.header_name = header_name.encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()

        async def timed_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                duration = time.monotonic() - start
                headers = list(message.get("headers", []))
                headers.append((self.header_name, f"{duration:.6f}".encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, timed_send)
