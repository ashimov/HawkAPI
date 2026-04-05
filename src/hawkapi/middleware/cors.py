"""CORS (Cross-Origin Resource Sharing) middleware."""

from __future__ import annotations

from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class CORSMiddleware(Middleware):
    """Handle CORS preflight and response headers.

    Pure ASGI implementation — no body buffering, no contextvars issues.

    Note on blocked origins:
        When an origin is not in ``allow_origins``, the request is still
        forwarded to the application — it just won't receive CORS headers
        in the response. This is correct per the CORS spec: the *browser*
        enforces the policy by checking for the ``Access-Control-Allow-Origin``
        header. The server cannot prevent a non-browser client from reading
        the response. If you need to reject requests from disallowed origins
        at the server level, add a separate middleware or guard.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        allow_credentials: bool = False,
        expose_headers: list[str] | None = None,
        max_age: int = 600,
    ) -> None:
        super().__init__(app)

        origins = allow_origins or ["*"]
        if allow_credentials and "*" in origins:
            msg = "allow_credentials=True cannot be used with allow_origins=['*']"
            raise ValueError(msg)

        self.allow_origins = origins
        self.allow_methods = allow_methods or [
            "GET",
            "HEAD",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers or []
        self.max_age = max_age

        self._allow_all_origins = "*" in self.allow_origins
        self._allow_all_headers = "*" in self.allow_headers

        # Pre-encode headers that don't change per-request
        self._preflight_headers = self._build_preflight_headers()
        self._simple_headers = self._build_simple_headers()

    def _build_preflight_headers(self) -> list[tuple[bytes, bytes]]:
        headers: list[tuple[bytes, bytes]] = [
            (b"access-control-allow-methods", ", ".join(self.allow_methods).encode("latin-1")),
            (b"access-control-max-age", str(self.max_age).encode("latin-1")),
        ]
        if self._allow_all_headers:
            # Will be set dynamically from request
            pass
        else:
            headers.append(
                (b"access-control-allow-headers", ", ".join(self.allow_headers).encode("latin-1"))
            )
        if self.allow_credentials:
            headers.append((b"access-control-allow-credentials", b"true"))
        return headers

    def _build_simple_headers(self) -> list[tuple[bytes, bytes]]:
        headers: list[tuple[bytes, bytes]] = []
        if self.allow_credentials:
            headers.append((b"access-control-allow-credentials", b"true"))
        if self.expose_headers:
            headers.append(
                (b"access-control-expose-headers", ", ".join(self.expose_headers).encode("latin-1"))
            )
        return headers

    def _get_origin(self, scope: Scope) -> str | None:
        for key, value in scope.get("headers", []):
            if key == b"origin":
                return value.decode("latin-1")
        return None

    def _is_origin_allowed(self, origin: str) -> bool:
        if self._allow_all_origins:
            return True
        return origin in self.allow_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origin = self._get_origin(scope)
        if origin is None:
            # No Origin header — not a CORS request
            await self.app(scope, receive, send)
            return

        if not self._is_origin_allowed(origin):
            # Still inject Vary: Origin so shared caches don't poison responses
            async def vary_send(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"vary", b"Origin"))
                    message = {**message, "headers": headers}
                await send(message)

            await self.app(scope, receive, vary_send)
            return

        # Handle preflight
        if scope["method"] == "OPTIONS":
            await self._handle_preflight(scope, receive, send, origin)
            return

        # Regular CORS request — inject headers into the response
        async def cors_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(self._origin_header(origin))
                headers.extend(self._simple_headers)
                # Vary header for caching
                headers.append((b"vary", b"Origin"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, cors_send)

    async def _handle_preflight(
        self, scope: Scope, receive: Receive, send: Send, origin: str
    ) -> None:
        headers: list[tuple[bytes, bytes]] = [
            self._origin_header(origin),
            (b"vary", b"Origin"),
        ]
        headers.extend(self._preflight_headers)

        # If allow_all_headers, reflect the request's Access-Control-Request-Headers
        if self._allow_all_headers:
            for key, value in scope.get("headers", []):
                if key == b"access-control-request-headers":
                    headers.append((b"access-control-allow-headers", value))
                    break

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"",
            }
        )

    def _origin_header(self, origin: str) -> tuple[bytes, bytes]:
        if self._allow_all_origins and not self.allow_credentials:
            return (b"access-control-allow-origin", b"*")
        return (b"access-control-allow-origin", origin.encode("latin-1"))
