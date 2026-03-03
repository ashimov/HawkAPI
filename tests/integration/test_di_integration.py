"""Integration tests for DI with routes."""

from typing import Annotated

import msgspec
import pytest

from hawkapi import Container, Depends, HawkAPI


class FakeDB:
    def __init__(self, url: str = "test://"):
        self.url = url
        self.queries: list[str] = []

    async def execute(self, query: str):
        self.queries.append(query)
        return {"result": query}


class FakeCache:
    def __init__(self, name: str = "default"):
        self.name = name
        self.data: dict = {}

    def get(self, key: str):
        return self.data.get(key)


async def _call_app(app, method, path, body=b"", headers=None):
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


class TestDIInRoutes:
    @pytest.mark.asyncio
    async def test_singleton_injection(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("production://"))

        app = HawkAPI(container=container)

        @app.get("/db-url")
        async def get_db_url(db: FakeDB):
            return {"url": db.url}

        resp = await _call_app(app, "GET", "/db-url")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data["url"] == "production://"

    @pytest.mark.asyncio
    async def test_scoped_injection(self):
        container = Container()
        call_count = 0

        def make_db():
            nonlocal call_count
            call_count += 1
            return FakeDB(f"scoped-{call_count}")

        container.scoped(FakeDB, factory=make_db)
        app = HawkAPI(container=container)

        @app.get("/db")
        async def get_db(db: FakeDB):
            return {"url": db.url}

        resp1 = await _call_app(app, "GET", "/db")
        resp2 = await _call_app(app, "GET", "/db")

        data1 = msgspec.json.decode(resp1["body"])
        data2 = msgspec.json.decode(resp2["body"])

        # Different instances for different requests (scoped)
        assert data1["url"] != data2["url"]

    @pytest.mark.asyncio
    async def test_named_dependency_injection(self):
        container = Container()
        container.singleton(FakeCache, factory=lambda: FakeCache("redis"), name="cache")
        container.singleton(FakeCache, factory=lambda: FakeCache("memcached"), name="sessions")

        app = HawkAPI(container=container)

        @app.get("/cache-info")
        async def get_cache_info(
            cache: Annotated[FakeCache, Depends(name="cache")],
            sessions: Annotated[FakeCache, Depends(name="sessions")],
        ):
            return {"cache": cache.name, "sessions": sessions.name}

        resp = await _call_app(app, "GET", "/cache-info")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data == {"cache": "redis", "sessions": "memcached"}

    @pytest.mark.asyncio
    async def test_function_depends(self):
        app = HawkAPI()

        async def get_current_user():
            return {"id": 1, "name": "Alice"}

        @app.get("/me")
        async def get_me(user: Annotated[dict, Depends(get_current_user)]):
            return user

        resp = await _call_app(app, "GET", "/me")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data == {"id": 1, "name": "Alice"}

    @pytest.mark.asyncio
    async def test_di_override_for_testing(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("production://"))

        app = HawkAPI(container=container)

        @app.get("/db-url")
        async def get_db_url(db: FakeDB):
            return {"url": db.url}

        # Test with production DB
        resp = await _call_app(app, "GET", "/db-url")
        data = msgspec.json.decode(resp["body"])
        assert data["url"] == "production://"

        # Override for testing
        with container.override(FakeDB, factory=lambda: FakeDB("test://")):
            resp = await _call_app(app, "GET", "/db-url")
            data = msgspec.json.decode(resp["body"])
            assert data["url"] == "test://"

        # Back to production after override exits
        resp = await _call_app(app, "GET", "/db-url")
        data = msgspec.json.decode(resp["body"])
        assert data["url"] == "production://"


class TestDIOutsideRoutes:
    @pytest.mark.asyncio
    async def test_standalone_scope(self):
        """DI works outside HTTP routes — unlike FastAPI."""
        container = Container()
        container.scoped(FakeDB, factory=lambda: FakeDB("background"))

        async with container.scope() as scope:
            db = await scope.resolve(FakeDB)
            assert db.url == "background"
            await db.execute("DELETE FROM expired")
            assert db.queries == ["DELETE FROM expired"]

    @pytest.mark.asyncio
    async def test_singleton_outside_routes(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("shared"))

        db = await container.resolve(FakeDB)
        assert db.url == "shared"
