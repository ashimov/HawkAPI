"""Tests for sync (def) handler support."""

from hawkapi import HawkAPI, HTTPException
from hawkapi.testing import TestClient


def test_sync_handler_returns_json():
    app = HawkAPI(openapi_url=None)

    @app.get("/hello")
    def hello():
        return {"message": "hello"}

    client = TestClient(app)
    resp = client.get("/hello")
    assert resp.status_code == 200
    assert resp.json() == {"message": "hello"}


def test_sync_handler_with_path_param():
    app = HawkAPI(openapi_url=None)

    @app.get("/users/{user_id:int}")
    def get_user(user_id: int):
        return {"id": user_id}

    client = TestClient(app)
    resp = client.get("/users/42")
    assert resp.json() == {"id": 42}


def test_sync_handler_returns_none():
    app = HawkAPI(openapi_url=None)

    @app.get("/fire", status_code=200)
    def fire():
        return None

    client = TestClient(app)
    resp = client.get("/fire")
    assert resp.status_code == 204


def test_sync_handler_raises_http_exception():
    app = HawkAPI(openapi_url=None)

    @app.get("/fail")
    def fail():
        raise HTTPException(404, detail="Not found")

    client = TestClient(app)
    resp = client.get("/fail")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Not found"


def test_async_handler_still_works():
    """Regression: async handlers must continue to work."""
    app = HawkAPI(openapi_url=None)

    @app.get("/async")
    async def async_handler():
        return {"async": True}

    client = TestClient(app)
    resp = client.get("/async")
    assert resp.status_code == 200
    assert resp.json() == {"async": True}


def test_sync_handler_with_query_param():
    app = HawkAPI(openapi_url=None)

    @app.get("/search")
    def search(q: str = ""):
        return {"q": q}

    client = TestClient(app)
    resp = client.get("/search?q=test")
    assert resp.json() == {"q": "test"}
