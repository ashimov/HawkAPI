"""Tests for route-level and router-level ``dependencies=[Depends(...)]``.

Covers DX Gap #2 from the 2026-04-18 FastAPI parity audit. Side-effect
dependencies run before the handler; their return values are discarded.
``HTTPException`` raised inside a dependency short-circuits; other exceptions
propagate like any handler-raised error.
"""

from __future__ import annotations

from hawkapi import Depends, HawkAPI, HTTPException, Router
from hawkapi.testing import TestClient


def test_route_level_dependency_runs_before_handler() -> None:
    calls: list[str] = []

    def record_call() -> None:
        calls.append("dep")

    app = HawkAPI(openapi_url=None)

    @app.get("/x", dependencies=[Depends(record_call)])
    async def handler() -> dict:
        calls.append("handler")
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/x")
    assert resp.status_code == 200
    assert calls == ["dep", "handler"]


def test_router_level_dependency_applies_to_every_route() -> None:
    calls: list[str] = []

    def admin_gate() -> None:
        calls.append("admin_gate")

    admin = Router(prefix="/admin", dependencies=[Depends(admin_gate)])

    @admin.get("/a")
    async def a() -> dict:
        return {}

    @admin.get("/b")
    async def b() -> dict:
        return {}

    app = HawkAPI(openapi_url=None)
    app.include_router(admin)

    client = TestClient(app)
    client.get("/admin/a")
    client.get("/admin/b")
    assert calls == ["admin_gate", "admin_gate"]


def test_router_deps_run_before_route_deps() -> None:
    calls: list[str] = []

    def router_dep() -> None:
        calls.append("router")

    def route_dep() -> None:
        calls.append("route")

    admin = Router(prefix="/admin", dependencies=[Depends(router_dep)])

    @admin.get("/x", dependencies=[Depends(route_dep)])
    async def handler() -> dict:
        calls.append("handler")
        return {}

    app = HawkAPI(openapi_url=None)
    app.include_router(admin)

    client = TestClient(app)
    client.get("/admin/x")
    assert calls == ["router", "route", "handler"]


def test_http_exception_in_dependency_short_circuits() -> None:
    def require_auth() -> None:
        raise HTTPException(status_code=403, detail="forbidden")

    app = HawkAPI(openapi_url=None)

    @app.get("/protected", dependencies=[Depends(require_auth)])
    async def handler() -> dict:
        return {"secret": "never seen"}

    resp = TestClient(app).get("/protected")
    assert resp.status_code == 403
    body = resp.json()
    assert body["status"] == 403
    assert body["detail"] == "forbidden"


def test_sub_dependency_inside_side_effect_dep_resolves() -> None:
    def get_user_id() -> int:
        return 42

    seen: list[int] = []

    def require_user(user_id: int = Depends(get_user_id)) -> None:
        seen.append(user_id)

    app = HawkAPI(openapi_url=None)

    @app.get("/u", dependencies=[Depends(require_user)])
    async def handler() -> dict:
        return {}

    TestClient(app).get("/u")
    assert seen == [42]


def test_empty_dependencies_is_zero_overhead() -> None:
    """Baseline: no dependencies kwarg → behaviour unchanged."""
    app = HawkAPI(openapi_url=None)

    @app.get("/plain")
    async def handler() -> dict:
        return {"ok": True}

    resp = TestClient(app).get("/plain")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_generic_exception_in_dependency_returns_500() -> None:
    """A non-HTTPException error from a side-effect dep is caught by the
    framework's default error handler and surfaced as a 500 response
    (matching how handler-raised errors are reported)."""

    def broken() -> None:
        raise RuntimeError("boom")

    app = HawkAPI(openapi_url=None)

    @app.get("/broken", dependencies=[Depends(broken)])
    async def handler() -> dict:
        return {}

    resp = TestClient(app).get("/broken")
    assert resp.status_code == 500
