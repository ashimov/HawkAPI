"""Tests for middleware system."""

import gzip

import msgspec
import pytest

from hawkapi import HawkAPI, Middleware, Response
from hawkapi.middleware.cors import CORSMiddleware
from hawkapi.middleware.gzip import GZipMiddleware
from hawkapi.middleware.timing import TimingMiddleware
from hawkapi.middleware.trusted_host import TrustedHostMiddleware


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


class TestMiddlewareHooks:
    @pytest.mark.asyncio
    async def test_before_request_passthrough(self):
        app = HawkAPI()
        call_log = []

        class LogMiddleware(Middleware):
            async def before_request(self, request):
                call_log.append("before")
                return None

        app.add_middleware(LogMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test")
        assert resp["status"] == 200
        assert call_log == ["before"]

    @pytest.mark.asyncio
    async def test_before_request_short_circuit(self):
        app = HawkAPI()

        class BlockMiddleware(Middleware):
            async def before_request(self, request):
                return Response(content=b"blocked", status_code=403)

        app.add_middleware(BlockMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test")
        assert resp["status"] == 403
        assert resp["body"] == b"blocked"

    @pytest.mark.asyncio
    async def test_after_response_modify(self):
        app = HawkAPI()

        class AddHeaderMiddleware(Middleware):
            async def after_response(self, request, response):
                response.headers["x-custom"] = "added"
                return response

        app.add_middleware(AddHeaderMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test")
        assert resp["status"] == 200
        assert resp["headers"].get(b"x-custom") == b"added"

    @pytest.mark.asyncio
    async def test_middleware_ordering(self):
        app = HawkAPI()
        order = []

        class First(Middleware):
            async def before_request(self, request):
                order.append("first-before")
                return None

        class Second(Middleware):
            async def before_request(self, request):
                order.append("second-before")
                return None

        app.add_middleware(First)
        app.add_middleware(Second)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        await _call_app(app, "GET", "/test")
        # First middleware added = outermost = runs first
        assert order == ["first-before", "second-before"]


class TestTimingMiddleware:
    @pytest.mark.asyncio
    async def test_adds_timing_header(self):
        app = HawkAPI()
        app.add_middleware(TimingMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test")
        assert resp["status"] == 200
        assert b"x-process-time" in resp["headers"]
        time_val = float(resp["headers"][b"x-process-time"])
        assert time_val >= 0


class TestCORSMiddleware:
    @pytest.mark.asyncio
    async def test_cors_preflight(self):
        app = HawkAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])

        @app.get("/api")
        async def handler():
            return {}

        resp = await _call_app(
            app,
            "OPTIONS",
            "/api",
            headers=[(b"origin", b"https://example.com")],
        )
        assert resp["status"] == 200
        assert resp["headers"][b"access-control-allow-origin"] == b"https://example.com"

    @pytest.mark.asyncio
    async def test_cors_simple_request(self):
        app = HawkAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])

        @app.get("/api")
        async def handler():
            return {"data": "value"}

        resp = await _call_app(
            app,
            "GET",
            "/api",
            headers=[(b"origin", b"https://example.com")],
        )
        assert resp["status"] == 200
        assert resp["headers"][b"access-control-allow-origin"] == b"*"

    @pytest.mark.asyncio
    async def test_cors_no_origin_header(self):
        app = HawkAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])

        @app.get("/api")
        async def handler():
            return {"data": "value"}

        resp = await _call_app(app, "GET", "/api")
        assert resp["status"] == 200
        # No CORS headers added
        assert b"access-control-allow-origin" not in resp["headers"]

    @pytest.mark.asyncio
    async def test_cors_disallowed_origin(self):
        app = HawkAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["https://allowed.com"])

        @app.get("/api")
        async def handler():
            return {"data": "value"}

        resp = await _call_app(
            app,
            "GET",
            "/api",
            headers=[(b"origin", b"https://evil.com")],
        )
        assert resp["status"] == 200
        assert b"access-control-allow-origin" not in resp["headers"]


class TestTrustedHostMiddleware:
    @pytest.mark.asyncio
    async def test_allowed_host(self):
        app = HawkAPI()
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost"])

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test", headers=[(b"host", b"localhost:8000")])
        assert resp["status"] == 200

    @pytest.mark.asyncio
    async def test_disallowed_host(self):
        app = HawkAPI()
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost"])

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test", headers=[(b"host", b"evil.com")])
        assert resp["status"] == 400


class TestGZipMiddleware:
    @pytest.mark.asyncio
    async def test_compresses_large_response(self):
        app = HawkAPI()
        app.add_middleware(GZipMiddleware, minimum_size=10)

        @app.get("/test")
        async def handler():
            return {"data": "x" * 1000}

        resp = await _call_app(
            app,
            "GET",
            "/test",
            headers=[(b"accept-encoding", b"gzip")],
        )
        assert resp["status"] == 200
        assert resp["headers"][b"content-encoding"] == b"gzip"
        # Verify it's valid gzip
        decompressed = gzip.decompress(resp["body"])
        data = msgspec.json.decode(decompressed)
        assert data["data"] == "x" * 1000

    @pytest.mark.asyncio
    async def test_skips_small_response(self):
        app = HawkAPI()
        app.add_middleware(GZipMiddleware, minimum_size=10000)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(
            app,
            "GET",
            "/test",
            headers=[(b"accept-encoding", b"gzip")],
        )
        assert resp["status"] == 200
        assert b"content-encoding" not in resp["headers"]

    @pytest.mark.asyncio
    async def test_no_gzip_without_accept(self):
        app = HawkAPI()
        app.add_middleware(GZipMiddleware, minimum_size=10)

        @app.get("/test")
        async def handler():
            return {"data": "x" * 1000}

        resp = await _call_app(app, "GET", "/test")
        assert resp["status"] == 200
        assert b"content-encoding" not in resp["headers"]
