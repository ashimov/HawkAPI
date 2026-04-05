"""Tests for per-route middleware support."""

import msgspec
import pytest

from hawkapi import HawkAPI, Middleware, Response


async def _call_app(app, method, path, headers=None, body=b""):
    """Helper to call an ASGI app and capture the response."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestPerRouteMiddleware:
    """Test that middleware can be applied to individual routes."""

    @pytest.mark.asyncio
    async def test_route_with_middleware_applies_it(self):
        """A route with per-route middleware should have that middleware run."""
        app = HawkAPI()
        call_log = []

        class LogMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("before")
                return None

            async def after_response(self, request, response):
                call_log.append("after")
                return response

        @app.get("/with-mw", middleware=[LogMiddleware])
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/with-mw")
        assert resp["status"] == 200
        assert call_log == ["before", "after"]

    @pytest.mark.asyncio
    async def test_route_without_middleware_works_normally(self):
        """Routes without per-route middleware should work as before."""
        app = HawkAPI()
        call_log = []

        class LogMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("should-not-run")
                return None

        @app.get("/no-mw")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/no-mw")
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body == {"ok": True}
        assert call_log == []

    @pytest.mark.asyncio
    async def test_multiple_middleware_correct_ordering(self):
        """Multiple per-route middleware should execute in list order (first = outermost)."""
        app = HawkAPI()
        call_log = []

        class FirstMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("first-before")
                return None

            async def after_response(self, request, response):
                call_log.append("first-after")
                return response

        class SecondMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("second-before")
                return None

            async def after_response(self, request, response):
                call_log.append("second-after")
                return response

        @app.get("/multi-mw", middleware=[FirstMiddleware, SecondMiddleware])
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/multi-mw")
        assert resp["status"] == 200
        # Onion model: first added = outermost
        # before: first -> second -> handler -> second-after -> first-after
        assert call_log == [
            "first-before",
            "second-before",
            "second-after",
            "first-after",
        ]

    @pytest.mark.asyncio
    async def test_route_middleware_does_not_affect_other_routes(self):
        """Per-route middleware on one route must not run for other routes."""
        app = HawkAPI()
        call_log = []

        class TrackingMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("tracked")
                return None

        @app.get("/tracked", middleware=[TrackingMiddleware])
        async def tracked():
            return {"tracked": True}

        @app.get("/untracked")
        async def untracked():
            return {"tracked": False}

        # Call the untracked route first
        resp1 = await _call_app(app, "GET", "/untracked")
        assert resp1["status"] == 200
        assert call_log == []

        # Call the tracked route
        resp2 = await _call_app(app, "GET", "/tracked")
        assert resp2["status"] == 200
        assert call_log == ["tracked"]

    @pytest.mark.asyncio
    async def test_route_middleware_with_kwargs(self):
        """Per-route middleware can be specified as (class, kwargs) tuples."""
        app = HawkAPI()

        class HeaderMiddleware(Middleware):
            def __init__(self, app, header_name="X-Custom", header_value="default"):
                super().__init__(app)
                self.header_name = header_name
                self.header_value = header_value

            async def after_response(self, request, response):
                response._headers[self.header_name.lower()] = self.header_value
                return response

        @app.get(
            "/custom-header",
            middleware=[(HeaderMiddleware, {"header_name": "X-Test", "header_value": "hello"})],
        )
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/custom-header")
        assert resp["status"] == 200
        assert resp["headers"].get(b"x-test") == b"hello"

    @pytest.mark.asyncio
    async def test_route_middleware_short_circuit(self):
        """Per-route middleware can short-circuit and prevent the handler from running."""
        app = HawkAPI()
        handler_called = False

        class BlockMiddleware(Middleware):
            async def before_request(self, request):
                return Response(content=b"blocked", status_code=403)

        @app.get("/blocked", middleware=[BlockMiddleware])
        async def handler():
            nonlocal handler_called
            handler_called = True
            return {"ok": True}

        resp = await _call_app(app, "GET", "/blocked")
        assert resp["status"] == 403
        assert resp["body"] == b"blocked"
        assert not handler_called

    @pytest.mark.asyncio
    async def test_route_middleware_with_app_level_middleware(self):
        """Per-route middleware runs inside app-level middleware."""
        app = HawkAPI()
        call_log = []

        class AppMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("app-before")
                return None

            async def after_response(self, request, response):
                call_log.append("app-after")
                return response

        class RouteMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("route-before")
                return None

            async def after_response(self, request, response):
                call_log.append("route-after")
                return response

        app.add_middleware(AppMiddleware)

        @app.get("/both", middleware=[RouteMiddleware])
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/both")
        assert resp["status"] == 200
        # App middleware wraps everything (outermost), route middleware is inner
        assert call_log == [
            "app-before",
            "route-before",
            "route-after",
            "app-after",
        ]

    @pytest.mark.asyncio
    async def test_route_middleware_stored_on_route_object(self):
        """The middleware tuple should be accessible on the Route object."""
        app = HawkAPI()

        class SomeMiddleware(Middleware):
            pass

        @app.get("/check", middleware=[SomeMiddleware])
        async def handler():
            return {"ok": True}

        routes = app.routes
        route = [r for r in routes if r.path == "/check"][0]
        assert route.middleware is not None
        assert len(route.middleware) == 1
        assert route.middleware[0] is SomeMiddleware

    @pytest.mark.asyncio
    async def test_route_without_middleware_has_none(self):
        """Routes without middleware should have middleware=None on the Route object."""
        app = HawkAPI()

        @app.get("/plain")
        async def handler():
            return {"ok": True}

        routes = app.routes
        route = [r for r in routes if r.path == "/plain"][0]
        assert route.middleware is None

    @pytest.mark.asyncio
    async def test_per_route_middleware_via_add_route(self):
        """Per-route middleware works when using add_route() directly."""
        app = HawkAPI()
        call_log = []

        class DirectMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("direct")
                return None

        async def my_handler():
            return {"direct": True}

        app.add_route(
            "/direct",
            my_handler,
            methods={"GET"},
            middleware=[DirectMiddleware],
        )

        resp = await _call_app(app, "GET", "/direct")
        assert resp["status"] == 200
        assert call_log == ["direct"]

    @pytest.mark.asyncio
    async def test_per_route_middleware_preserved_in_include_router(self):
        """Per-route middleware should survive include_router merging."""
        from hawkapi.routing.router import Router

        app = HawkAPI()
        call_log = []

        class SubMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("sub")
                return None

        router = Router(prefix="/api")

        @router.get("/items", middleware=[SubMiddleware])
        async def items():
            return {"items": []}

        app.include_router(router)

        resp = await _call_app(app, "GET", "/api/items")
        assert resp["status"] == 200
        assert call_log == ["sub"]
