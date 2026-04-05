"""Tests for TrustedProxyMiddleware."""

import pytest

from hawkapi.middleware.trusted_proxy import TrustedProxyMiddleware


async def _dummy_app(scope, receive, send):
    """Dummy ASGI app that echoes back scope details."""
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        }
    )
    # Encode scope details into response body for assertions
    client = scope.get("client") or ("", 0)
    scheme = scope.get("scheme", "http")
    host = ""
    for key, value in scope.get("headers", []):
        if key == b"host":
            host = value.decode("latin-1")
            break
    body = f"client={client[0]},scheme={scheme},host={host}".encode()
    await send({"type": "http.response.body", "body": body})


async def _call_app(app, *, method="GET", path="/", headers=None, client=None, scheme="http"):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
        "scheme": scheme,
        "client": client or ("127.0.0.1", 12345),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
        "scope": scope,
    }


class TestTrustedProxyMiddleware:
    @pytest.mark.asyncio
    async def test_rewrite_client_ip_from_trusted_proxy(self):
        """Client IP is rewritten from X-Forwarded-For for trusted proxy."""
        app = TrustedProxyMiddleware(
            _dummy_app,
            trusted_proxies=["127.0.0.0/8"],
        )
        resp = await _call_app(
            app,
            client=("127.0.0.1", 12345),
            headers=[
                (b"x-forwarded-for", b"203.0.113.50"),
            ],
        )
        assert resp["status"] == 200
        assert resp["scope"]["client"] == ("203.0.113.50", 0)

    @pytest.mark.asyncio
    async def test_ignore_headers_from_untrusted_proxy(self):
        """X-Forwarded-* headers should be ignored when request comes from untrusted IP."""
        app = TrustedProxyMiddleware(
            _dummy_app,
            trusted_proxies=["10.0.0.0/8"],
        )
        resp = await _call_app(
            app,
            client=("192.168.1.1", 54321),
            headers=[
                (b"x-forwarded-for", b"203.0.113.50"),
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-host", b"evil.com"),
            ],
        )
        assert resp["status"] == 200
        # Client should NOT be rewritten
        assert resp["scope"]["client"] == ("192.168.1.1", 54321)
        # Scheme should NOT be rewritten
        assert resp["scope"]["scheme"] == "http"

    @pytest.mark.asyncio
    async def test_rewrite_scheme_from_x_forwarded_proto(self):
        """Scheme is rewritten from X-Forwarded-Proto for trusted proxy."""
        app = TrustedProxyMiddleware(
            _dummy_app,
            trusted_proxies=["127.0.0.0/8"],
        )
        resp = await _call_app(
            app,
            client=("127.0.0.1", 12345),
            headers=[
                (b"x-forwarded-proto", b"https"),
            ],
        )
        assert resp["status"] == 200
        assert resp["scope"]["scheme"] == "https"

    @pytest.mark.asyncio
    async def test_multiple_ips_in_x_forwarded_for_takes_rightmost_non_trusted(self):
        """When X-Forwarded-For has multiple IPs, the rightmost non-trusted IP is used."""
        app = TrustedProxyMiddleware(
            _dummy_app,
            trusted_proxies=["127.0.0.0/8", "10.0.0.0/8"],
        )
        resp = await _call_app(
            app,
            client=("127.0.0.1", 12345),
            headers=[
                (b"x-forwarded-for", b"203.0.113.50, 10.0.0.1, 172.16.0.1"),
            ],
        )
        assert resp["status"] == 200
        # 172.16.0.1 is the rightmost non-trusted IP (10.0.0.0/8 is trusted)
        assert resp["scope"]["client"] == ("172.16.0.1", 0)

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        """Non-HTTP scopes (e.g. websocket, lifespan) should pass through unchanged."""
        called = False

        async def ws_app(scope, receive, send):
            nonlocal called
            called = True

        app = TrustedProxyMiddleware(
            ws_app,
            trusted_proxies=["127.0.0.0/8"],
        )
        scope = {
            "type": "websocket",
            "client": ("127.0.0.1", 12345),
            "headers": [
                (b"x-forwarded-for", b"203.0.113.50"),
            ],
        }

        async def receive():
            return {}

        async def send(message):
            pass

        await app(scope, receive, send)
        assert called
        # Client should NOT be rewritten for non-HTTP scopes
        assert scope["client"] == ("127.0.0.1", 12345)

    @pytest.mark.asyncio
    async def test_rewrite_host_from_x_forwarded_host(self):
        """Host header is rewritten from X-Forwarded-Host for trusted proxy."""
        app = TrustedProxyMiddleware(
            _dummy_app,
            trusted_proxies=["127.0.0.0/8"],
        )
        resp = await _call_app(
            app,
            client=("127.0.0.1", 12345),
            headers=[
                (b"host", b"internal.local"),
                (b"x-forwarded-host", b"public.example.com"),
            ],
        )
        assert resp["status"] == 200
        # Check that the host header was rewritten in the scope
        host_found = False
        for key, value in resp["scope"]["headers"]:
            if key == b"host":
                assert value == b"public.example.com"
                host_found = True
                break
        assert host_found

    @pytest.mark.asyncio
    async def test_all_headers_rewritten_together(self):
        """All X-Forwarded-* headers should be processed together from a trusted proxy."""
        app = TrustedProxyMiddleware(
            _dummy_app,
            trusted_proxies=["10.0.0.0/8"],
        )
        resp = await _call_app(
            app,
            client=("10.1.2.3", 9999),
            headers=[
                (b"host", b"backend.internal"),
                (b"x-forwarded-for", b"198.51.100.42"),
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-host", b"api.example.com"),
            ],
        )
        assert resp["status"] == 200
        assert resp["scope"]["client"] == ("198.51.100.42", 0)
        assert resp["scope"]["scheme"] == "https"
        for key, value in resp["scope"]["headers"]:
            if key == b"host":
                assert value == b"api.example.com"
                break

    @pytest.mark.asyncio
    async def test_no_forwarded_headers_from_trusted_proxy(self):
        """When no X-Forwarded-* headers are present, scope should remain unchanged."""
        app = TrustedProxyMiddleware(
            _dummy_app,
            trusted_proxies=["127.0.0.0/8"],
        )
        resp = await _call_app(
            app,
            client=("127.0.0.1", 12345),
            headers=[],
        )
        assert resp["status"] == 200
        assert resp["scope"]["client"] == ("127.0.0.1", 12345)
        assert resp["scope"]["scheme"] == "http"

    @pytest.mark.asyncio
    async def test_no_client_in_scope(self):
        """When scope has no client, headers should not be processed."""
        app = TrustedProxyMiddleware(
            _dummy_app,
            trusted_proxies=["127.0.0.0/8"],
        )
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"203.0.113.50")],
            "root_path": "",
            "scheme": "http",
            "client": None,
        }
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200
        # Client should remain None
        assert scope["client"] is None
