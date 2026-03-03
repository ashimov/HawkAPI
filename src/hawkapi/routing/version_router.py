"""Version-scoped router that auto-applies a version prefix to all routes."""

from __future__ import annotations

from typing import Any

from hawkapi._types import RouteHandler
from hawkapi.routing.route import Route
from hawkapi.routing.router import Router


class VersionRouter(Router):
    """Router that auto-applies a version to all registered routes.

    Usage:
        v2 = VersionRouter("v2", prefix="/api")

        @v2.get("/users")
        async def list_users():  # -> /api/v2/users
            ...

        app.include_router(v2)
    """

    def __init__(
        self,
        version: str,
        *,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Create a version router with the given API version string."""
        super().__init__(prefix=prefix, tags=tags)
        self._version = version

    @property
    def version(self) -> str:
        """The API version for this router."""
        return self._version

    def add_route(
        self,
        path: str,
        handler: RouteHandler,
        *,
        version: str | None = None,
        **kwargs: Any,
    ) -> Route:
        """Register a route, auto-applying this router's version."""
        return super().add_route(path, handler, version=version or self._version, **kwargs)
