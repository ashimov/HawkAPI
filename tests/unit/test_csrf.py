"""Tests for CSRF protection middleware."""

from __future__ import annotations

from hawkapi.middleware.csrf import CSRFMiddleware

SECRET = "test-secret-key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scope(
    path: str = "/",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
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
        "scheme": "https",
    }


async def _inner_app(scope, receive, send):
    """Minimal downstream app that returns 200 OK."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _collect_response(app, scope, body: bytes = b""):
    """Run an ASGI app and collect the response messages."""
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg):
        messages.append(msg)

    await app(scope, receive, send)
    return messages


def _extract_set_cookie(messages: list[dict], cookie_name: str = "csrftoken") -> str | None:
    """Extract the CSRF token from the Set-Cookie header."""
    for msg in messages:
        if msg.get("type") != "http.response.start":
            continue
        for key, value in msg.get("headers", []):
            if key == b"set-cookie":
                cookie_str = value.decode("latin-1")
                if cookie_str.startswith(f"{cookie_name}="):
                    # csrftoken=<value>; Path=...; ...
                    return cookie_str.split(";")[0].split("=", 1)[1]
    return None


def _make_app(**kwargs) -> CSRFMiddleware:
    return CSRFMiddleware(_inner_app, secret=SECRET, **kwargs)


# ---------------------------------------------------------------------------
# Tests: Safe methods
# ---------------------------------------------------------------------------


class TestSafeMethods:
    async def test_get_passes_through(self):
        app = _make_app()
        scope = _make_scope(method="GET")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 200

    async def test_head_passes_through(self):
        app = _make_app()
        scope = _make_scope(method="HEAD")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 200

    async def test_options_passes_through(self):
        app = _make_app()
        scope = _make_scope(method="OPTIONS")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 200

    async def test_trace_passes_through(self):
        app = _make_app()
        scope = _make_scope(method="TRACE")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 200


# ---------------------------------------------------------------------------
# Tests: Cookie generation on safe requests
# ---------------------------------------------------------------------------


class TestCookieGeneration:
    async def test_cookie_set_on_first_safe_request(self):
        app = _make_app()
        scope = _make_scope(method="GET")
        msgs = await _collect_response(app, scope)
        token = _extract_set_cookie(msgs)
        assert token is not None
        assert "." in token  # HMAC-signed format: raw.sig

    async def test_cookie_not_reset_when_already_present(self):
        """If the CSRF cookie already exists, no new Set-Cookie is emitted."""
        app = _make_app()
        # First request — sets the cookie
        scope1 = _make_scope(method="GET")
        msgs1 = await _collect_response(app, scope1)
        token = _extract_set_cookie(msgs1)
        assert token is not None

        # Second request with cookie already set
        scope2 = _make_scope(
            method="GET",
            headers=[(b"cookie", f"csrftoken={token}".encode("latin-1"))],
        )
        msgs2 = await _collect_response(app, scope2)
        new_token = _extract_set_cookie(msgs2)
        assert new_token is None  # No new cookie set

    async def test_cookie_attributes(self):
        app = _make_app(cookie_secure=True, cookie_samesite="strict", cookie_httponly=True)
        scope = _make_scope(method="GET")
        msgs = await _collect_response(app, scope)

        # Find the Set-Cookie header
        set_cookie = None
        for msg in msgs:
            if msg.get("type") != "http.response.start":
                continue
            for key, value in msg.get("headers", []):
                if key == b"set-cookie":
                    set_cookie = value.decode("latin-1")

        assert set_cookie is not None
        assert "Secure" in set_cookie
        assert "SameSite=strict" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Path=/" in set_cookie


# ---------------------------------------------------------------------------
# Tests: Unsafe methods
# ---------------------------------------------------------------------------


class TestUnsafeMethods:
    async def test_post_without_token_returns_403(self):
        app = _make_app()
        scope = _make_scope(method="POST")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 403

    async def test_put_without_token_returns_403(self):
        app = _make_app()
        scope = _make_scope(method="PUT")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 403

    async def test_delete_without_token_returns_403(self):
        app = _make_app()
        scope = _make_scope(method="DELETE")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 403

    async def test_patch_without_token_returns_403(self):
        app = _make_app()
        scope = _make_scope(method="PATCH")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 403

    async def test_403_is_problem_json(self):
        """The 403 response should be RFC 9457 problem+json."""
        import json

        app = _make_app()
        scope = _make_scope(method="POST")
        msgs = await _collect_response(app, scope)
        assert msgs[0]["status"] == 403

        headers = dict(msgs[0].get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("latin-1")
        assert "application/problem+json" in content_type

        body = json.loads(msgs[1]["body"])
        assert body["status"] == 403
        assert body["title"] == "CSRF Validation Failed"
        assert "type" in body

    async def test_post_with_valid_header_token_passes(self):
        app = _make_app()

        # Step 1: GET to obtain a CSRF token cookie
        scope_get = _make_scope(method="GET")
        msgs_get = await _collect_response(app, scope_get)
        token = _extract_set_cookie(msgs_get)
        assert token is not None

        # Step 2: POST with the token in both cookie and header
        scope_post = _make_scope(
            method="POST",
            headers=[
                (b"cookie", f"csrftoken={token}".encode("latin-1")),
                (b"x-csrf-token", token.encode("latin-1")),
            ],
        )
        msgs_post = await _collect_response(app, scope_post)
        assert msgs_post[0]["status"] == 200

    async def test_post_with_mismatched_token_returns_403(self):
        app = _make_app()

        # Step 1: GET to obtain a CSRF token cookie
        scope_get = _make_scope(method="GET")
        msgs_get = await _collect_response(app, scope_get)
        token = _extract_set_cookie(msgs_get)
        assert token is not None

        # Step 2: POST with the cookie but a different header token
        scope_post = _make_scope(
            method="POST",
            headers=[
                (b"cookie", f"csrftoken={token}".encode("latin-1")),
                (b"x-csrf-token", b"wrong-token-value"),
            ],
        )
        msgs_post = await _collect_response(app, scope_post)
        assert msgs_post[0]["status"] == 403

    async def test_post_with_cookie_but_no_token_returns_403(self):
        """Cookie is set but no header or form token submitted."""
        app = _make_app()

        # Step 1: GET to obtain a CSRF token cookie
        scope_get = _make_scope(method="GET")
        msgs_get = await _collect_response(app, scope_get)
        token = _extract_set_cookie(msgs_get)
        assert token is not None

        # Step 2: POST with cookie but no header token and no form body
        scope_post = _make_scope(
            method="POST",
            headers=[
                (b"cookie", f"csrftoken={token}".encode("latin-1")),
            ],
        )
        msgs_post = await _collect_response(app, scope_post)
        assert msgs_post[0]["status"] == 403

    async def test_post_with_form_field_token_passes(self):
        """Token submitted via form field csrf_token should be accepted."""
        app = _make_app()

        # Step 1: GET to obtain a CSRF token cookie
        scope_get = _make_scope(method="GET")
        msgs_get = await _collect_response(app, scope_get)
        token = _extract_set_cookie(msgs_get)
        assert token is not None

        # Step 2: POST with the token in the form body
        from urllib.parse import urlencode

        form_body = urlencode({"csrf_token": token}).encode("utf-8")
        scope_post = _make_scope(
            method="POST",
            headers=[
                (b"cookie", f"csrftoken={token}".encode("latin-1")),
            ],
        )
        msgs_post = await _collect_response(app, scope_post, body=form_body)
        assert msgs_post[0]["status"] == 200


# ---------------------------------------------------------------------------
# Tests: Non-HTTP scopes
# ---------------------------------------------------------------------------


class TestNonHTTPScope:
    async def test_websocket_scope_passes_through(self):
        """Non-HTTP scopes should be forwarded to the inner app unchanged."""
        called = False

        async def ws_inner(scope, receive, send):
            nonlocal called
            called = True

        app = CSRFMiddleware(ws_inner, secret=SECRET)
        scope = {"type": "websocket", "path": "/ws"}

        async def receive():
            return {}

        async def send(msg):
            pass

        await app(scope, receive, send)
        assert called

    async def test_lifespan_scope_passes_through(self):
        called = False

        async def lifespan_inner(scope, receive, send):
            nonlocal called
            called = True

        app = CSRFMiddleware(lifespan_inner, secret=SECRET)
        scope = {"type": "lifespan"}

        async def receive():
            return {}

        async def send(msg):
            pass

        await app(scope, receive, send)
        assert called
