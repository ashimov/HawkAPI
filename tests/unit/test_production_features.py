"""Tests for production features: health check, request timeout, graceful shutdown,
StaticFiles caching, WebSocket DI, CSP header, and CORS docs."""

import asyncio

import pytest

from hawkapi import HawkAPI
from hawkapi.di.container import Container
from hawkapi.websocket.connection import WebSocket

# --- Helpers ---


def _make_scope(path="/", method="GET", headers=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "server": ("localhost", 8000),
    }


async def _collect(app, scope):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        messages.append(msg)

    await app(scope, receive, send)
    return messages


# =============================================================================
# 1. Health check /healthz
# =============================================================================


class TestHealthCheck:
    async def test_healthz_returns_ok(self):
        app = HawkAPI(openapi_url=None)
        msgs = await _collect(app, _make_scope("/healthz"))
        assert msgs[0]["status"] == 200

    async def test_healthz_custom_url(self):
        app = HawkAPI(openapi_url=None, health_url="/health")
        msgs = await _collect(app, _make_scope("/health"))
        assert msgs[0]["status"] == 200

    async def test_healthz_disabled(self):
        app = HawkAPI(openapi_url=None, health_url=None)
        msgs = await _collect(app, _make_scope("/healthz"))
        assert msgs[0]["status"] == 404


# =============================================================================
# 2. Request timeout
# =============================================================================


class TestRequestTimeout:
    async def test_timeout_triggers_504(self):
        app = HawkAPI(openapi_url=None, request_timeout=0.05)

        @app.get("/slow")
        async def slow_handler(request):
            await asyncio.sleep(1.0)
            return {"ok": True}

        msgs = await _collect(app, _make_scope("/slow"))
        assert msgs[0]["status"] == 504
        body = b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body")
        assert b"timeout" in body.lower() or b"Timeout" in body

    async def test_no_timeout_by_default(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/fast")
        async def fast_handler(request):
            return {"ok": True}

        msgs = await _collect(app, _make_scope("/fast"))
        assert msgs[0]["status"] == 200

    async def test_fast_handler_within_timeout(self):
        app = HawkAPI(openapi_url=None, request_timeout=5.0)

        @app.get("/fast")
        async def fast_handler(request):
            return {"ok": True}

        msgs = await _collect(app, _make_scope("/fast"))
        assert msgs[0]["status"] == 200


# =============================================================================
# 3. Graceful shutdown (in-flight tracking)
# =============================================================================


class TestGracefulShutdown:
    async def test_in_flight_counter(self):
        app = HawkAPI(openapi_url=None)

        inflight_during = None

        @app.get("/check")
        async def handler(request):
            nonlocal inflight_during
            inflight_during = app._in_flight
            return {"ok": True}

        await _collect(app, _make_scope("/check"))
        assert inflight_during == 1
        assert app._in_flight == 0

    async def test_wait_for_in_flight_no_requests(self):
        app = HawkAPI(openapi_url=None)
        # Should complete immediately when no requests in flight
        await app._wait_for_in_flight(timeout=0.1)


# =============================================================================
# 4. StaticFiles ETag/Cache-Control/Last-Modified
# =============================================================================


class TestStaticFilesCaching:
    @pytest.fixture
    def static_dir(self, tmp_path):
        (tmp_path / "hello.txt").write_text("Hello, World!")
        return tmp_path

    def _make_static_scope(self, path="/", method="GET", headers=None):
        return {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "root_path": "",
            "headers": headers or [],
            "server": ("localhost", 8000),
        }

    async def _static_collect(self, app, scope):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            messages.append(msg)

        await app(scope, receive, send)
        return messages

    async def test_etag_header(self, static_dir):
        from hawkapi.staticfiles import StaticFiles

        app = StaticFiles(directory=static_dir)
        msgs = await self._static_collect(app, self._make_static_scope("/hello.txt"))
        assert msgs[0]["status"] == 200
        headers = dict(msgs[0]["headers"])
        assert b"etag" in headers
        assert headers[b"etag"].startswith(b'W/"')

    async def test_last_modified_header(self, static_dir):
        from hawkapi.staticfiles import StaticFiles

        app = StaticFiles(directory=static_dir)
        msgs = await self._static_collect(app, self._make_static_scope("/hello.txt"))
        headers = dict(msgs[0]["headers"])
        assert b"last-modified" in headers

    async def test_cache_control_with_max_age(self, static_dir):
        from hawkapi.staticfiles import StaticFiles

        app = StaticFiles(directory=static_dir, max_age=3600)
        msgs = await self._static_collect(app, self._make_static_scope("/hello.txt"))
        headers = dict(msgs[0]["headers"])
        assert b"cache-control" in headers
        assert b"max-age=3600" in headers[b"cache-control"]

    async def test_cache_control_no_cache_default(self, static_dir):
        from hawkapi.staticfiles import StaticFiles

        app = StaticFiles(directory=static_dir, max_age=0)
        msgs = await self._static_collect(app, self._make_static_scope("/hello.txt"))
        headers = dict(msgs[0]["headers"])
        assert b"cache-control" in headers
        assert headers[b"cache-control"] == b"no-cache"

    async def test_304_on_etag_match(self, static_dir):
        from hawkapi.staticfiles import StaticFiles

        app = StaticFiles(directory=static_dir)
        # First request to get ETag
        msgs = await self._static_collect(app, self._make_static_scope("/hello.txt"))
        etag = dict(msgs[0]["headers"])[b"etag"]

        # Second request with If-None-Match
        scope = self._make_static_scope(
            "/hello.txt",
            headers=[(b"if-none-match", etag)],
        )
        msgs2 = await self._static_collect(app, scope)
        assert msgs2[0]["status"] == 304

    async def test_304_on_if_modified_since(self, static_dir):
        from hawkapi.staticfiles import StaticFiles

        app = StaticFiles(directory=static_dir)
        # First request to get Last-Modified
        msgs = await self._static_collect(app, self._make_static_scope("/hello.txt"))
        last_modified = dict(msgs[0]["headers"])[b"last-modified"]

        # Second request with If-Modified-Since set to same or later time
        scope = self._make_static_scope(
            "/hello.txt",
            headers=[(b"if-modified-since", last_modified)],
        )
        msgs2 = await self._static_collect(app, scope)
        assert msgs2[0]["status"] == 304

    async def test_no_304_on_different_etag(self, static_dir):
        from hawkapi.staticfiles import StaticFiles

        app = StaticFiles(directory=static_dir)
        scope = self._make_static_scope(
            "/hello.txt",
            headers=[(b"if-none-match", b'W/"bogus"')],
        )
        msgs = await self._static_collect(app, scope)
        assert msgs[0]["status"] == 200


# =============================================================================
# 5. WebSocket DI injection
# =============================================================================


class TestWebSocketDI:
    async def test_ws_handler_with_di_service(self):
        container = Container()

        class MyService:
            def greet(self) -> str:
                return "hi from service"

        container.singleton(MyService, factory=MyService)
        app = HawkAPI(openapi_url=None, container=container)

        result = []

        @app.websocket("/ws")
        async def ws_handler(ws: WebSocket, svc: MyService):
            await ws.accept()
            result.append(svc.greet())
            await ws.close()

        messages = [
            {"type": "websocket.connect"},
        ]
        msg_iter = iter(messages)
        sent = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        await app(scope, receive, send)
        assert result == ["hi from service"]

    async def test_ws_handler_simple_no_di(self):
        """WebSocket handler that takes only ws still works."""
        app = HawkAPI(openapi_url=None)
        result = []

        @app.websocket("/ws")
        async def ws_handler(ws: WebSocket):
            await ws.accept()
            result.append("connected")
            await ws.close()

        messages = [{"type": "websocket.connect"}]
        msg_iter = iter(messages)
        sent = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        await app(scope, receive, send)
        assert result == ["connected"]


# =============================================================================
# 6. CSP header in SecurityHeaders
# =============================================================================


class TestCSPHeader:
    def _make_app(self, **kwargs):
        from hawkapi.middleware.security_headers import SecurityHeadersMiddleware

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        return SecurityHeadersMiddleware(inner, **kwargs)

    async def test_csp_header_added(self):
        app = self._make_app(content_security_policy="default-src 'self'")
        msgs = await _collect(app, _make_scope())
        headers = dict(msgs[0]["headers"])
        assert b"content-security-policy" in headers
        assert headers[b"content-security-policy"] == b"default-src 'self'"

    async def test_csp_header_not_added_by_default(self):
        app = self._make_app()
        msgs = await _collect(app, _make_scope())
        headers = dict(msgs[0]["headers"])
        assert b"content-security-policy" not in headers

    async def test_csp_complex_policy(self):
        policy = "default-src 'self'; script-src 'self' 'unsafe-inline'; img-src *"
        app = self._make_app(content_security_policy=policy)
        msgs = await _collect(app, _make_scope())
        headers = dict(msgs[0]["headers"])
        assert headers[b"content-security-policy"] == policy.encode()


# =============================================================================
# 7. CORS docs: blocked origins behavior
# =============================================================================


class TestCORSBlockedOrigins:
    async def test_blocked_origin_gets_response_without_cors_headers(self):
        """Blocked origins still receive the response body but no CORS headers."""
        from hawkapi.middleware.cors import CORSMiddleware

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"secret data"})

        app = CORSMiddleware(inner, allow_origins=["https://allowed.com"])

        scope = _make_scope(headers=[(b"origin", b"https://evil.com")])
        msgs = await _collect(app, scope)

        assert msgs[0]["status"] == 200
        body = b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body")
        assert body == b"secret data"

        # No CORS headers on the response
        headers = dict(msgs[0]["headers"])
        assert b"access-control-allow-origin" not in headers

    async def test_allowed_origin_gets_cors_headers(self):
        """Allowed origins receive CORS headers."""
        from hawkapi.middleware.cors import CORSMiddleware

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        app = CORSMiddleware(inner, allow_origins=["https://allowed.com"])

        scope = _make_scope(headers=[(b"origin", b"https://allowed.com")])
        msgs = await _collect(app, scope)

        headers = dict(msgs[0]["headers"])
        assert b"access-control-allow-origin" in headers
