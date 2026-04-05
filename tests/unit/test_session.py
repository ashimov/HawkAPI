"""Tests for cookie-based session middleware."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

import msgspec
import pytest

from hawkapi import HawkAPI
from hawkapi.middleware.session import SessionMiddleware

SECRET = "test-secret-key-for-sessions"


async def _call_app(
    app: Any,
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
        "raw_headers": sent[0].get("headers", []),
    }


def _extract_session_cookie(resp: dict[str, Any], cookie_name: str = "session") -> str | None:
    """Extract the session cookie value from Set-Cookie headers."""
    for key, value in resp["raw_headers"]:
        if key == b"set-cookie":
            header_str = value.decode("latin-1")
            # Parse "session=<value>; ..."
            if header_str.startswith(f"{cookie_name}="):
                cookie_val = header_str.split(";")[0].split("=", 1)[1]
                return cookie_val
    return None


def _make_cookie_header(cookie_name: str, cookie_value: str) -> tuple[bytes, bytes]:
    """Build a Cookie request header."""
    return (b"cookie", f"{cookie_name}={cookie_value}".encode("latin-1"))


def _forge_cookie(data: dict[str, Any], secret: str, timestamp: int | None = None) -> str:
    """Create a valid signed cookie for testing."""
    json_bytes = msgspec.json.encode(data)
    b64_data = base64.urlsafe_b64encode(json_bytes).decode("ascii")
    ts = str(timestamp if timestamp is not None else int(time.time()))
    payload = f"{b64_data}.{ts}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


class TestSessionMissing:
    """Missing cookie results in empty session."""

    @pytest.mark.asyncio
    async def test_missing_cookie_gives_empty_session(self) -> None:
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        @app.get("/check")
        async def handler(request: Any) -> dict[str, Any]:
            session: dict[str, Any] = request.scope["session"]
            return {"session": session}

        resp = await _call_app(app, "GET", "/check")
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["session"] == {}


class TestSessionPersistence:
    """Session data set in one request can be read in another."""

    @pytest.mark.asyncio
    async def test_set_and_read_session(self) -> None:
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        @app.get("/set")
        async def set_handler(request: Any) -> dict[str, str]:
            request.scope["session"]["user"] = "alice"
            return {"status": "set"}

        @app.get("/get")
        async def get_handler(request: Any) -> dict[str, Any]:
            return {"user": request.scope["session"].get("user", "")}

        # First request: set session data
        resp1 = await _call_app(app, "GET", "/set")
        assert resp1["status"] == 200
        cookie = _extract_session_cookie(resp1)
        assert cookie is not None

        # Second request: read session data with cookie
        resp2 = await _call_app(
            app, "GET", "/get", headers=[_make_cookie_header("session", cookie)]
        )
        assert resp2["status"] == 200
        body = msgspec.json.decode(resp2["body"])
        assert body["user"] == "alice"


class TestSessionTampering:
    """Tampered cookie results in fresh empty session."""

    @pytest.mark.asyncio
    async def test_tampered_signature_gives_empty_session(self) -> None:
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        @app.get("/check")
        async def handler(request: Any) -> dict[str, Any]:
            return {"session": request.scope["session"]}

        # Create a valid cookie, then tamper with the signature
        valid_cookie = _forge_cookie({"user": "alice"}, SECRET)
        tampered = valid_cookie[:-4] + "XXXX"

        resp = await _call_app(
            app, "GET", "/check", headers=[_make_cookie_header("session", tampered)]
        )
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["session"] == {}

    @pytest.mark.asyncio
    async def test_tampered_data_gives_empty_session(self) -> None:
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        @app.get("/check")
        async def handler(request: Any) -> dict[str, Any]:
            return {"session": request.scope["session"]}

        # Forge a cookie with wrong secret
        bad_cookie = _forge_cookie({"user": "eve"}, "wrong-secret")

        resp = await _call_app(
            app, "GET", "/check", headers=[_make_cookie_header("session", bad_cookie)]
        )
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["session"] == {}

    @pytest.mark.asyncio
    async def test_malformed_cookie_gives_empty_session(self) -> None:
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        @app.get("/check")
        async def handler(request: Any) -> dict[str, Any]:
            return {"session": request.scope["session"]}

        resp = await _call_app(
            app, "GET", "/check", headers=[_make_cookie_header("session", "garbage-value")]
        )
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["session"] == {}


class TestSessionExpiry:
    """Expired session cookie results in empty session."""

    @pytest.mark.asyncio
    async def test_expired_session(self) -> None:
        max_age = 3600  # 1 hour
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET, max_age=max_age)

        @app.get("/check")
        async def handler(request: Any) -> dict[str, Any]:
            return {"session": request.scope["session"]}

        # Forge a cookie with a timestamp older than max_age
        old_timestamp = int(time.time()) - max_age - 100
        expired_cookie = _forge_cookie({"user": "alice"}, SECRET, timestamp=old_timestamp)

        resp = await _call_app(
            app, "GET", "/check", headers=[_make_cookie_header("session", expired_cookie)]
        )
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["session"] == {}

    @pytest.mark.asyncio
    async def test_not_yet_expired_session(self) -> None:
        max_age = 3600
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET, max_age=max_age)

        @app.get("/check")
        async def handler(request: Any) -> dict[str, Any]:
            return {"session": request.scope["session"]}

        # Forge a cookie with a recent timestamp (well within max_age)
        recent_timestamp = int(time.time()) - 60
        valid_cookie = _forge_cookie({"user": "alice"}, SECRET, timestamp=recent_timestamp)

        resp = await _call_app(
            app, "GET", "/check", headers=[_make_cookie_header("session", valid_cookie)]
        )
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["session"] == {"user": "alice"}


class TestNonHTTPPassthrough:
    """Non-HTTP scopes pass through without session handling."""

    @pytest.mark.asyncio
    async def test_websocket_passthrough(self) -> None:
        called = False

        async def inner_app(scope: Any, receive: Any, send: Any) -> None:
            nonlocal called
            called = True
            # Session should NOT be set for non-HTTP scopes
            assert "session" not in scope

        middleware = SessionMiddleware(inner_app, secret_key=SECRET)

        scope: dict[str, Any] = {"type": "websocket", "headers": []}

        async def receive() -> dict[str, Any]:
            return {}

        async def send(message: dict[str, Any]) -> None:
            pass

        await middleware(scope, receive, send)
        assert called


class TestMultipleSessionValues:
    """Session can store multiple key-value pairs."""

    @pytest.mark.asyncio
    async def test_multiple_values(self) -> None:
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        @app.get("/set")
        async def set_handler(request: Any) -> dict[str, str]:
            request.scope["session"]["user"] = "alice"
            request.scope["session"]["role"] = "admin"
            request.scope["session"]["theme"] = "dark"
            return {"status": "set"}

        @app.get("/get")
        async def get_handler(request: Any) -> dict[str, Any]:
            s: dict[str, Any] = request.scope["session"]
            return {"user": s.get("user"), "role": s.get("role"), "theme": s.get("theme")}

        resp1 = await _call_app(app, "GET", "/set")
        cookie = _extract_session_cookie(resp1)
        assert cookie is not None

        resp2 = await _call_app(
            app, "GET", "/get", headers=[_make_cookie_header("session", cookie)]
        )
        assert resp2["status"] == 200
        body = msgspec.json.decode(resp2["body"])
        assert body["user"] == "alice"
        assert body["role"] == "admin"
        assert body["theme"] == "dark"

    @pytest.mark.asyncio
    async def test_session_unchanged_no_set_cookie(self) -> None:
        """If session is not modified, no Set-Cookie header is sent."""
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        @app.get("/noop")
        async def handler(request: Any) -> dict[str, str]:
            # Read session but don't modify it
            _ = request.scope["session"]
            return {"status": "ok"}

        resp = await _call_app(app, "GET", "/noop")
        assert resp["status"] == 200
        assert b"set-cookie" not in resp["headers"]

    @pytest.mark.asyncio
    async def test_custom_cookie_name(self) -> None:
        """Custom session cookie name works correctly."""
        app = HawkAPI()
        app.add_middleware(SessionMiddleware, secret_key=SECRET, session_cookie="my_session")

        @app.get("/set")
        async def handler(request: Any) -> dict[str, str]:
            request.scope["session"]["key"] = "value"
            return {"status": "set"}

        resp = await _call_app(app, "GET", "/set")
        cookie = _extract_session_cookie(resp, cookie_name="my_session")
        assert cookie is not None
