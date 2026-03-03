"""Request ID middleware — assigns a unique ID to each request."""

from __future__ import annotations

import uuid
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class RequestIDMiddleware(Middleware):
    """Assign a unique request ID to each HTTP request.

    Reads X-Request-ID from the incoming request (if present) or generates
    a new UUID4. Injects the ID into the response headers.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        header_name: str = "x-request-id",
    ) -> None:
        super().__init__(app)
        self._header_name = header_name
        self._header_name_bytes = header_name.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check for existing request ID
        request_id = None
        for key, value in scope.get("headers", []):
            if key == self._header_name_bytes:
                request_id = value.decode("latin-1")
                break

        # Reject overly long or injection-prone request IDs
        if request_id is None or len(request_id) > 128 or "\n" in request_id or "\r" in request_id:
            request_id = str(uuid.uuid4())

        # Store in scope for access by handlers
        scope["request_id"] = request_id

        header_name_bytes = self._header_name_bytes
        request_id_bytes = request_id.encode("latin-1")

        async def add_request_id(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((header_name_bytes, request_id_bytes))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, add_request_id)
