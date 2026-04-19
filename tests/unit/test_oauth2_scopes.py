"""Tests for OAuth2 scopes support (DX Gap #4)."""

from __future__ import annotations

from hawkapi import Depends, HawkAPI, Security, SecurityScopes
from hawkapi.security import OAuth2PasswordBearer
from hawkapi.testing import TestClient


def test_oauth2_scopes_reflected_in_openapi() -> None:
    oauth2 = OAuth2PasswordBearer(
        token_url="/token",
        scopes={"read": "Read", "write": "Write"},
    )
    assert oauth2.openapi_scheme["flows"]["password"]["scopes"] == {
        "read": "Read",
        "write": "Write",
    }


def test_security_class_is_depends_subclass() -> None:
    from hawkapi import Depends as D

    sec = Security(lambda: None, scopes=["a", "b"])
    assert isinstance(sec, D)
    assert sec.scopes == ["a", "b"]


def test_security_scopes_default_empty() -> None:
    ss = SecurityScopes()
    assert ss.scopes == ()
    assert ss.scope_str == ""


def test_security_scopes_scope_str_joins_with_space() -> None:
    ss = SecurityScopes(scopes=("read", "write"))
    assert ss.scope_str == "read write"


def test_security_scopes_injected_into_callable() -> None:
    seen: list[SecurityScopes] = []

    def require(security_scopes: SecurityScopes) -> None:
        seen.append(security_scopes)

    app = HawkAPI(openapi_url=None)

    @app.get("/x", dependencies=[Security(require, scopes=["read"])])
    async def handler() -> dict:
        return {}

    TestClient(app).get("/x")
    assert len(seen) == 1
    assert seen[0].scopes == ("read",)


def test_multiple_security_aggregate_and_deduplicate() -> None:
    seen: list[SecurityScopes] = []

    def cb(security_scopes: SecurityScopes) -> None:
        seen.append(security_scopes)

    app = HawkAPI(openapi_url=None)

    @app.get(
        "/x",
        dependencies=[
            Security(cb, scopes=["read", "write"]),
            Security(cb, scopes=["write", "admin"]),
        ],
    )
    async def handler() -> dict:
        return {}

    TestClient(app).get("/x")
    # Both deps fire; each receives the full aggregated sorted scope tuple.
    assert seen[0].scopes == ("admin", "read", "write")
    assert seen[1].scopes == ("admin", "read", "write")


def test_scopes_reflected_in_operation_security() -> None:
    oauth2 = OAuth2PasswordBearer(token_url="/token", scopes={"read": ""})

    def current_user(security_scopes: SecurityScopes, token: str = Depends(oauth2)) -> str:
        return token

    app = HawkAPI(title="t", version="1")

    @app.get("/items", dependencies=[Security(current_user, scopes=["read"])])
    async def list_items(
        user: str = Depends(current_user),
    ) -> dict:
        return {}

    spec = TestClient(app).get("/openapi.json").json()
    # The /items route's operation.security should carry the required scopes.
    op = spec["paths"]["/items"]["get"]
    assert "security" in op
    # Some scheme mapping with ["read"] as the scope list.
    first = op["security"][0]
    assert list(first.values())[0] == ["read"]


def test_no_scopes_no_regression() -> None:
    oauth2 = OAuth2PasswordBearer(token_url="/token")

    def current_user(token: str = Depends(oauth2)) -> str:
        return token

    app = HawkAPI(openapi_url=None)

    @app.get("/me")
    async def me(user: str = Depends(current_user)) -> dict:
        return {"user": user}

    # No auth header → 401 (auto_error default True).
    resp = TestClient(app).get("/me")
    assert resp.status_code == 401
