"""Tests for class-based controllers."""

import pytest

from hawkapi import HawkAPI
from hawkapi.routing.controllers import Controller, delete, get, post


class TestControllerRouteCollection:
    def test_collects_decorated_methods(self):
        class ItemController(Controller):
            prefix = "/items"
            tags = ["items"]

            @get("/")
            async def list_items(self):
                return []

            @post("/")
            async def create_item(self):
                return {}

        routes = ItemController.collect_routes()
        assert len(routes) == 2
        paths = {info.path for info, _ in routes}
        assert "/" in paths

    def test_prefix_and_tags(self):
        class UserController(Controller):
            prefix = "/users"
            tags = ["users"]

            @get("/{user_id:int}")
            async def get_user(self, user_id: int):
                return {}

        routes = UserController.collect_routes()
        assert len(routes) == 1
        info, _ = routes[0]
        assert info.path == "/{user_id:int}"


class TestControllerIntegration:
    @pytest.mark.asyncio
    async def test_include_controller(self):
        app = HawkAPI(openapi_url=None)

        class HealthController(Controller):
            prefix = "/health"
            tags = ["health"]

            @get("/")
            async def check(self):
                return {"status": "ok"}

        app.include_controller(HealthController)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health/",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_controller_multiple_methods(self):
        app = HawkAPI(openapi_url=None)
        log = []

        class CrudController(Controller):
            prefix = "/things"

            @get("/")
            async def list_things(self):
                log.append("list")
                return []

            @post("/")
            async def create_thing(self):
                log.append("create")
                return {"id": 1}

            @delete("/{thing_id:int}")
            async def delete_thing(self, thing_id: int):
                log.append(f"delete-{thing_id}")
                return None

        app.include_controller(CrudController)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        # Test GET
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/things/",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent = []

        async def send(msg):
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 200
        assert "list" in log

        # Test POST
        scope["method"] = "POST"
        sent.clear()
        await app(scope, receive, send)
        assert sent[0]["status"] == 201
        assert "create" in log

    def test_non_controller_raises(self):
        app = HawkAPI(openapi_url=None)
        with pytest.raises(TypeError, match="not a Controller subclass"):
            app.include_controller(dict)
