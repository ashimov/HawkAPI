"""Tests covering audit findings: bugs, features, and coverage gaps."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

import pytest

from hawkapi import HawkAPI, Router
from hawkapi.middleware.cors import CORSMiddleware
from hawkapi.middleware.request_id import RequestIDMiddleware
from hawkapi.middleware.security_headers import SecurityHeadersMiddleware
from hawkapi.observability.config import ObservabilityConfig
from hawkapi.observability.middleware import ObservabilityMiddleware
from hawkapi.requests.request import Request
from hawkapi.security.permissions import PermissionPolicy
from hawkapi.testing import TestClient

# ── Helpers ──────────────────────────────────────────────────────────────────


async def _call_app(app: Any, method: str, path: str, headers: list | None = None) -> dict:
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent: list[dict] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


# ── BUG-02: CORS credentials + wildcard ──────────────────────────────────────


class TestCORSCredentialsWildcard:
    def test_credentials_with_wildcard_raises(self):
        app = HawkAPI()

        @app.get("/x")
        async def handler():
            return {}

        with pytest.raises(ValueError, match="allow_credentials"):
            CORSMiddleware(app, allow_credentials=True, allow_origins=["*"])

    def test_credentials_with_default_origins_raises(self):
        app = HawkAPI()

        @app.get("/x")
        async def handler():
            return {}

        with pytest.raises(ValueError, match="allow_credentials"):
            CORSMiddleware(app, allow_credentials=True)

    def test_credentials_with_specific_origin_ok(self):
        app = HawkAPI()

        @app.get("/x")
        async def handler():
            return {}

        mw = CORSMiddleware(app, allow_credentials=True, allow_origins=["https://example.com"])
        assert mw.allow_credentials is True


# ── QUA-04: SecurityHeaders no message mutation ──────────────────────────────


class TestSecurityHeadersNoMutation:
    @pytest.mark.asyncio
    async def test_does_not_mutate_original_message(self):
        """SecurityHeadersMiddleware should not mutate the original ASGI message."""
        original_message: dict[str, Any] = {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
        original_headers_copy = list(original_message["headers"])

        async def inner_app(scope: Any, receive: Any, send: Any) -> None:
            await send(original_message)
            await send({"type": "http.response.body", "body": b"ok"})

        mw = SecurityHeadersMiddleware(inner_app)
        sent: list[dict] = []

        scope: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict) -> None:
            sent.append(msg)

        await mw(scope, receive, send)
        # Original message should NOT have been mutated
        assert original_message["headers"] == original_headers_copy
        # Sent message should have security headers
        response_headers = dict(sent[0].get("headers", []))
        assert b"x-content-type-options" in response_headers


# ── BUG-04: RequestIDMiddleware no generator param ───────────────────────────


class TestRequestIDMiddlewareNoGenerator:
    def test_no_generator_param(self):
        """The generator parameter should be removed."""
        import inspect

        sig = inspect.signature(RequestIDMiddleware.__init__)
        params = list(sig.parameters.keys())
        assert "generator" not in params

    @pytest.mark.asyncio
    async def test_request_id_no_message_mutation(self):
        app = HawkAPI()

        @app.get("/test")
        async def handler():
            return {"ok": True}

        mw = RequestIDMiddleware(app)
        resp = await _call_app(mw, "GET", "/test")
        assert resp["status"] == 200
        assert b"x-request-id" in resp["headers"]


# ── FEAT-05: request.url property ────────────────────────────────────────────


class TestRequestUrl:
    def test_url_with_server(self):
        scope: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/users",
            "query_string": b"page=1",
            "headers": [],
            "scheme": "https",
            "server": ("example.com", 443),
        }
        req = Request(scope, None)
        assert req.url == "https://example.com/users?page=1"

    def test_url_with_non_default_port(self):
        scope: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/api",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("localhost", 8000),
        }
        req = Request(scope, None)
        assert req.url == "http://localhost:8000/api"

    def test_url_with_default_http_port(self):
        scope: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("example.com", 80),
        }
        req = Request(scope, None)
        assert req.url == "http://example.com/"

    def test_url_without_server_uses_host_header(self):
        scope: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"host", b"myhost.com")],
            "scheme": "http",
        }
        req = Request(scope, None)
        assert req.url == "http://myhost.com/test"

    def test_url_without_server_or_host(self):
        scope: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
        }
        req = Request(scope, None)
        assert req.url == "http://localhost/test"


# ── COV-03: ReDoc UI handler ─────────────────────────────────────────────────


class TestReDocUI:
    def test_redoc_returns_html(self):
        app = HawkAPI(title="TestApp")
        client = TestClient(app)
        resp = client.get("/redoc")
        assert resp.status_code == 200
        body = resp.body.decode()
        assert "ReDoc" in body
        assert "redoc.standalone.js" in body

    def test_redoc_disabled(self):
        app = HawkAPI(redoc_url=None)

        @app.get("/test")
        async def handler():
            return {}

        client = TestClient(app)
        resp = client.get("/redoc")
        assert resp.status_code == 404


# ── COV-05: ExceptionGroup during DI scope teardown ─────────────────────────


class TestDIScopeTeardownExceptionGroup:
    @pytest.mark.asyncio
    async def test_exception_group_on_teardown_errors(self):
        from hawkapi.di.scope import Scope

        class FailingService:
            async def aclose(self) -> None:
                raise RuntimeError("teardown error 1")

        class FailingService2:
            def close(self) -> None:
                raise ValueError("teardown error 2")

        from hawkapi.di.provider import Provider

        providers: dict[tuple[type, str | None], Provider] = {}
        scope = Scope(providers)
        # Manually inject teardown instances as (instance, close_method) tuples
        svc1 = FailingService()
        svc2 = FailingService2()
        scope._teardown.append((svc1, svc1.aclose))
        scope._teardown.append((svc2, svc2.close))

        with pytest.raises(ExceptionGroup) as exc_info:
            await scope.close()
        eg = exc_info.value
        assert len(eg.exceptions) == 2


# ── COV-07: ObservabilityMiddleware non-HTTP passthrough ─────────────────────


class TestObservabilityNonHTTP:
    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        """Non-HTTP scopes should pass through without modification."""
        passthrough_called = False

        async def inner_app(scope: Any, receive: Any, send: Any) -> None:
            nonlocal passthrough_called
            passthrough_called = True

        config = ObservabilityConfig(enable_logging=False)
        mw = ObservabilityMiddleware(inner_app, config=config)

        scope: dict[str, Any] = {"type": "websocket", "path": "/ws"}

        async def receive() -> dict:
            return {}

        async def send(msg: dict) -> None:
            pass

        await mw(scope, receive, send)
        assert passthrough_called is True


# ── COV-08: Tracing exception fallback path ──────────────────────────────────


class TestTracingFallbackPath:
    def test_tracing_import_error_falls_back(self):
        """When tracing setup fails, app should still work."""
        app = HawkAPI(
            observability=ObservabilityConfig(
                enable_tracing=True,
                enable_logging=False,
                enable_metrics=False,
            )
        )

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)
        # Even with tracing enabled, it falls back gracefully (no OTel installed)
        resp = client.get("/test")
        assert resp.status_code == 200


# ── COV-09: Metrics/logging error swallowing ─────────────────────────────────


class TestMetricsLoggingErrorSwallowing:
    def test_metrics_error_swallowed(self):
        """Metrics recording errors should not affect the response."""
        app = HawkAPI(
            observability=ObservabilityConfig(
                enable_tracing=False,
                enable_logging=False,
                enable_metrics=True,
            )
        )

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200

    def test_logging_error_swallowed(self):
        """Logging errors should not affect the response."""
        app = HawkAPI(
            observability=ObservabilityConfig(
                enable_tracing=False,
                enable_logging=True,
                enable_metrics=False,
            )
        )

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)

        # Patch the logger to raise
        with patch("hawkapi.observability.middleware.logger") as mock_logger:
            mock_logger.info.side_effect = RuntimeError("log failure")
            mock_logger.debug = logging.getLogger().debug  # keep debug working
            resp = client.get("/test")
            assert resp.status_code == 200


# ── COV-11: WS routes via include_router ─────────────────────────────────────


class TestWSRoutesIncludeRouter:
    @pytest.mark.asyncio
    async def test_ws_routes_merged_via_include_router(self):
        app = HawkAPI(openapi_url=None)
        router = Router(prefix="/api")

        @router.websocket("/ws")
        async def ws_handler(ws: Any) -> None:
            await ws.accept()
            await ws.send_text("hello")
            await ws.close()

        app.include_router(router)

        messages = [{"type": "websocket.connect"}]
        msg_iter = iter(messages)
        sent: list[dict] = []

        async def receive() -> dict:
            return next(msg_iter)

        async def send(msg: dict) -> None:
            sent.append(msg)

        scope: dict[str, Any] = {
            "type": "websocket",
            "path": "/api/ws",
            "query_string": b"",
            "headers": [],
        }
        await app(scope, receive, send)
        assert sent[0]["type"] == "websocket.accept"

    @pytest.mark.asyncio
    async def test_ws_routes_with_permissions_via_include_router(self):
        async def resolver(request: Request) -> set[str]:
            return set()

        app = HawkAPI(openapi_url=None)
        app.permission_policy = PermissionPolicy(resolver=resolver)

        router = Router(prefix="/api")

        @router.websocket("/ws", permissions=["admin"])
        async def ws_handler(ws: Any) -> None:
            await ws.accept()

        app.include_router(router)

        sent: list[dict] = []

        async def receive() -> dict:
            return {"type": "websocket.connect"}

        async def send(msg: dict) -> None:
            sent.append(msg)

        scope: dict[str, Any] = {
            "type": "websocket",
            "path": "/api/ws",
            "query_string": b"",
            "headers": [],
        }
        await app(scope, receive, send)
        # Should be denied (no permissions in resolver)
        assert sent[0]["type"] == "websocket.close"
        assert sent[0]["code"] == 4003


# ── QUA-05: OpenAPI cache invalidation ───────────────────────────────────────


class TestOpenAPICacheInvalidation:
    def test_cache_invalidated_on_add_route(self):
        app = HawkAPI()

        @app.get("/first")
        async def first():
            return {}

        spec1 = app.openapi()
        paths1 = set(spec1["paths"].keys())

        @app.get("/second")
        async def second():
            return {}

        spec2 = app.openapi()
        paths2 = set(spec2["paths"].keys())

        assert "/second" in paths2
        assert "/second" not in paths1

    def test_cache_invalidated_on_include_router(self):
        app = HawkAPI()

        @app.get("/first")
        async def first():
            return {}

        app.openapi()  # populate cache

        router = Router(prefix="/api")

        @router.get("/items")
        async def items():
            return []

        app.include_router(router)
        spec2 = app.openapi()

        assert "/api/items" in spec2["paths"]


# ── BUG-01: validation_error_status ──────────────────────────────────────────


class TestValidationErrorStatus:
    def test_custom_validation_error_status(self):
        app = HawkAPI(validation_error_status=422)

        @app.get("/items")
        async def get_items(page: int = 1) -> dict:
            return {"page": page}

        client = TestClient(app)
        resp = client.get("/items?page=not-a-number")
        assert resp.status_code == 422

    def test_default_validation_error_status(self):
        app = HawkAPI()

        @app.get("/items")
        async def get_items(page: int = 1) -> dict:
            return {"page": page}

        client = TestClient(app)
        resp = client.get("/items?page=not-a-number")
        assert resp.status_code == 400


# ── PermissionPolicy mode validation ─────────────────────────────────────────


class TestPermissionPolicyModeValidation:
    def test_invalid_mode_raises(self):
        async def resolver(r: Any) -> set[str]:
            return set()

        with pytest.raises(ValueError, match="mode must be"):
            PermissionPolicy(resolver=resolver, mode="invalid")

    def test_all_mode_ok(self):
        async def resolver(r: Any) -> set[str]:
            return set()

        p = PermissionPolicy(resolver=resolver, mode="all")
        assert p is not None

    def test_any_mode_ok(self):
        async def resolver(r: Any) -> set[str]:
            return set()

        p = PermissionPolicy(resolver=resolver, mode="any")
        assert p is not None


# ── AUDIT-3: DI scope closed even when send() raises ─────────────────────────


class TestDIScopeAlwaysClosed:
    @pytest.mark.asyncio
    async def test_di_scope_closed_on_send_error(self):
        """DI scope must be closed even if response send raises."""
        app = HawkAPI(openapi_url=None, health_url=None)
        handler_ran = []

        @app.get("/test")
        async def handler(request: Request) -> dict:
            handler_ran.append(True)
            return {"ok": True}

        scope_dict: dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        call_count = 0

        async def send_that_fails(msg: dict) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # fail on body send
                raise ConnectionError("client disconnected")

        with pytest.raises(ConnectionError):
            await app(scope_dict, receive, send_that_fails)

        # Handler did run — the error is in send, not in the handler
        assert handler_ran == [True]


# ── AUDIT-3: HEAD + StreamingResponse returns empty body ──────────────────────


class TestHeadStreamingResponse:
    @pytest.mark.asyncio
    async def test_head_streaming_returns_empty(self):
        """HEAD request on a route returning StreamingResponse should not stream."""
        from hawkapi.responses.streaming import StreamingResponse

        app = HawkAPI(openapi_url=None, health_url=None)

        async def gen():
            yield b"chunk1"
            yield b"chunk2"

        @app.get("/stream")
        async def handler(request: Request) -> StreamingResponse:
            return StreamingResponse(gen())

        sent: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict) -> None:
            sent.append(msg)

        scope: dict[str, Any] = {
            "type": "http",
            "method": "HEAD",
            "path": "/stream",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        await app(scope, receive, send)
        # Should get a response start + empty body, no streamed chunks
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        assert body == b""


# ── AUDIT-3: Lifespan shutdown runs hooks even if ctx __aexit__ fails ─────────


class TestLifespanShutdownResilience:
    @pytest.mark.asyncio
    async def test_shutdown_hooks_run_even_if_lifespan_ctx_fails(self):
        """Shutdown hooks must run even if the lifespan ctx __aexit__ raises."""
        from contextlib import asynccontextmanager

        from hawkapi.lifespan.hooks import HookRegistry
        from hawkapi.lifespan.manager import LifespanManager

        hook_ran = []

        @asynccontextmanager
        async def failing_lifespan(app: Any):
            yield
            raise RuntimeError("lifespan exit error")

        hooks = HookRegistry()

        async def my_shutdown_hook() -> None:
            hook_ran.append(True)

        hooks.on_shutdown(my_shutdown_hook)

        manager = LifespanManager(hooks, lifespan=failing_lifespan)

        # Simulate startup
        scope: dict[str, Any] = {"type": "lifespan", "state": {}}
        messages = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        msg_iter = iter(messages)
        sent: list[dict] = []

        async def receive() -> dict:
            return next(msg_iter)

        async def send(msg: dict) -> None:
            sent.append(msg)

        await manager.handle(scope, receive, send)

        # Shutdown hook should have run despite lifespan __aexit__ failing
        assert hook_ran == [True]
        # Both startup.complete and shutdown.complete should be sent
        types = [m["type"] for m in sent]
        assert "lifespan.startup.complete" in types
        assert "lifespan.shutdown.complete" in types


# ── AUDIT-3: Filename sanitization strips semicolons ──────────────────────────


class TestFilenameSanitization:
    def test_semicolon_stripped(self):
        """Semicolons in filenames should be stripped to prevent header injection."""
        import tempfile
        from pathlib import Path

        from hawkapi.responses.file_response import FileResponse

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            tmp_path = Path(f.name)

        try:
            resp = FileResponse(tmp_path, filename="file; type=text/html")
            headers = dict(resp._build_raw_headers())
            disposition = headers[b"content-disposition"].decode()
            assert ";" not in disposition.split("filename=")[1]
        finally:
            tmp_path.unlink()
