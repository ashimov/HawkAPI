"""Tests for response_model parameter."""

import msgspec

from hawkapi import HawkAPI, Response
from hawkapi.testing import TestClient


class UserOut(msgspec.Struct):
    id: int
    name: str


class UserFull(msgspec.Struct):
    id: int
    name: str
    email: str
    password_hash: str


def test_response_model_filters_dict():
    """response_model drops extra fields from a dict return."""
    app = HawkAPI(openapi_url=None)

    @app.get("/user", response_model=UserOut)
    async def get_user():
        return {"id": 1, "name": "Alice", "email": "a@b.com", "password_hash": "secret"}

    client = TestClient(app)
    resp = client.get("/user")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"id": 1, "name": "Alice"}
    assert "password_hash" not in data
    assert "email" not in data


def test_response_model_filters_struct():
    """response_model filters a Struct to a smaller Struct."""
    app = HawkAPI(openapi_url=None)

    @app.get("/user", response_model=UserOut)
    async def get_user():
        return UserFull(id=1, name="Alice", email="a@b.com", password_hash="xxx")

    client = TestClient(app)
    resp = client.get("/user")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"id": 1, "name": "Alice"}


def test_response_model_none_passthrough():
    """When response_model is None, no filtering occurs."""
    app = HawkAPI(openapi_url=None)

    @app.get("/user")
    async def get_user():
        return {"id": 1, "name": "Alice", "extra": "data"}

    client = TestClient(app)
    resp = client.get("/user")
    data = resp.json()
    assert "extra" in data


def test_response_model_already_correct_type():
    """If result is already the response_model type, pass through."""
    app = HawkAPI(openapi_url=None)

    @app.get("/user", response_model=UserOut)
    async def get_user():
        return UserOut(id=1, name="Alice")

    client = TestClient(app)
    resp = client.get("/user")
    assert resp.json() == {"id": 1, "name": "Alice"}


def test_response_model_in_openapi():
    """OpenAPI schema uses response_model instead of return type."""
    app = HawkAPI(openapi_url=None)

    @app.get("/user", response_model=UserOut)
    async def get_user() -> dict:
        return {"id": 1, "name": "Alice"}

    spec = app.openapi()
    resp_schema = spec["paths"]["/user"]["get"]["responses"]["200"]
    assert "content" in resp_schema
    schema_ref = resp_schema["content"]["application/json"]["schema"]
    assert "$ref" in schema_ref
    assert "UserOut" in schema_ref["$ref"]


def test_response_model_does_not_affect_raw_response():
    """Response objects bypass response_model."""
    app = HawkAPI(openapi_url=None)

    @app.get("/custom", response_model=UserOut)
    async def custom():
        return Response(content=b"custom", status_code=200, content_type="text/plain")

    client = TestClient(app)
    resp = client.get("/custom")
    assert resp.body == b"custom"


def test_response_model_list():
    """response_model works with list types."""
    app = HawkAPI(openapi_url=None)

    @app.get("/users", response_model=list[UserOut])
    async def list_users():
        return [
            {"id": 1, "name": "Alice", "extra": "x"},
            {"id": 2, "name": "Bob", "extra": "y"},
        ]

    client = TestClient(app)
    resp = client.get("/users")
    data = resp.json()
    assert len(data) == 2
    assert data[0] == {"id": 1, "name": "Alice"}
    assert "extra" not in data[0]
