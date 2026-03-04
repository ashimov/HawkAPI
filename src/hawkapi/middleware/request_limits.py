"""Request limits middleware — reject oversized queries and headers early."""

from __future__ import annotations

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.responses.response import Response
from hawkapi.serialization.encoder import encode_response


class RequestLimitsMiddleware(Middleware):
    """Reject requests with oversized query strings or headers before body parsing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_query_length: int = 2048,
        max_headers_count: int = 100,
        max_header_size: int = 8192,
    ) -> None:
        super().__init__(app)
        self.max_query_length = max_query_length
        self.max_headers_count = max_headers_count
        self.max_header_size = max_header_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check query string length
        query_string: bytes = scope.get("query_string", b"")
        if len(query_string) > self.max_query_length:
            detail = (
                f"Query string length {len(query_string)} exceeds limit of {self.max_query_length}"
            )
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/http",
                        "title": "URI Too Long",
                        "status": 414,
                        "detail": detail,
                    }
                ),
                status_code=414,
                content_type="application/problem+json",
            )
            await response(scope, receive, send)
            return

        # Check header count
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        if len(headers) > self.max_headers_count:
            detail = f"Header count {len(headers)} exceeds limit of {self.max_headers_count}"
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/http",
                        "title": "Request Header Fields Too Large",
                        "status": 431,
                        "detail": detail,
                    }
                ),
                status_code=431,
                content_type="application/problem+json",
            )
            await response(scope, receive, send)
            return

        # Check individual header value sizes
        for _name, value in headers:
            if len(value) > self.max_header_size:
                detail = f"Header value size {len(value)} exceeds limit of {self.max_header_size}"
                response = Response(
                    content=encode_response(
                        {
                            "type": "https://hawkapi.ashimov.com/errors/http",
                            "title": "Request Header Fields Too Large",
                            "status": 431,
                            "detail": detail,
                        }
                    ),
                    status_code=431,
                    content_type="application/problem+json",
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
