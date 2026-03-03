"""Tests for the built-in TestClient."""

import msgspec
import pytest

from hawkapi import HawkAPI, Response
from hawkapi.testing.client import TestClient, TestResponse


class TestTestClient:
    def test_get(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/hello")
        async def hello():
            return {"message": "world"}

        client = TestClient(app)
        resp = client.get("/hello")
        assert resp.status_code == 200
        assert resp.json() == {"message": "world"}

    def test_post_json(self):
        app = HawkAPI(openapi_url=None)

        class Item(msgspec.Struct):
            name: str

        @app.post("/items")
        async def create(body: Item):
            return {"name": body.name}

        client = TestClient(app)
        resp = client.post("/items", json={"name": "widget"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "widget"

    def test_put(self):
        app = HawkAPI(openapi_url=None)

        class Item(msgspec.Struct):
            name: str

        @app.put("/items/{item_id:int}")
        async def update(item_id: int, body: Item):
            return {"id": item_id, "name": body.name}

        client = TestClient(app)
        resp = client.put("/items/1", json={"name": "updated"})
        assert resp.status_code == 200
        assert resp.json() == {"id": 1, "name": "updated"}

    def test_delete(self):
        app = HawkAPI(openapi_url=None)

        @app.delete("/items/{item_id:int}")
        async def remove(item_id: int):
            return None

        client = TestClient(app)
        resp = client.delete("/items/1")
        assert resp.status_code == 204

    def test_query_params(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/search")
        async def search(q: str = "default"):
            return {"q": q}

        client = TestClient(app)
        resp = client.get("/search", params={"q": "hello"})
        assert resp.status_code == 200
        assert resp.json()["q"] == "hello"

    def test_custom_headers(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/check")
        async def check(request):
            token = request.headers.get("x-token")
            return {"token": token}

        client = TestClient(app)
        resp = client.get("/check", headers={"x-token": "abc123"})
        assert resp.status_code == 200
        assert resp.json()["token"] == "abc123"

    def test_head_returns_no_body(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/data")
        async def data():
            return {"value": 42}

        client = TestClient(app)
        resp = client.head("/data")
        assert resp.status_code == 200
        assert resp.body == b""

    def test_404_for_missing_route(self):
        app = HawkAPI(openapi_url=None)
        client = TestClient(app)
        resp = client.get("/nope")
        assert resp.status_code == 404

    def test_response_text(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/text")
        async def text():
            return Response(content=b"plain text", status_code=200, content_type="text/plain")

        client = TestClient(app)
        resp = client.get("/text")
        assert resp.text == "plain text"

    def test_response_headers(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/custom")
        async def custom():
            return Response(content=b"ok", status_code=200, headers={"x-custom": "value"})

        client = TestClient(app)
        resp = client.get("/custom")
        assert resp.headers.get("x-custom") == "value"

    def test_response_repr(self):
        resp = TestResponse(status_code=200, body=b"", headers=[])
        assert repr(resp) == "<TestResponse [200]>"


class TestTestClientAsync:
    @pytest.mark.asyncio
    async def test_async_get(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/hello")
        async def hello():
            return {"msg": "async"}

        client = TestClient(app)
        resp = await client.async_get("/hello")
        assert resp.status_code == 200
        assert resp.json()["msg"] == "async"

    @pytest.mark.asyncio
    async def test_async_post(self):
        app = HawkAPI(openapi_url=None)

        class Data(msgspec.Struct):
            value: int

        @app.post("/data")
        async def create(body: Data):
            return {"value": body.value}

        client = TestClient(app)
        resp = await client.async_post("/data", json={"value": 42})
        assert resp.status_code == 201
        assert resp.json()["value"] == 42
