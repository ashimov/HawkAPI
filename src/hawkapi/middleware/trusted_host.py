"""Trusted host middleware — reject requests from non-whitelisted hosts."""

from __future__ import annotations

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.responses.response import Response


class TrustedHostMiddleware(Middleware):
    """Reject requests whose Host header is not in the allowed list."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.allowed_hosts = {h.lower() for h in (allowed_hosts or ["*"])}
        self.allow_all = "*" in self.allowed_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.allow_all:
            await self.app(scope, receive, send)
            return

        host = ""
        for key, value in scope.get("headers", []):
            if key == b"host":
                host = value.decode("latin-1").split(":")[0].lower()
                break

        if host not in self.allowed_hosts:
            response = Response(
                content=b"Invalid host header",
                status_code=400,
                content_type="text/plain; charset=utf-8",
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
