"""Tests for declarative RBAC/permission system."""

import pytest

from hawkapi import HawkAPI
from hawkapi.exceptions import HTTPException
from hawkapi.requests.request import Request
from hawkapi.security.permissions import PermissionPolicy
from hawkapi.testing import TestClient


async def _admin_resolver(request: Request) -> set[str]:
    """Resolver that grants admin permissions based on header."""
    token = request.headers.get("x-role", "")
    if token == "admin":
        return {"admin:read", "admin:write", "user:read"}
    if token == "user":
        return {"user:read"}
    return set()


class TestPermissionPolicy:
    @pytest.fixture
    def policy(self):
        return PermissionPolicy(resolver=_admin_resolver)

    @pytest.fixture
    def any_policy(self):
        return PermissionPolicy(resolver=_admin_resolver, mode="any")


class TestPermissionPolicyModeAll:
    async def test_check_passes_with_all_permissions(self):
        policy = PermissionPolicy(resolver=_admin_resolver)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"x-role", b"admin")],
        }
        request = Request(scope, None)
        await policy.check(request, ["admin:read"])

    async def test_check_fails_with_missing_permission(self):
        policy = PermissionPolicy(resolver=_admin_resolver)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"x-role", b"user")],
        }
        request = Request(scope, None)
        with pytest.raises(HTTPException) as exc_info:
            await policy.check(request, ["admin:read"])
        assert exc_info.value.status_code == 403


class TestPermissionPolicyModeAny:
    async def test_any_passes_with_one_matching(self):
        policy = PermissionPolicy(resolver=_admin_resolver, mode="any")
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"x-role", b"user")],
        }
        request = Request(scope, None)
        await policy.check(request, ["user:read", "admin:write"])

    async def test_any_fails_with_no_matching(self):
        policy = PermissionPolicy(resolver=_admin_resolver, mode="any")
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [(b"x-role", b"user")],
        }
        request = Request(scope, None)
        with pytest.raises(HTTPException) as exc_info:
            await policy.check(request, ["admin:read", "admin:write"])
        assert exc_info.value.status_code == 403


class TestWebSocketPermissions:
    @pytest.mark.asyncio
    async def test_websocket_permissions_denied(self):
        app = HawkAPI(openapi_url=None)
        app.permission_policy = PermissionPolicy(resolver=_admin_resolver)

        @app.websocket("/ws", permissions=["admin:read"])
        async def ws_handler(ws):
            await ws.accept()

        sent: list[dict] = []

        async def receive():
            return {"type": "websocket.connect"}

        async def send(msg):
            sent.append(msg)

        scope = {
            "type": "websocket",
            "path": "/ws",
            "query_string": b"",
            "headers": [(b"x-role", b"user")],
        }
        await app(scope, receive, send)
        assert sent[0]["type"] == "websocket.close"
        assert sent[0]["code"] == 4003

    @pytest.mark.asyncio
    async def test_websocket_permissions_allowed(self):
        app = HawkAPI(openapi_url=None)
        app.permission_policy = PermissionPolicy(resolver=_admin_resolver)

        @app.websocket("/ws", permissions=["admin:read"])
        async def ws_handler(ws):
            await ws.accept()
            await ws.send_text("ok")
            await ws.close()

        messages = [
            {"type": "websocket.connect"},
        ]
        msg_iter = iter(messages)
        sent: list[dict] = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {
            "type": "websocket",
            "path": "/ws",
            "query_string": b"",
            "headers": [(b"x-role", b"admin")],
        }
        await app(scope, receive, send)
        assert sent[0]["type"] == "websocket.accept"

    @pytest.mark.asyncio
    async def test_websocket_no_permissions_skips_check(self):
        app = HawkAPI(openapi_url=None)
        app.permission_policy = PermissionPolicy(resolver=_admin_resolver)

        @app.websocket("/ws")
        async def ws_handler(ws):
            await ws.accept()
            await ws.send_text("open")
            await ws.close()

        messages = [
            {"type": "websocket.connect"},
        ]
        msg_iter = iter(messages)
        sent: list[dict] = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {
            "type": "websocket",
            "path": "/ws",
            "query_string": b"",
            "headers": [],
        }
        await app(scope, receive, send)
        assert sent[0]["type"] == "websocket.accept"


class TestPermissionIntegration:
    def test_route_with_permissions_enforced(self):
        app = HawkAPI()
        app.permission_policy = PermissionPolicy(resolver=_admin_resolver)

        @app.get("/admin", permissions=["admin:read"])
        async def admin_panel():
            return {"secret": "data"}

        client = TestClient(app)
        resp = client.get("/admin", headers={"x-role": "admin"})
        assert resp.status_code == 200

    def test_route_with_permissions_denied(self):
        app = HawkAPI()
        app.permission_policy = PermissionPolicy(resolver=_admin_resolver)

        @app.get("/admin", permissions=["admin:read"])
        async def admin_panel():
            return {"secret": "data"}

        client = TestClient(app)
        resp = client.get("/admin", headers={"x-role": "user"})
        assert resp.status_code == 403

    def test_route_without_permissions_not_checked(self):
        app = HawkAPI()
        app.permission_policy = PermissionPolicy(resolver=_admin_resolver)

        @app.get("/public")
        async def public():
            return {"data": "public"}

        client = TestClient(app)
        resp = client.get("/public")
        assert resp.status_code == 200
