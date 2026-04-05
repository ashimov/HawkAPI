"""HTTPS redirect middleware — redirects HTTP to HTTPS."""

from __future__ import annotations

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.responses.redirect import RedirectResponse


class HTTPSRedirectMiddleware(Middleware):
    """Redirect all HTTP requests to HTTPS.

    Args:
        redirect_status_code: HTTP status code for the redirect (default: 307).
            Use 301 for permanent redirects in production, 307 to preserve request method.
    """

    def __init__(self, app: ASGIApp, *, redirect_status_code: int = 307) -> None:
        super().__init__(app)
        self._redirect_status_code = redirect_status_code

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("scheme") == "http":
            host = ""
            for key, value in scope.get("headers", []):
                if key == b"host":
                    host = value.decode("latin-1")
                    break

            # Validate host to prevent open redirect via crafted Host header
            if not host or "/" in host or "\\" in host:
                host = "localhost"

            path = scope.get("path", "/")
            query_string = scope.get("query_string", b"")
            url = f"https://{host}{path}"
            if query_string:
                url += f"?{query_string.decode('ascii', errors='ignore')}"

            response = RedirectResponse(url, status_code=self._redirect_status_code)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
