"""OAuth2 password bearer security scheme."""

from __future__ import annotations

from typing import Any

from hawkapi.requests.request import Request
from hawkapi.security.api_key import missing_credential_error
from hawkapi.security.base import SecurityScheme


class OAuth2PasswordBearer(SecurityScheme):
    """OAuth2 with Password flow — extracts the Bearer token.

    Usage:
        oauth2 = OAuth2PasswordBearer(token_url="/auth/token")

        @app.get("/users/me")
        async def me(token: str = Depends(oauth2)):
            user = await verify_token(token)
            return user
    """

    def __init__(
        self,
        token_url: str,
        *,
        scopes: dict[str, str] | None = None,
        auto_error: bool = True,
    ) -> None:
        """Create an OAuth2 Password Bearer scheme.

        ``scopes`` is an optional mapping of ``scope_name → human description``
        reflected into the OpenAPI ``components.securitySchemes`` entry.
        Per-route scope requirements are declared separately via
        ``Security(dep, scopes=[...])``.
        """
        self.token_url = token_url
        self.scopes = dict(scopes) if scopes else {}
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> str | None:
        """Extract the Bearer token string from the request."""
        _headers = {"WWW-Authenticate": "Bearer"}
        auth = request.headers.get("authorization")
        if auth is None:
            if self.auto_error:
                raise missing_credential_error("Not authenticated", headers=_headers)
            return None

        parts = auth.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            if self.auto_error:
                raise missing_credential_error(
                    "Invalid authentication credentials", headers=_headers
                )
            return None

        return parts[1]

    @property
    def openapi_scheme(self) -> dict[str, Any]:
        """Return the OpenAPI security scheme definition."""
        return {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": self.token_url,
                    "scopes": dict(self.scopes),
                },
            },
        }
