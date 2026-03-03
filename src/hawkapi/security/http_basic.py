"""HTTP Basic authentication security scheme."""

from __future__ import annotations

import base64
from typing import Any

import msgspec

from hawkapi.requests.request import Request
from hawkapi.security.api_key import missing_credential_error
from hawkapi.security.base import SecurityScheme


class HTTPBasicCredentials(msgspec.Struct, frozen=True):
    """Parsed Basic auth credentials."""

    username: str
    password: str


class HTTPBasic(SecurityScheme):
    """Extract Basic credentials from the Authorization header.

    Usage:
        basic = HTTPBasic()

        @app.get("/secure")
        async def secure(creds: HTTPBasicCredentials = Depends(basic)):
            return {"user": creds.username}
    """

    def __init__(self, *, auto_error: bool = True) -> None:
        """Create an HTTP Basic scheme, raising 401 on missing credentials by default."""
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> HTTPBasicCredentials | None:
        """Extract and decode Basic credentials from the request."""
        auth = request.headers.get("authorization")
        if auth is None:
            if self.auto_error:
                raise missing_credential_error("Missing Authorization header")
            return None

        parts = auth.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "basic":
            if self.auto_error:
                raise missing_credential_error("Invalid Authorization header format")
            return None

        try:
            decoded = base64.b64decode(parts[1]).decode("utf-8")
        except Exception as exc:
            if self.auto_error:
                raise missing_credential_error("Invalid base64 encoding") from exc
            return None

        if ":" not in decoded:
            if self.auto_error:
                raise missing_credential_error("Invalid credentials format")
            return None

        username, _, password = decoded.partition(":")
        return HTTPBasicCredentials(username=username, password=password)

    @property
    def openapi_scheme(self) -> dict[str, Any]:
        """Return the OpenAPI security scheme definition."""
        return {"type": "http", "scheme": "basic"}
