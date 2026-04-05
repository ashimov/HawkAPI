"""Plugin API for HawkAPI."""

from __future__ import annotations

from typing import Any


class Plugin:
    """Base plugin class. Override hooks to customize behavior."""

    def on_route_registered(self, route: Any) -> Any:
        """Called when a route is registered. Return the (possibly modified) route."""
        return route

    def on_schema_generated(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Called when OpenAPI schema is generated. Return the (possibly enriched) spec."""
        return spec

    def on_startup(self) -> None:
        """Called during application startup."""

    def on_shutdown(self) -> None:
        """Called during application shutdown."""

    def on_exception(self, request: Any, exc: Exception) -> None:
        """Called when an unhandled exception occurs, before the exception handler chain."""

    def on_middleware_added(self, middleware_class: type, kwargs: dict[str, Any]) -> None:
        """Called when a middleware is added to the application."""
