"""Tests for auto-inference of ``response_model`` from return annotations.

See docs/plans/2026-04-18-tier3-typed-routes-design.md.
"""

from __future__ import annotations

from typing import Any

import msgspec
import pytest

from hawkapi import HawkAPI, JSONResponse
from hawkapi.testing import TestClient


class _Item(msgspec.Struct):
    id: int
    name: str


def test_annotation_msgspec_struct_is_used() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/item")
    async def h() -> _Item:
        return _Item(id=1, name="A")

    route = next(r for r in app.routes if r.path == "/item")
    assert route.response_model is _Item


def test_annotation_list_of_struct_is_used() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/items")
    async def h() -> list[_Item]:
        return [_Item(id=1, name="A")]

    route = next(r for r in app.routes if r.path == "/items")
    assert route.response_model == list[_Item]


def test_explicit_response_model_wins() -> None:
    class _Other(msgspec.Struct):
        x: int

    app = HawkAPI(openapi_url=None)

    @app.get("/x", response_model=_Other)
    async def h() -> _Item:
        return _Item(id=1, name="A")

    route = next(r for r in app.routes if r.path == "/x")
    assert route.response_model is _Other


def test_no_return_annotation_no_inference() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/none")
    async def h():  # no annotation
        return {"ok": True}

    route = next(r for r in app.routes if r.path == "/none")
    assert route.response_model is None


def test_none_annotation_no_inference() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/void")
    async def h() -> None:
        return None

    route = next(r for r in app.routes if r.path == "/void")
    assert route.response_model is None


def test_response_subclass_no_inference() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/raw")
    async def h() -> JSONResponse:
        return JSONResponse({"ok": True})

    route = next(r for r in app.routes if r.path == "/raw")
    assert route.response_model is None


def test_primitive_return_no_inference() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/str")
    async def h1() -> str:
        return "hi"

    @app.get("/int")
    async def h2() -> int:
        return 42

    @app.get("/bool")
    async def h3() -> bool:
        return True

    for path in ("/str", "/int", "/bool"):
        route = next(r for r in app.routes if r.path == path)
        assert route.response_model is None, path


def test_bare_container_no_inference() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/l")
    async def h1() -> list:
        return []

    @app.get("/d")
    async def h2() -> dict:
        return {}

    for path in ("/l", "/d"):
        route = next(r for r in app.routes if r.path == path)
        assert route.response_model is None, path


def test_any_annotation_no_inference() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/any")
    async def h() -> Any:
        return {"ok": True}

    route = next(r for r in app.routes if r.path == "/any")
    assert route.response_model is None


def test_optional_of_struct_is_used() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/opt")
    async def h() -> _Item | None:
        return _Item(id=1, name="A")

    route = next(r for r in app.routes if r.path == "/opt")
    # Union types are parameterized — passed through as-is.
    assert route.response_model is not None
    assert route.response_model == (_Item | None)


def test_integration_inferred_response_filters_to_schema() -> None:
    app = HawkAPI(openapi_url=None)

    @app.get("/u")
    async def h() -> _Item:
        # Return a dict with extra fields; response_model coercion drops them.
        return {"id": 1, "name": "A", "extra": "dropped"}

    resp = TestClient(app).get("/u")
    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "name": "A"}


def test_pydantic_model_annotation_is_used() -> None:
    pydantic = pytest.importorskip("pydantic")

    class _PItem(pydantic.BaseModel):
        id: int
        name: str

    app = HawkAPI(openapi_url=None)

    @app.get("/p")
    async def h() -> _PItem:
        return _PItem(id=1, name="A")

    route = next(r for r in app.routes if r.path == "/p")
    assert route.response_model is _PItem
