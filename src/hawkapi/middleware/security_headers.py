"""Security headers middleware — adds common security headers to responses."""

from __future__ import annotations

from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class SecurityHeadersMiddleware(Middleware):
    """Add common security headers to all HTTP responses.

    Default headers (enabled when a value is provided):
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security (via ``hsts`` param, off by default)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy (via ``permissions_policy`` param)
    - Content-Security-Policy (via ``content_security_policy`` param)
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        content_type_options: str = "nosniff",
        frame_options: str = "DENY",
        xss_protection: str = "1; mode=block",
        hsts: str | None = None,
        referrer_policy: str = "strict-origin-when-cross-origin",
        permissions_policy: str | None = None,
        content_security_policy: str | None = None,
    ) -> None:
        super().__init__(app)
        self._headers: list[tuple[bytes, bytes]] = []

        if content_type_options:
            self._headers.append((b"x-content-type-options", content_type_options.encode()))
        if frame_options:
            self._headers.append((b"x-frame-options", frame_options.encode()))
        if xss_protection:
            self._headers.append((b"x-xss-protection", xss_protection.encode()))
        if hsts:
            self._headers.append((b"strict-transport-security", hsts.encode()))
        if referrer_policy:
            self._headers.append((b"referrer-policy", referrer_policy.encode()))
        if permissions_policy:
            self._headers.append((b"permissions-policy", permissions_policy.encode()))
        if content_security_policy:
            self._headers.append((b"content-security-policy", content_security_policy.encode()))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers_to_add = self._headers

        async def inject_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(headers_to_add)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, inject_headers)
