"""Extra tests for OpenAPI schema generation — covering uncovered branches."""

from typing import Annotated

import msgspec

from hawkapi import HawkAPI, Header, Query
from hawkapi.openapi.schema import generate_openapi
from hawkapi.validation.constraints import Cookie


def _make_app_and_generate(*routes_setup):
    """Helper to create an app, add routes, and generate OpenAPI schema."""
    app = HawkAPI(openapi_url=None)
    for setup in routes_setup:
        setup(app)
    return generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )


def test_deprecated_in_openapi():
    app = HawkAPI(openapi_url=None)

    @app.get("/old", deprecated=True)
    async def old():
        return {}

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    assert spec["paths"]["/old"]["get"]["deprecated"] is True


def test_description_from_docstring():
    app = HawkAPI(openapi_url=None)

    @app.get("/doc")
    async def documented():
        """This is a documented endpoint."""
        return {}

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    assert "documented endpoint" in spec["paths"]["/doc"]["get"]["description"]


def test_query_param_with_marker():
    app = HawkAPI(openapi_url=None)

    @app.get("/search")
    async def search(
        q: Annotated[str, Query(description="Search term")] = "",
    ):
        return {}

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    params = spec["paths"]["/search"]["get"]["parameters"]
    assert any(p["name"] == "q" and p["in"] == "query" for p in params)


def test_header_param():
    app = HawkAPI(openapi_url=None)

    @app.get("/check")
    async def check(
        x_token: Annotated[str, Header(alias="x-token", description="Token")] = "",
    ):
        return {}

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    params = spec["paths"]["/check"]["get"]["parameters"]
    assert any(p["name"] == "x-token" and p["in"] == "header" for p in params)


def test_cookie_param():
    app = HawkAPI(openapi_url=None)

    @app.get("/session")
    async def session(
        sid: Annotated[str, Cookie(alias="session_id")] = "",
    ):
        return {}

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    params = spec["paths"]["/session"]["get"]["parameters"]
    assert any(p["name"] == "session_id" and p["in"] == "cookie" for p in params)


def test_body_param_struct():
    app = HawkAPI(openapi_url=None)

    class Item(msgspec.Struct):
        name: str

    @app.post("/items")
    async def create(body: Item):
        return {}

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    op = spec["paths"]["/items"]["post"]
    assert "requestBody" in op
    assert "$ref" in op["requestBody"]["content"]["application/json"]["schema"]
    assert "Item" in spec["components"]["schemas"]


def test_return_type_struct():
    app = HawkAPI(openapi_url=None)

    class UserResponse(msgspec.Struct):
        id: int
        name: str

    @app.get("/user")
    async def get_user() -> UserResponse:
        return UserResponse(id=1, name="Alice")

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    op = spec["paths"]["/user"]["get"]
    assert "$ref" in op["responses"]["200"]["content"]["application/json"]["schema"]


def test_path_conversion():
    app = HawkAPI(openapi_url=None)

    @app.get("/users/{user_id:int}")
    async def get_user(user_id: int):
        return {}

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    assert "/users/{user_id}" in spec["paths"]


def test_tags_collected():
    app = HawkAPI(openapi_url=None)

    @app.get("/items", tags=["items"])
    async def list_items():
        return []

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    assert any(t["name"] == "items" for t in spec["tags"])


def test_with_description():
    spec = generate_openapi([], title="API", version="1.0", description="My API")
    assert spec["info"]["description"] == "My API"


def test_implicit_query_param():
    app = HawkAPI(openapi_url=None)

    @app.get("/search")
    async def search(page: int = 1):
        return {}

    spec = generate_openapi(
        [r for r in app.routes if r.include_in_schema],
        title="Test",
        version="1.0",
    )
    params = spec["paths"]["/search"]["get"]["parameters"]
    assert any(p["name"] == "page" for p in params)
