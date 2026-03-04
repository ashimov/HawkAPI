"""Tests for DebugMiddleware."""

import msgspec
import pytest

from hawkapi import HawkAPI
from hawkapi.middleware.debug import DebugMiddleware


async def _call_app(app, method, path, headers=None, body=b""):
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


class TestDebugRoutes:
    @pytest.mark.asyncio
    async def test_debug_routes_returns_registered_routes(self):
        app = HawkAPI()
        app.add_middleware(DebugMiddleware)

        @app.get("/items")
        async def list_items():
            return []

        @app.post("/items")
        async def create_item():
            return {"id": 1}

        resp = await _call_app(app, "GET", "/_debug/routes")
        assert resp["status"] == 200
        assert resp["headers"][b"content-type"] == b"application/json"

        routes = msgspec.json.decode(resp["body"])
        # Find user-defined routes (not internal ones like /openapi.json, /docs, etc.)
        user_routes = [r for r in routes if r["path"] in ("/items",)]
        assert len(user_routes) >= 1  # At least /items appears

        # Verify route structure
        items_get = next(r for r in routes if r["path"] == "/items" and "GET" in r["methods"])
        assert "path" in items_get
        assert "methods" in items_get
        assert "name" in items_get
        assert "deprecated" in items_get
        assert items_get["deprecated"] is False

    @pytest.mark.asyncio
    async def test_debug_routes_shows_deprecated(self):
        app = HawkAPI()
        app.add_middleware(DebugMiddleware)

        @app.get("/old", deprecated=True)
        async def old_endpoint():
            return {}

        resp = await _call_app(app, "GET", "/_debug/routes")
        routes = msgspec.json.decode(resp["body"])
        old_route = next(r for r in routes if r["path"] == "/old")
        assert old_route["deprecated"] is True

    @pytest.mark.asyncio
    async def test_debug_routes_methods_sorted(self):
        app = HawkAPI()
        app.add_middleware(DebugMiddleware)

        @app.get("/test")
        async def test_handler():
            return {}

        resp = await _call_app(app, "GET", "/_debug/routes")
        routes = msgspec.json.decode(resp["body"])
        test_route = next(r for r in routes if r["path"] == "/test")
        # GET route also registers HEAD; methods should be sorted
        assert test_route["methods"] == sorted(test_route["methods"])


class TestDebugStats:
    @pytest.mark.asyncio
    async def test_stats_empty_initially(self):
        app = HawkAPI()
        app.add_middleware(DebugMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/_debug/stats")
        assert resp["status"] == 200
        stats = msgspec.json.decode(resp["body"])
        assert stats == {}

    @pytest.mark.asyncio
    async def test_stats_after_request(self):
        app = HawkAPI()
        app.add_middleware(DebugMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        # Make a request first to populate stats
        await _call_app(app, "GET", "/test")

        # Now check stats
        resp = await _call_app(app, "GET", "/_debug/stats")
        assert resp["status"] == 200
        stats = msgspec.json.decode(resp["body"])

        assert "/test" in stats
        assert stats["/test"]["count"] == 1
        assert stats["/test"]["avg_latency_ms"] >= 0
        assert stats["/test"]["errors"] == 0

    @pytest.mark.asyncio
    async def test_stats_multiple_requests(self):
        app = HawkAPI()
        app.add_middleware(DebugMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        # Make multiple requests
        await _call_app(app, "GET", "/test")
        await _call_app(app, "GET", "/test")
        await _call_app(app, "GET", "/test")

        resp = await _call_app(app, "GET", "/_debug/stats")
        stats = msgspec.json.decode(resp["body"])

        assert stats["/test"]["count"] == 3

    @pytest.mark.asyncio
    async def test_stats_tracks_errors(self):
        app = HawkAPI()
        app.add_middleware(DebugMiddleware)

        # A request to a non-existent path should return 404 (not 5xx)
        # So let's make a handler that causes a 500
        @app.get("/fail")
        async def fail_handler():
            raise RuntimeError("boom")

        await _call_app(app, "GET", "/fail")

        resp = await _call_app(app, "GET", "/_debug/stats")
        stats = msgspec.json.decode(resp["body"])

        assert "/fail" in stats
        assert stats["/fail"]["count"] == 1
        assert stats["/fail"]["errors"] == 1

    @pytest.mark.asyncio
    async def test_stats_does_not_track_debug_endpoints(self):
        """Debug endpoints themselves should not appear in stats."""
        app = HawkAPI()
        app.add_middleware(DebugMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        # Access debug endpoints
        await _call_app(app, "GET", "/_debug/routes")
        await _call_app(app, "GET", "/_debug/stats")

        resp = await _call_app(app, "GET", "/_debug/stats")
        stats = msgspec.json.decode(resp["body"])

        # Debug endpoints should not be tracked
        assert "/_debug/routes" not in stats
        assert "/_debug/stats" not in stats


class TestDebugCustomPrefix:
    @pytest.mark.asyncio
    async def test_custom_prefix(self):
        app = HawkAPI()
        app.add_middleware(DebugMiddleware, prefix="/_internal")

        @app.get("/test")
        async def handler():
            return {"ok": True}

        # Default prefix should not work
        resp = await _call_app(app, "GET", "/_debug/routes")
        assert resp["status"] != 200 or resp["headers"].get(b"content-type") != b"application/json"

        # Custom prefix should work
        resp = await _call_app(app, "GET", "/_internal/routes")
        assert resp["status"] == 200
        routes = msgspec.json.decode(resp["body"])
        assert isinstance(routes, list)


class TestDebugNonHTTPPassthrough:
    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        """Non-HTTP scopes should pass through without interception."""
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = DebugMiddleware(inner_app)

        scope = {"type": "websocket", "path": "/_debug/routes"}
        await middleware(scope, lambda: None, lambda msg: None)

        assert called is True

    @pytest.mark.asyncio
    async def test_lifespan_passthrough(self):
        """Lifespan scopes should pass through."""
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = DebugMiddleware(inner_app)

        scope = {"type": "lifespan"}
        await middleware(scope, lambda: None, lambda msg: None)

        assert called is True
