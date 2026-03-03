"""Integration tests for production hardening features."""

import pytest

from hawkapi import BackgroundTasks, HawkAPI, HTTPException, PlainTextResponse
from hawkapi.testing import TestClient


@pytest.fixture
def app():
    return HawkAPI(openapi_url=None, debug=True)


# --- HTTPException ---


class TestHTTPExceptionIntegration:
    def test_raise_404(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/item")
        async def get_item():
            raise HTTPException(404, detail="Item not found")

        client = TestClient(app)
        resp = client.get("/item")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Item not found"

    def test_raise_with_headers(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/auth")
        async def auth():
            raise HTTPException(
                401,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        client = TestClient(app)
        resp = client.get("/auth")
        assert resp.status_code == 401


# --- BackgroundTasks ---


class TestBackgroundTasksIntegration:
    def test_background_tasks_run_after_response(self):
        app = HawkAPI(openapi_url=None)
        results = []

        @app.post("/notify")
        async def notify(tasks: BackgroundTasks):
            tasks.add_task(lambda: results.append("done"))
            return {"status": "queued"}

        client = TestClient(app)
        resp = client.post("/notify")
        assert resp.status_code == 201
        assert resp.json() == {"status": "queued"}
        assert results == ["done"]


# --- Body size limits ---


class TestBodyLimits:
    def test_body_within_limit(self):
        app = HawkAPI(openapi_url=None, max_body_size=1024)

        import msgspec

        class Item(msgspec.Struct):
            name: str

        @app.post("/items")
        async def create(body: Item):
            return {"name": body.name}

        client = TestClient(app)
        resp = client.post("/items", json={"name": "test"})
        assert resp.status_code == 201

    def test_body_exceeds_limit(self):
        app = HawkAPI(openapi_url=None, max_body_size=10)

        import msgspec

        class Item(msgspec.Struct):
            name: str

        @app.post("/items")
        async def create(body: Item):
            return {"name": body.name}

        client = TestClient(app)
        resp = client.post("/items", json={"name": "a very long name that exceeds"})
        assert resp.status_code == 413


# --- Query coercion ---


class TestQueryCoercion:
    def test_invalid_int_returns_400(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/users/{user_id:int}")
        async def get_user(user_id: int, page: int = 1):
            return {"id": user_id, "page": page}

        client = TestClient(app)
        resp = client.get("/users/42?page=abc")
        assert resp.status_code == 400


# --- PlainTextResponse ---


class TestPlainTextResponse:
    def test_plain_text(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/text")
        async def text():
            return PlainTextResponse("Hello, World!")

        client = TestClient(app)
        resp = client.get("/text")
        assert resp.status_code == 200
        assert resp.text == "Hello, World!"


# --- Deprecated routes ---


class TestDeprecatedRoutes:
    def test_deprecated_route_works(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/old", deprecated=True)
        async def old_endpoint():
            return {"deprecated": True}

        client = TestClient(app)
        resp = client.get("/old")
        assert resp.status_code == 200
        assert resp.json() == {"deprecated": True}

    def test_deprecated_in_routes(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/old", deprecated=True)
        async def old_endpoint():
            return {"deprecated": True}

        route = next(r for r in app.routes if r.path == "/old")
        assert route.deprecated is True
