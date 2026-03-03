"""Tests for middleware edge cases — coverage gaps."""

from __future__ import annotations

from typing import Any

import pytest


class TestCORSEdgeCases:
    @pytest.mark.asyncio
    async def test_preflight_with_wildcard_headers(self):
        """Covers cors.py lines 54, 125-129: allow_all_headers preflight."""
        from hawkapi.middleware.cors import CORSMiddleware

        sent: list[dict[str, Any]] = []

        async def app(scope, receive, send):
            pass

        middleware = CORSMiddleware(
            app,
            allow_origins=["http://example.com"],
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

        scope = {
            "type": "http",
            "method": "OPTIONS",
            "path": "/api",
            "headers": [
                (b"origin", b"http://example.com"),
                (b"access-control-request-method", b"POST"),
                (b"access-control-request-headers", b"content-type, authorization"),
            ],
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await middleware(scope, receive, send)
        # Should reflect the requested headers
        start = sent[0]
        headers_dict = {k: v for k, v in start["headers"]}
        assert b"access-control-allow-headers" in headers_dict

    @pytest.mark.asyncio
    async def test_cors_with_credentials(self):
        """Covers cors.py line 58: allow_credentials."""
        from hawkapi.middleware.cors import CORSMiddleware

        sent: list[dict[str, Any]] = []

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = CORSMiddleware(
            app,
            allow_origins=["http://example.com"],
            allow_credentials=True,
        )

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"origin", b"http://example.com")],
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await middleware(scope, receive, send)

    @pytest.mark.asyncio
    async def test_cors_with_expose_headers(self):
        """Covers cors.py lines 64-68: expose_headers in simple response."""
        from hawkapi.middleware.cors import CORSMiddleware

        sent: list[dict[str, Any]] = []

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = CORSMiddleware(
            app,
            allow_origins=["http://example.com"],
            expose_headers=["X-Custom-Header"],
        )

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"origin", b"http://example.com")],
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await middleware(scope, receive, send)

    @pytest.mark.asyncio
    async def test_cors_non_http_passthrough(self):
        """Covers cors.py line 84: non-http scope passthrough."""
        from hawkapi.middleware.cors import CORSMiddleware

        called = []

        async def app(scope, receive, send):
            called.append(True)

        middleware = CORSMiddleware(app, allow_origins=["*"])

        await middleware({"type": "websocket"}, None, None)
        assert called == [True]


class TestHTTPSRedirect:
    @pytest.mark.asyncio
    async def test_https_redirect(self):
        """Covers https_redirect.py lines 15-16: redirect response."""
        from hawkapi.middleware.https_redirect import HTTPSRedirectMiddleware

        sent: list[dict[str, Any]] = []

        async def app(scope, receive, send):
            pass

        middleware = HTTPSRedirectMiddleware(app)

        scope = {
            "type": "http",
            "scheme": "http",
            "path": "/test",
            "query_string": b"foo=bar",
            "headers": [(b"host", b"example.com")],
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await middleware(scope, receive, send)
        assert sent[0]["status"] == 307


class TestTrustedHost:
    @pytest.mark.asyncio
    async def test_trusted_host_rejected(self):
        """Covers trusted_host.py lines 25-26: rejected host."""
        from hawkapi.middleware.trusted_host import TrustedHostMiddleware

        sent: list[dict[str, Any]] = []

        async def app(scope, receive, send):
            pass

        middleware = TrustedHostMiddleware(app, allowed_hosts=["example.com"])

        scope = {
            "type": "http",
            "headers": [(b"host", b"evil.com")],
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await middleware(scope, receive, send)
        assert sent[0]["status"] == 400
