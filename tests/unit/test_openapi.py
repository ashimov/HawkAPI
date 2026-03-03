"""Tests for OpenAPI schema generation."""

from typing import Annotated

import msgspec
import pytest

from hawkapi import HawkAPI
from hawkapi.openapi.inspector import struct_to_schema, type_to_schema
from hawkapi.openapi.schema import generate_openapi


# Module-level Struct for request body test (get_type_hints needs resolvable names)
class _CreateItem(msgspec.Struct):
    name: str
    price: float


class TestTypeToSchema:
    def test_str(self):
        assert type_to_schema(str) == {"type": "string"}

    def test_int(self):
        assert type_to_schema(int) == {"type": "integer"}

    def test_float(self):
        assert type_to_schema(float) == {"type": "number"}

    def test_bool(self):
        assert type_to_schema(bool) == {"type": "boolean"}

    def test_list_of_str(self):
        assert type_to_schema(list[str]) == {"type": "array", "items": {"type": "string"}}

    def test_dict_str_int(self):
        schema = type_to_schema(dict[str, int])
        assert schema["type"] == "object"
        assert schema["additionalProperties"] == {"type": "integer"}

    def test_optional_int(self):
        schema = type_to_schema(int | None)
        assert schema == {"anyOf": [{"type": "integer"}, {"type": "null"}]}

    def test_annotated_with_meta(self):
        tp = Annotated[int, msgspec.Meta(ge=0, le=100)]
        schema = type_to_schema(tp)
        assert schema["type"] == "integer"
        assert schema["minimum"] == 0
        assert schema["maximum"] == 100


class TestStructToSchema:
    def test_simple_struct(self):
        class User(msgspec.Struct):
            name: str
            age: int

        schema = struct_to_schema(User)
        assert schema["type"] == "object"
        assert schema["title"] == "User"
        assert "name" in schema["properties"]
        assert "age" in schema["properties"]
        assert set(schema["required"]) == {"name", "age"}

    def test_optional_field(self):
        class Item(msgspec.Struct):
            name: str
            description: str | None = None

        schema = struct_to_schema(Item)
        assert "name" in schema["required"]
        assert "description" not in schema.get("required", [])

    def test_constrained_field(self):
        class Product(msgspec.Struct):
            price: Annotated[float, msgspec.Meta(ge=0)]

        schema = struct_to_schema(Product)
        price_schema = schema["properties"]["price"]
        assert price_schema["type"] == "number"
        assert price_schema["minimum"] == 0


class TestGenerateOpenAPI:
    def test_basic_spec(self):
        app = HawkAPI(title="TestAPI", version="1.0.0", openapi_url=None)

        @app.get("/items")
        async def list_items() -> list[dict]:
            return []

        spec = generate_openapi(
            app._collect_routes(),
            title="TestAPI",
            version="1.0.0",
        )
        assert spec["openapi"] == "3.1.0"
        assert spec["info"]["title"] == "TestAPI"
        assert spec["info"]["version"] == "1.0.0"
        assert "/items" in spec["paths"]
        assert "get" in spec["paths"]["/items"]

    def test_path_params(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/users/{user_id:int}")
        async def get_user(user_id: int) -> dict:
            return {}

        spec = generate_openapi(app._collect_routes())
        path = spec["paths"]["/users/{user_id}"]
        params = path["get"]["parameters"]
        assert any(p["name"] == "user_id" and p["in"] == "path" for p in params)

    def test_request_body(self):
        app = HawkAPI(openapi_url=None)

        @app.post("/items")
        async def create_item(body: _CreateItem) -> dict:
            return {}

        spec = generate_openapi(app._collect_routes())
        op = spec["paths"]["/items"]["post"]
        assert "requestBody" in op
        assert "application/json" in op["requestBody"]["content"]
        assert "_CreateItem" in spec.get("components", {}).get("schemas", {})

    def test_tags_collected(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/a", tags=["alpha"])
        async def a():
            return {}

        @app.get("/b", tags=["beta"])
        async def b():
            return {}

        spec = generate_openapi(app._collect_routes())
        tag_names = {t["name"] for t in spec.get("tags", [])}
        assert "alpha" in tag_names
        assert "beta" in tag_names

    def test_head_excluded(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/test")
        async def handler():
            return {}

        spec = generate_openapi(app._collect_routes())
        assert "head" not in spec["paths"]["/test"]

    def test_include_in_schema_false(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/public")
        async def public():
            return {}

        @app.get("/internal", include_in_schema=False)
        async def internal():
            return {}

        spec = generate_openapi(app._collect_routes())
        assert "/public" in spec["paths"]
        assert "/internal" not in spec["paths"]

    def test_description_from_docstring(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/test")
        async def handler():
            """This is a test endpoint."""
            return {}

        spec = generate_openapi(app._collect_routes())
        op = spec["paths"]["/test"]["get"]
        assert op.get("description") == "This is a test endpoint."


class TestOpenAPIRoutes:
    @pytest.mark.asyncio
    async def test_openapi_json_served(self):
        app = HawkAPI(title="TestApp")

        @app.get("/hello")
        async def hello():
            return {"msg": "hi"}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/openapi.json",
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
        body = msgspec.json.decode(sent[1]["body"])
        assert body["info"]["title"] == "TestApp"
        assert "/hello" in body["paths"]
        # Doc routes should NOT appear in schema
        assert "/docs" not in body["paths"]
        assert "/openapi.json" not in body["paths"]

    @pytest.mark.asyncio
    async def test_docs_returns_html(self):
        app = HawkAPI()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/docs",
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
        headers = dict(sent[0].get("headers", []))
        assert b"text/html" in headers.get(b"content-type", b"")

    @pytest.mark.asyncio
    async def test_scalar_returns_html(self):
        app = HawkAPI()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/scalar",
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
    async def test_docs_disabled(self):
        app = HawkAPI(docs_url=None, redoc_url=None, scalar_url=None, openapi_url=None)

        @app.get("/hello")
        async def hello():
            return {}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/docs",
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
        assert sent[0]["status"] == 404
