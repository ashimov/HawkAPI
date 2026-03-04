"""Tests for structured logging middleware."""

import pytest

pytest.importorskip("structlog")

from hawkapi import HawkAPI
from hawkapi.middleware.structured_logging import StructuredLoggingMiddleware


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


class TestStructuredLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_adds_request_id_header(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(StructuredLoggingMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test")
        assert resp["status"] == 200
        # Check that x-request-id header was added
        assert b"x-request-id" in resp["headers"]

    @pytest.mark.asyncio
    async def test_preserves_incoming_request_id(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(StructuredLoggingMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(
            app,
            "GET",
            "/test",
            headers=[(b"x-request-id", b"custom-id-123")],
        )
        assert resp["headers"].get(b"x-request-id") == b"custom-id-123"

    @pytest.mark.asyncio
    async def test_custom_header_name(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(StructuredLoggingMiddleware, request_id_header="x-trace-id")

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test")
        assert b"x-trace-id" in resp["headers"]
