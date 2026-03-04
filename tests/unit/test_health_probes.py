"""Tests for /readyz and /livez health probe endpoints."""

import msgspec.json

from hawkapi import HawkAPI

# --- Helpers ---


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


# =============================================================================
# /livez
# =============================================================================


class TestLivez:
    async def test_livez_returns_200_alive(self):
        """/livez returns 200 with {"status": "alive"}."""
        app = HawkAPI(openapi_url=None)
        resp = await _call_app(app, "GET", "/livez")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data == {"status": "alive"}

    async def test_livez_disabled_returns_404(self):
        """livez_url=None disables the /livez endpoint."""
        app = HawkAPI(openapi_url=None, livez_url=None)
        resp = await _call_app(app, "GET", "/livez")
        assert resp["status"] == 404


# =============================================================================
# /readyz
# =============================================================================


class TestReadyz:
    async def test_readyz_no_checks_returns_200_ready(self):
        """/readyz with no registered checks returns 200 "ready"."""
        app = HawkAPI(openapi_url=None)
        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data["status"] == "ready"
        assert data["checks"] == {}

    async def test_readyz_passing_check_returns_200(self):
        """/readyz with a passing check returns 200 with check details."""
        app = HawkAPI(openapi_url=None)

        @app.readiness_check("db")
        async def check_db():
            return True, "connected"

        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data["status"] == "ready"
        assert data["checks"]["db"] == {"ok": True, "detail": "connected"}

    async def test_readyz_failing_check_returns_503(self):
        """/readyz with a failing check returns 503."""
        app = HawkAPI(openapi_url=None)

        @app.readiness_check("cache")
        async def check_cache():
            return False, "connection refused"

        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 503
        data = msgspec.json.decode(resp["body"])
        assert data["status"] == "not_ready"
        assert data["checks"]["cache"] == {"ok": False, "detail": "connection refused"}

    async def test_readyz_disabled_returns_404(self):
        """readyz_url=None disables the /readyz endpoint."""
        app = HawkAPI(openapi_url=None, readyz_url=None)
        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 404

    async def test_readyz_mixed_checks_returns_503(self):
        """/readyz with mixed passing/failing checks returns 503."""
        app = HawkAPI(openapi_url=None)

        @app.readiness_check("db")
        async def check_db():
            return True, "connected"

        @app.readiness_check("cache")
        async def check_cache():
            return False, "timeout"

        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 503
        data = msgspec.json.decode(resp["body"])
        assert data["status"] == "not_ready"
        assert data["checks"]["db"] == {"ok": True, "detail": "connected"}
        assert data["checks"]["cache"] == {"ok": False, "detail": "timeout"}
