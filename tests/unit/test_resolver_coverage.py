"""Tests for DI resolver edge cases — covers uncovered branches."""

from typing import Annotated, Any

import pytest

from hawkapi import HawkAPI
from hawkapi.di.depends import Depends
from hawkapi.validation.constraints import Cookie, Header, Path


class TestPathParamDefault:
    @pytest.mark.asyncio
    async def test_path_param_with_default(self):
        """Covers resolver lines 125-127: Path param with default."""
        app = HawkAPI(openapi_url=None)

        @app.get("/items/{item_id:int}")
        async def get_item(item_id: Annotated[int, Path(default=42)]) -> dict[str, Any]:
            return {"id": item_id}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/items/99",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200


class TestHeaderParamDefault:
    @pytest.mark.asyncio
    async def test_header_with_param_default(self):
        """Covers resolver lines 146-147: Header with param.default fallback."""
        app = HawkAPI(openapi_url=None)

        @app.get("/test")
        async def handler(x_custom: Annotated[str, Header()] = "fallback") -> dict[str, Any]:
            return {"value": x_custom}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200


class TestCookieParamDefault:
    @pytest.mark.asyncio
    async def test_cookie_with_param_default(self):
        """Covers resolver lines 155-156: Cookie with param.default fallback."""
        app = HawkAPI(openapi_url=None)

        @app.get("/test")
        async def handler(session: Annotated[str, Cookie()] = "none") -> dict[str, Any]:
            return {"session": session}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200


class TestContainerResolution:
    @pytest.mark.asyncio
    async def test_depends_resolved_from_container(self):
        """Covers resolver lines 171-173: Depends resolved from container."""
        app = HawkAPI(openapi_url=None)

        class DBService:
            pass

        db = DBService()
        app.container.singleton(DBService, factory=lambda: db)

        @app.get("/test")
        async def handler(svc: Annotated[DBService, Depends()]) -> dict[str, Any]:
            return {"ok": True}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200


class TestAutoResolveFromContainer:
    @pytest.mark.asyncio
    async def test_auto_resolve_by_type(self):
        """Covers resolver line 218: auto-resolve from container without scope."""
        app = HawkAPI(openapi_url=None)

        class Config:
            val = 42

        cfg = Config()
        app.container.singleton(Config, factory=lambda: cfg)

        @app.get("/test")
        async def handler(config: Config) -> dict[str, Any]:
            return {"val": config.val}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200


class TestBareQueryFallback:
    @pytest.mark.asyncio
    async def test_unannotated_query_param(self):
        """Covers resolver lines 228-230: bare query param coercion."""
        app = HawkAPI(openapi_url=None)

        @app.get("/search")
        async def handler(q: str) -> dict[str, Any]:
            return {"q": q}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "query_string": b"q=hello",
            "headers": [],
            "root_path": "",
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200
