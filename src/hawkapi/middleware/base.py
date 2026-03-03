"""Unified Middleware base class.

Supports two modes:
1. Raw ASGI override — override __call__ for maximum performance
2. Hook-based — override before_request/after_response for convenience

Both compile to the same ASGI callable pattern internally.
No BaseHTTPMiddleware-style body buffering. Context variables propagate correctly.
"""

from __future__ import annotations

from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.requests.request import Request
from hawkapi.responses.json_response import JSONResponse
from hawkapi.responses.response import Response


class Middleware:
    """Base middleware class. Subclass and override hooks or __call__."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._use_hooks = (
            type(self).before_request is not Middleware.before_request
            or type(self).after_response is not Middleware.after_response
        )

    async def before_request(self, request: Request) -> Request | Response | JSONResponse | None:
        """Called before the route handler.

        Return the request to continue processing.
        Return a Response to short-circuit (skip the handler).
        Return None to continue with the original request.
        """
        return None

    async def after_response(
        self, request: Request, response: Response | JSONResponse
    ) -> Response | JSONResponse | None:
        """Called after the route handler produces a response.

        Return a modified response, or None to keep the original.
        """
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._use_hooks:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Before request hook
        before_result = await self.before_request(request)

        if isinstance(before_result, (Response, JSONResponse)):
            # Short-circuit: send the response directly
            await before_result(scope, receive, send)
            return

        if not self._has_after_hook():
            # No after_response hook — pass through directly
            await self.app(scope, receive, send)
            return

        # Capture the response from downstream
        response_started = False
        initial_message: dict[str, Any] | None = None
        body_parts: list[bytes] = []

        async def capture_send(message: dict[str, Any]) -> None:
            nonlocal response_started, initial_message
            if message["type"] == "http.response.start":
                response_started = True
                initial_message = message
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        await self.app(scope, receive, capture_send)

        if initial_message is None:
            return

        # Reconstruct a Response for the after_response hook
        status_code = initial_message["status"]
        raw_headers: list[tuple[bytes, bytes]] = initial_message.get("headers", [])
        body = b"".join(body_parts)

        headers_dict: dict[str, str] = {}
        content_type = "application/octet-stream"
        for hdr_pair in raw_headers:  # pyright: ignore[reportUnknownVariableType]
            k: str = hdr_pair[0].decode("latin-1").lower()  # pyright: ignore[reportUnknownMemberType]
            v = hdr_pair[1].decode("latin-1")
            if k == "content-type":
                content_type = v
            else:
                headers_dict[k] = v

        captured_response = Response(
            content=body,
            status_code=status_code,
            headers=headers_dict,
            content_type=content_type,
        )

        after_result = await self.after_response(request, captured_response)
        final_response = after_result if after_result is not None else captured_response

        await final_response(scope, receive, send)

    def _has_after_hook(self) -> bool:
        return type(self).after_response is not Middleware.after_response
