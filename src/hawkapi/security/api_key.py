"""API Key security scheme."""

from __future__ import annotations

from typing import Any

from hawkapi.requests.request import Request
from hawkapi.security.base import SecurityScheme


class APIKeyHeader(SecurityScheme):
    """Extract an API key from a request header.

    Usage:
        api_key = APIKeyHeader(name="X-API-Key")

        @app.get("/secure")
        async def secure(key: str = Depends(api_key)):
            return {"key": key}
    """

    def __init__(self, name: str, *, auto_error: bool = True) -> None:
        """Initialize with the header name to extract the key from."""
        self.name = name
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> str | None:
        """Extract the API key from the request header."""
        key = request.headers.get(self.name.lower())
        if key is None and self.auto_error:
            raise missing_credential_error(f"Missing header: {self.name}")
        return key

    @property
    def openapi_scheme(self) -> dict[str, Any]:
        """OpenAPI security scheme definition."""
        return {"type": "apiKey", "in": "header", "name": self.name}


class APIKeyQuery(SecurityScheme):
    """Extract an API key from a query parameter.

    Usage:
        api_key = APIKeyQuery(name="api_key")
    """

    def __init__(self, name: str, *, auto_error: bool = True) -> None:
        """Initialize with the query parameter name to extract the key from."""
        self.name = name
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> str | None:
        """Extract the API key from the query string."""
        key = request.query_params.get(self.name)
        if key is None and self.auto_error:
            raise missing_credential_error(f"Missing query parameter: {self.name}")
        return key

    @property
    def openapi_scheme(self) -> dict[str, Any]:
        """OpenAPI security scheme definition."""
        return {"type": "apiKey", "in": "query", "name": self.name}


class APIKeyCookie(SecurityScheme):
    """Extract an API key from a cookie.

    Usage:
        api_key = APIKeyCookie(name="session_token")
    """

    def __init__(self, name: str, *, auto_error: bool = True) -> None:
        """Initialize with the cookie name to extract the key from."""
        self.name = name
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> str | None:
        """Extract the API key from a cookie."""
        key = request.cookies.get(self.name)
        if key is None and self.auto_error:
            raise missing_credential_error(f"Missing cookie: {self.name}")
        return key

    @property
    def openapi_scheme(self) -> dict[str, Any]:
        """OpenAPI security scheme definition."""
        return {"type": "apiKey", "in": "cookie", "name": self.name}


class MissingCredentialError(Exception):
    """Raised when a required credential is missing.

    Caught by HawkAPI's core handler and converted to a 401 response.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        self.status_code = 401
        super().__init__(detail)


def missing_credential_error(detail: str) -> MissingCredentialError:
    """Create a MissingCredentialError with the given detail message."""
    return MissingCredentialError(detail)
