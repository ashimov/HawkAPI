"""Tests for the Plugin API."""

from __future__ import annotations

from typing import Any

from hawkapi import HawkAPI
from hawkapi.plugins import Plugin
from hawkapi.requests import Request

# Disable all built-in doc/health routes so only test routes exist.
_NO_DOCS = dict(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    scalar_url=None,
    health_url=None,
)


class TestPluginRouteRegistered:
    """Plugin receives on_route_registered callback."""

    def test_plugin_receives_route_on_registration(self) -> None:
        """Plugin.on_route_registered is called when a route is added."""
        received: list[Any] = []

        class TrackingPlugin(Plugin):
            def on_route_registered(self, route: Any) -> Any:
                received.append(route)
                return route

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(TrackingPlugin())

        @app.get("/items")
        async def list_items(request: Request) -> list[str]:
            return []

        assert len(received) == 1
        assert received[0].path == "/items"

    def test_plugin_receives_correct_route_details(self) -> None:
        """The route passed to on_route_registered has the expected attributes."""
        captured_route: list[Any] = []

        class InspectorPlugin(Plugin):
            def on_route_registered(self, route: Any) -> Any:
                captured_route.append(route)
                return route

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(InspectorPlugin())

        @app.post("/users", status_code=201, tags=["users"])
        async def create_user(request: Request) -> dict[str, str]:
            return {"id": "1"}

        assert len(captured_route) == 1
        route = captured_route[0]
        assert route.path == "/users"
        assert "POST" in route.methods
        assert route.status_code == 201
        assert "users" in route.tags


class TestPluginSchemaGenerated:
    """Plugin can enrich OpenAPI schema via on_schema_generated."""

    def test_plugin_can_enrich_openapi_schema(self) -> None:
        """on_schema_generated allows modifying the generated spec."""

        class EnrichPlugin(Plugin):
            def on_schema_generated(self, spec: dict[str, Any]) -> dict[str, Any]:
                spec["info"]["x-custom"] = "enriched"
                return spec

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(EnrichPlugin())

        @app.get("/ping")
        async def ping(request: Request) -> dict[str, str]:
            return {"pong": "ok"}

        spec = app.openapi()
        assert spec["info"]["x-custom"] == "enriched"

    def test_plugin_schema_enrichment_is_cached(self) -> None:
        """The enriched schema is cached so the plugin is not called again."""
        call_count = 0

        class CountingPlugin(Plugin):
            def on_schema_generated(self, spec: dict[str, Any]) -> dict[str, Any]:
                nonlocal call_count
                call_count += 1
                spec["info"]["x-count"] = call_count
                return spec

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(CountingPlugin())

        @app.get("/test")
        async def test_endpoint(request: Request) -> dict[str, str]:
            return {}

        spec1 = app.openapi()
        spec2 = app.openapi()
        assert call_count == 1
        assert spec1["info"]["x-count"] == 1
        assert spec2["info"]["x-count"] == 1


class TestMultiplePlugins:
    """Multiple plugins are called in order."""

    def test_multiple_plugins_route_registered_in_order(self) -> None:
        """Plugins are notified of route registration in the order they were added."""
        order: list[str] = []

        class PluginA(Plugin):
            def on_route_registered(self, route: Any) -> Any:
                order.append("A")
                return route

        class PluginB(Plugin):
            def on_route_registered(self, route: Any) -> Any:
                order.append("B")
                return route

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(PluginA())
        app.add_plugin(PluginB())

        @app.get("/test")
        async def handler(request: Request) -> dict[str, str]:
            return {}

        assert order == ["A", "B"]

    def test_multiple_plugins_schema_generated_in_order(self) -> None:
        """Plugins enrich schema in the order they were added (chained)."""

        class PluginFirst(Plugin):
            def on_schema_generated(self, spec: dict[str, Any]) -> dict[str, Any]:
                spec["info"]["x-first"] = True
                return spec

        class PluginSecond(Plugin):
            def on_schema_generated(self, spec: dict[str, Any]) -> dict[str, Any]:
                # Verify first plugin already ran
                spec["info"]["x-second"] = True
                spec["info"]["x-first-was-set"] = spec["info"].get("x-first", False)
                return spec

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(PluginFirst())
        app.add_plugin(PluginSecond())

        @app.get("/test")
        async def handler(request: Request) -> dict[str, str]:
            return {}

        spec = app.openapi()
        assert spec["info"]["x-first"] is True
        assert spec["info"]["x-second"] is True
        assert spec["info"]["x-first-was-set"] is True


class TestDefaultPlugin:
    """Default Plugin (no overrides) doesn't break anything."""

    def test_default_plugin_does_not_break_route_registration(self) -> None:
        """A Plugin with no overrides passes through route registration safely."""
        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(Plugin())

        @app.get("/safe")
        async def safe_handler(request: Request) -> dict[str, str]:
            return {"ok": "yes"}

        assert any(r.path == "/safe" for r in app.routes)

    def test_default_plugin_does_not_break_schema_generation(self) -> None:
        """A Plugin with no overrides passes through schema generation safely."""
        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(Plugin())

        @app.get("/info")
        async def info_handler(request: Request) -> dict[str, str]:
            return {"version": "1"}

        spec = app.openapi()
        assert "paths" in spec
        assert "/info" in spec["paths"]

    def test_default_plugin_on_route_registered_returns_route(self) -> None:
        """The base Plugin.on_route_registered returns the route unchanged."""
        plugin = Plugin()
        sentinel = object()
        assert plugin.on_route_registered(sentinel) is sentinel

    def test_default_plugin_on_schema_generated_returns_spec(self) -> None:
        """The base Plugin.on_schema_generated returns the spec unchanged."""
        plugin = Plugin()
        spec = {"openapi": "3.1.0", "info": {"title": "Test"}}
        result = plugin.on_schema_generated(spec)
        assert result is spec
