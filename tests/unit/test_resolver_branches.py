"""Tests for DI resolver — covering all parameter source branches."""

from typing import Annotated

import msgspec

from hawkapi import HawkAPI, Header, Query
from hawkapi.di import Container, Depends
from hawkapi.testing import TestClient
from hawkapi.validation.constraints import Cookie

# --- Query marker ---


def test_query_marker_with_alias():
    app = HawkAPI(openapi_url=None)

    @app.get("/search")
    async def search(q: Annotated[str, Query(alias="query")] = ""):
        return {"q": q}

    client = TestClient(app)
    resp = client.get("/search?query=hello")
    assert resp.json() == {"q": "hello"}


def test_query_marker_default():
    app = HawkAPI(openapi_url=None)

    @app.get("/page")
    async def page(p: Annotated[int, Query(default=1)]):
        return {"page": p}

    client = TestClient(app)
    resp = client.get("/page")
    assert resp.json() == {"page": 1}


def test_query_marker_none_uses_param_default():
    app = HawkAPI(openapi_url=None)

    @app.get("/items")
    async def items(limit: Annotated[int, Query()] = 10):
        return {"limit": limit}

    client = TestClient(app)
    resp = client.get("/items")
    assert resp.json() == {"limit": 10}


# --- Header marker ---


def test_header_marker():
    app = HawkAPI(openapi_url=None)

    @app.get("/check")
    async def check(x_token: Annotated[str, Header(alias="x-token")] = "none"):
        return {"token": x_token}

    client = TestClient(app)
    resp = client.get("/check", headers={"X-Token": "abc123"})
    assert resp.json() == {"token": "abc123"}


def test_header_marker_default():
    app = HawkAPI(openapi_url=None)

    @app.get("/check")
    async def check(auth: Annotated[str, Header(default="anonymous")]):
        return {"auth": auth}

    client = TestClient(app)
    resp = client.get("/check")
    assert resp.json() == {"auth": "anonymous"}


# --- Cookie marker ---


def test_cookie_marker():
    app = HawkAPI(openapi_url=None)

    @app.get("/session")
    async def session(session_id: Annotated[str, Cookie(alias="session_id")] = "none"):
        return {"session": session_id}

    client = TestClient(app)
    resp = client.get("/session", headers={"Cookie": "session_id=abc"})
    assert resp.json() == {"session": "abc"}


def test_cookie_marker_default():
    app = HawkAPI(openapi_url=None)

    @app.get("/theme")
    async def theme(color: Annotated[str, Cookie(default="dark")]):
        return {"color": color}

    client = TestClient(app)
    resp = client.get("/theme")
    assert resp.json() == {"color": "dark"}


# --- Depends marker ---


def test_depends_with_function():
    app = HawkAPI(openapi_url=None)

    def get_current_user():
        return {"name": "Alice"}

    @app.get("/me")
    async def me(user: Annotated[dict, Depends(get_current_user)]):
        return user

    client = TestClient(app)
    resp = client.get("/me")
    assert resp.json() == {"name": "Alice"}


def test_depends_async_function():
    app = HawkAPI(openapi_url=None)

    async def get_db():
        return "connection"

    @app.get("/db")
    async def db_check(db: Annotated[str, Depends(get_db)]):
        return {"db": db}

    client = TestClient(app)
    resp = client.get("/db")
    assert resp.json() == {"db": "connection"}


class DataStore:
    def __init__(self, items):
        self.items = items


def test_depends_from_container():
    container = Container()
    container.singleton(DataStore, factory=lambda: DataStore([1, 2, 3]))
    app = HawkAPI(openapi_url=None, container=container)

    @app.get("/items")
    async def items(data: DataStore):
        return {"items": data.items}

    client = TestClient(app)
    resp = client.get("/items")
    assert resp.json() == {"items": [1, 2, 3]}


def test_depends_with_default():
    app = HawkAPI(openapi_url=None)

    @app.get("/opt")
    async def opt(data: Annotated[str, Depends(name="missing")] = "fallback"):
        return {"data": data}

    client = TestClient(app)
    resp = client.get("/opt")
    assert resp.json() == {"data": "fallback"}


# --- Body from type inference ---


def test_body_struct_inferred():
    app = HawkAPI(openapi_url=None)

    class Item(msgspec.Struct):
        name: str

    @app.post("/items")
    async def create(body: Item):
        return {"name": body.name}

    client = TestClient(app)
    resp = client.post("/items", json={"name": "test"})
    assert resp.status_code == 201
    assert resp.json() == {"name": "test"}


def test_body_missing_raises_validation():
    app = HawkAPI(openapi_url=None)

    class Item(msgspec.Struct):
        name: str

    @app.post("/items")
    async def create(body: Item):
        return {"name": body.name}

    client = TestClient(app)
    resp = client.post("/items")
    assert resp.status_code == 400


# --- Request param ---


def test_request_param():
    app = HawkAPI(openapi_url=None)

    from hawkapi import Request

    @app.get("/info")
    async def info(request: Request):
        return {"path": request.path}

    client = TestClient(app)
    resp = client.get("/info")
    assert resp.json() == {"path": "/info"}


# --- Implicit query params ---


def test_implicit_query_with_default():
    app = HawkAPI(openapi_url=None)

    @app.get("/search")
    async def search(q: str = ""):
        return {"q": q}

    client = TestClient(app)
    resp = client.get("/search?q=test")
    assert resp.json() == {"q": "test"}


def test_implicit_query_uses_default():
    app = HawkAPI(openapi_url=None)

    @app.get("/search")
    async def search(q: str = "default"):
        return {"q": q}

    client = TestClient(app)
    resp = client.get("/search")
    assert resp.json() == {"q": "default"}
