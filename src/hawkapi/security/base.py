"""Security scheme base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from hawkapi.requests.request import Request


class SecurityScheme(ABC):
    """Abstract security scheme that extracts credentials from a request.

    Subclass this to implement custom authentication schemes.
    """

    @abstractmethod
    async def __call__(self, request: Request) -> Any:
        """Extract and validate credentials from the request.

        Returns the extracted credentials/user or raises an exception.
        Returning None signals that no credentials were provided.
        """
        ...

    @property
    def openapi_scheme(self) -> dict[str, Any]:
        """Return the OpenAPI security scheme definition."""
        return {}
