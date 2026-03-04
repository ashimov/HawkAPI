"""HTTP Bearer token security scheme."""

from __future__ import annotations

from typing import Any

import msgspec

from hawkapi.requests.request import Request
from hawkapi.security.api_key import missing_credential_error
from hawkapi.security.base import SecurityScheme


class HTTPBearerCredentials(msgspec.Struct, frozen=True):
    """Parsed Bearer token."""

    scheme: str
    credentials: str


class HTTPBearer(SecurityScheme):
    """Extract a Bearer token from the Authorization header.

    Usage:
        bearer = HTTPBearer()

        @app.get("/secure")
        async def secure(token: HTTPBearerCredentials = Depends(bearer)):
            return {"token": token.credentials}
    """

    def __init__(self, *, auto_error: bool = True) -> None:
        """Create an HTTP Bearer scheme, raising 401 on missing token by default."""
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> HTTPBearerCredentials | None:
        """Extract the Bearer token from the request."""
        _headers = {"WWW-Authenticate": "Bearer"}
        auth = request.headers.get("authorization")
        if auth is None:
            if self.auto_error:
                raise missing_credential_error("Missing Authorization header", headers=_headers)
            return None

        parts = auth.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            if self.auto_error:
                raise missing_credential_error(
                    "Invalid Authorization header format", headers=_headers
                )
            return None

        return HTTPBearerCredentials(scheme=parts[0], credentials=parts[1])

    @property
    def openapi_scheme(self) -> dict[str, Any]:
        """Return the OpenAPI security scheme definition."""
        return {"type": "http", "scheme": "bearer"}
