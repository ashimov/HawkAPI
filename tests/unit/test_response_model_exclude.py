"""Tests for FastAPI-parity response_model_exclude_* flags (DX Gap #3)."""

from __future__ import annotations

import msgspec
import pytest
from msgspec import UNSET, UnsetType

from hawkapi import HawkAPI
from hawkapi.testing import TestClient


class _Profile(msgspec.Struct):
    bio: str | None = None
    age: int = 0


class _User(msgspec.Struct):
    id: int
    name: str
    email: str | None = None
    profile: _Profile = msgspec.field(default_factory=_Profile)


def _app() -> HawkAPI:
    return HawkAPI(openapi_url=None)


def test_baseline_no_flags_emits_all_fields() -> None:
    """With no flags set, serialization is unchanged."""
    app = _app()

    @app.get("/u", response_model=_User)
    async def h() -> dict:
        return {"id": 1, "name": "A", "email": None, "profile": {"bio": None, "age": 0}}

    resp = TestClient(app).get("/u")
    assert resp.status_code == 200
    assert resp.json() == {
        "id": 1,
        "name": "A",
        "email": None,
        "profile": {"bio": None, "age": 0},
    }


def test_exclude_none_drops_none_values_recursively() -> None:
    app = _app()

    @app.get("/u", response_model=_User, response_model_exclude_none=True)
    async def h() -> dict:
        return {"id": 1, "name": "A", "email": None, "profile": {"bio": None, "age": 5}}

    data = TestClient(app).get("/u").json()
    assert "email" not in data
    assert "bio" not in data["profile"]
    assert data == {"id": 1, "name": "A", "profile": {"age": 5}}


def test_exclude_defaults_drops_fields_equal_to_default_msgspec() -> None:
    app = _app()

    @app.get("/u", response_model=_User, response_model_exclude_defaults=True)
    async def h() -> _User:
        # `age` and `bio` left at defaults; `email` set explicitly to non-default.
        return _User(id=1, name="A", email="x@y.z")

    data = TestClient(app).get("/u").json()
    # Required fields always present; defaults (profile, which equals _Profile())
    # are dropped entirely — matching FastAPI/Pydantic's exclude_defaults semantics.
    assert data == {"id": 1, "name": "A", "email": "x@y.z"}


def test_exclude_unset_msgspec_with_unsettype() -> None:
    """msgspec users who declare UNSET-typed fields get exclude_unset semantics."""

    class Partial(msgspec.Struct):
        id: int
        name: str | UnsetType = UNSET
        email: str | UnsetType = UNSET

    app = _app()

    @app.get("/u", response_model=Partial, response_model_exclude_unset=True)
    async def h() -> Partial:
        return Partial(id=7, name="A")  # email left UNSET

    data = TestClient(app).get("/u").json()
    assert data == {"id": 7, "name": "A"}


def test_exclude_unset_msgspec_without_unsettype_is_noop() -> None:
    """Plain msgspec Structs don't track 'set vs default' — flag is a no-op."""
    app = _app()

    @app.get("/u", response_model=_User, response_model_exclude_unset=True)
    async def h() -> _User:
        return _User(id=1, name="A")

    data = TestClient(app).get("/u").json()
    # All fields emitted; nothing is "unset" by msgspec's definition.
    assert data["id"] == 1
    assert data["name"] == "A"
    assert "email" in data
    assert "profile" in data


def test_all_three_flags_combined() -> None:
    app = _app()

    @app.get(
        "/u",
        response_model=_User,
        response_model_exclude_none=True,
        response_model_exclude_defaults=True,
    )
    async def h() -> _User:
        return _User(id=1, name="A")

    data = TestClient(app).get("/u").json()
    # email is None (exclude_none) and profile is default (exclude_defaults).
    assert data == {"id": 1, "name": "A"}


def test_exclude_none_on_dict_return_without_response_model() -> None:
    """exclude_none applies even without response_model coercion (best-effort on plain dicts)."""
    app = _app()

    @app.get("/d", response_model_exclude_none=True)
    async def h() -> dict:
        return {"a": 1, "b": None, "nested": {"c": 2, "d": None}}

    data = TestClient(app).get("/d").json()
    assert data == {"a": 1, "nested": {"c": 2}}


def test_pydantic_path_uses_model_dump() -> None:
    pydantic = pytest.importorskip("pydantic")

    class User(pydantic.BaseModel):
        id: int
        name: str = "default"
        email: str | None = None

    app = _app()

    @app.get(
        "/u",
        response_model=User,
        response_model_exclude_defaults=True,
        response_model_exclude_none=True,
    )
    async def h() -> dict:
        return {"id": 1, "name": "default", "email": None}

    data = TestClient(app).get("/u").json()
    # name is at default → excluded; email is None → excluded.
    assert data == {"id": 1}
