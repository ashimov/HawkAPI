"""Tests for OpenAPI example support in parameter markers."""

from typing import Annotated

import msgspec

from hawkapi import HawkAPI
from hawkapi.openapi.schema import generate_openapi
from hawkapi.validation.constraints import Body, Header, Path, Query


class _CreateUser(msgspec.Struct):
    name: str
    email: str


class TestOpenAPIExamples:
    def test_query_example(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/search")
        async def search(q: Annotated[str, Query(example="python")]):
            return {"q": q}

        spec = generate_openapi(app.routes)
        param = spec["paths"]["/search"]["get"]["parameters"][0]
        assert param["example"] == "python"

    def test_path_example(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/users/{user_id:int}")
        async def get_user(user_id: Annotated[int, Path(example=42)]):
            return {"id": user_id}

        spec = generate_openapi(app.routes)
        param = spec["paths"]["/users/{user_id}"]["get"]["parameters"][0]
        assert param["example"] == 42

    def test_header_example(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/protected")
        async def protected(x_token: Annotated[str, Header(example="secret-token")]):
            return {"ok": True}

        spec = generate_openapi(app.routes)
        param = spec["paths"]["/protected"]["get"]["parameters"][0]
        assert param["example"] == "secret-token"

    def test_body_example(self):
        app = HawkAPI(openapi_url=None)

        @app.post("/users")
        async def create_user(
            body: Annotated[_CreateUser, Body(example={"name": "Alice", "email": "a@b.com"})],
        ):
            return {"name": body.name}

        spec = generate_openapi(app.routes)
        rb = spec["paths"]["/users"]["post"]["requestBody"]
        assert rb["content"]["application/json"]["example"] == {
            "name": "Alice",
            "email": "a@b.com",
        }

    def test_no_example_omits_key(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/plain")
        async def plain(q: Annotated[str, Query()]):
            return {"q": q}

        spec = generate_openapi(app.routes)
        param = spec["paths"]["/plain"]["get"]["parameters"][0]
        assert "example" not in param
