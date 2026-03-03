"""HTTPException — raise to return an HTTP error response from anywhere."""

from __future__ import annotations

from typing import Any

from hawkapi.responses.response import Response
from hawkapi.serialization.encoder import encode_response


class HTTPException(Exception):
    """Raise to immediately return an HTTP error response.

    Usage:
        raise HTTPException(404, detail="User not found")
        raise HTTPException(403, detail="Forbidden", headers={"X-Reason": "expired"})
    """

    def __init__(
        self,
        status_code: int,
        detail: str = "",
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        super().__init__(detail)

    def to_response(self) -> Response:
        """Convert to an ASGI-compatible Response."""
        body: dict[str, Any] = {
            "type": "https://hawkapi.ashimov.com/errors/http",
            "title": _STATUS_PHRASES.get(self.status_code, "Error"),
            "status": self.status_code,
        }
        if self.detail:
            body["detail"] = self.detail

        return Response(
            content=encode_response(body),
            status_code=self.status_code,
            headers=self.headers,
            content_type="application/problem+json",
        )


_STATUS_PHRASES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}
