"""Tests for security-related middleware (SecurityHeaders, RequestID, HTTPSRedirect)."""


# --- Helpers ---


def _make_scope(path="/", method="GET", headers=None, scheme="https"):
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
        "scheme": scheme,
    }


async def _collect_response(app, scope):
    """Run an ASGI app and collect the response messages."""
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        messages.append(msg)

    await app(scope, receive, send)
    return messages


# --- SecurityHeadersMiddleware ---


class TestSecurityHeaders:
    def _make_app(self, **kwargs):
        from hawkapi.middleware.security_headers import SecurityHeadersMiddleware

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        return SecurityHeadersMiddleware(inner, **kwargs)

    async def test_default_headers(self):
        app = self._make_app()
        msgs = await _collect_response(app, _make_scope())
        headers = dict(msgs[0]["headers"])
        assert b"x-content-type-options" in headers
        assert headers[b"x-content-type-options"] == b"nosniff"
        assert b"x-frame-options" in headers
        assert headers[b"x-frame-options"] == b"DENY"

    async def test_custom_hsts(self):
        app = self._make_app(hsts="max-age=600")
        msgs = await _collect_response(app, _make_scope())
        headers = dict(msgs[0]["headers"])
        assert headers[b"strict-transport-security"] == b"max-age=600"

    async def test_non_http_passthrough(self):
        app = self._make_app()
        scope = {"type": "websocket", "path": "/ws"}
        msgs = await _collect_response(app, scope)
        # Should pass through without headers
        assert len(msgs) == 2


# --- RequestIDMiddleware ---


class TestRequestID:
    def _make_app(self, **kwargs):
        from hawkapi.middleware.request_id import RequestIDMiddleware

        async def inner(scope, receive, send):
            # Echo the request_id from scope
            rid = scope.get("request_id", "none")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": rid.encode(),
                }
            )

        return RequestIDMiddleware(inner, **kwargs)

    async def test_generates_uuid(self):
        app = self._make_app()
        msgs = await _collect_response(app, _make_scope())
        headers = dict(msgs[0]["headers"])
        rid = headers[b"x-request-id"].decode()
        assert len(rid) == 36  # UUID4 format
        assert rid.count("-") == 4

    async def test_preserves_existing_id(self):
        app = self._make_app()
        scope = _make_scope(headers=[(b"x-request-id", b"my-custom-id")])
        msgs = await _collect_response(app, scope)
        headers = dict(msgs[0]["headers"])
        assert headers[b"x-request-id"] == b"my-custom-id"
        # Also stored in scope
        assert scope["request_id"] == "my-custom-id"


# --- HTTPSRedirectMiddleware ---


class TestHTTPSRedirect:
    def _make_app(self):
        from hawkapi.middleware.https_redirect import HTTPSRedirectMiddleware

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        return HTTPSRedirectMiddleware(inner)

    async def test_redirects_http_to_https(self):
        app = self._make_app()
        scope = _make_scope(scheme="http", headers=[(b"host", b"example.com")])
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 307
        headers = dict(msgs[0]["headers"])
        assert b"https://example.com/" in headers.get(b"location", b"")

    async def test_passes_through_https(self):
        app = self._make_app()
        scope = _make_scope(scheme="https")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 200

    async def test_redirect_with_query_string(self):
        app = self._make_app()
        scope = _make_scope(
            scheme="http",
            path="/search",
            headers=[(b"host", b"example.com")],
        )
        scope["query_string"] = b"q=hello"
        msgs = await _collect_response(app, scope)
        headers = dict(msgs[0]["headers"])
        location = headers[b"location"].decode()
        assert location == "https://example.com/search?q=hello"
