"""Tests for API versioning: version field on routes, VersionRouter, OpenAPI filtering."""

from hawkapi import HawkAPI, Router
from hawkapi.routing.route import Route
from hawkapi.routing.version_router import VersionRouter


def _make_route(path: str, *, version: str | None = None, permissions: list[str] | None = None):
    async def handler():
        return {"ok": True}

    return Route(
        path=path,
        handler=handler,
        methods=frozenset({"GET"}),
        name=f"route_{path}_{version or 'none'}",
        version=version,
        permissions=permissions,
    )


class TestRouteVersionField:
    def test_version_default_none(self):
        route = _make_route("/users")
        assert route.version is None

    def test_version_set(self):
        route = _make_route("/users", version="v2")
        assert route.version == "v2"

    def test_permissions_default_none(self):
        route = _make_route("/users")
        assert route.permissions is None

    def test_permissions_set(self):
        route = _make_route("/admin", permissions=["admin:read", "admin:write"])
        assert route.permissions == ["admin:read", "admin:write"]


class TestVersionRouter:
    def test_version_router_applies_version(self):
        v2 = VersionRouter("v2")

        @v2.get("/users")
        async def list_users():
            return []

        routes = v2.routes
        assert len(routes) == 1
        assert routes[0].version == "v2"
        assert "/v2/" in routes[0].path

    def test_version_router_with_prefix(self):
        v2 = VersionRouter("v2", prefix="/api")

        @v2.get("/items")
        async def list_items():
            return []

        routes = v2.routes
        assert routes[0].path == "/v2/api/items"

    def test_version_router_property(self):
        v2 = VersionRouter("v2")
        assert v2.version == "v2"

    def test_version_override_on_individual_route(self):
        v2 = VersionRouter("v2")

        @v2.get("/special", version="v3")
        async def special():
            return {}

        routes = v2.routes
        assert routes[0].version == "v3"


class TestRouterVersionPropagation:
    def test_router_decorator_version(self):
        router = Router()

        @router.get("/users", version="v1")
        async def list_users():
            return []

        assert router.routes[0].version == "v1"

    def test_router_decorator_permissions(self):
        router = Router()

        @router.get("/admin", permissions=["admin"])
        async def admin_panel():
            return {}

        assert router.routes[0].permissions == ["admin"]


class TestVersionRouterIncludeController:
    def test_version_router_include_controller(self):
        from hawkapi.routing.controllers import Controller, get

        v2 = VersionRouter("v2")

        class ItemController(Controller):
            prefix = "/items"
            tags = ["items"]

            @get("/")
            async def list_items(self):
                return []

        v2.include_controller(ItemController)
        routes = v2.routes
        assert len(routes) == 1
        assert routes[0].version == "v2"
        assert routes[0].path == "/v2/items"

    def test_version_router_include_controller_with_prefix(self):
        from hawkapi.routing.controllers import Controller, get

        v2 = VersionRouter("v2", prefix="/api")

        class ItemController(Controller):
            prefix = "/items"
            tags = ["items"]

            @get("/")
            async def list_items(self):
                return []

        v2.include_controller(ItemController)
        routes = v2.routes
        assert routes[0].path == "/v2/api/items"


class TestOpenAPIVersionFilter:
    def test_openapi_without_filter(self):
        app = HawkAPI()

        @app.get("/users", version="v1")
        async def v1_users():
            return []

        @app.get("/users", version="v2")
        async def v2_users():
            return []

        spec = app.openapi()
        # version="v1" prepends /v1 to path /users -> /v1/users
        assert "/v1/users" in spec["paths"]
        assert "/v2/users" in spec["paths"]

    def test_openapi_with_version_filter(self):
        app = HawkAPI()

        @app.get("/users", version="v1")
        async def v1_users():
            return []

        @app.get("/users", version="v2")
        async def v2_users():
            return []

        spec_v1 = app.openapi(api_version="v1")
        assert "/v1/users" in spec_v1["paths"]
        assert len(spec_v1["paths"]) == 1

    def test_openapi_x_permissions(self):
        app = HawkAPI()

        @app.get("/admin", permissions=["admin:read"])
        async def admin_panel():
            return {}

        spec = app.openapi()
        op = spec["paths"]["/admin"]["get"]
        assert op["x-permissions"] == ["admin:read"]

    def test_openapi_no_x_permissions_when_none(self):
        app = HawkAPI()

        @app.get("/public")
        async def public():
            return {}

        spec = app.openapi()
        op = spec["paths"]["/public"]["get"]
        assert "x-permissions" not in op
