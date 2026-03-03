"""Tests for Pydantic v2 adapter."""

import pytest

from hawkapi._compat.pydantic_adapter import (
    decode_pydantic,
    encode_pydantic,
    is_pydantic_model,
    pydantic_to_json_schema,
)

pydantic = pytest.importorskip("pydantic")


class UserModel(pydantic.BaseModel):
    name: str
    age: int = 0


def test_is_pydantic_model_true():
    assert is_pydantic_model(UserModel) is True


def test_is_pydantic_model_false():
    assert is_pydantic_model(dict) is False
    assert is_pydantic_model(str) is False


def test_decode_pydantic():
    data = b'{"name": "Alice", "age": 30}'
    result = decode_pydantic(UserModel, data)
    assert isinstance(result, UserModel)
    assert result.name == "Alice"
    assert result.age == 30


def test_encode_pydantic():
    user = UserModel(name="Bob", age=25)
    result = encode_pydantic(user)
    assert b"Bob" in result
    assert b"25" in result


def test_pydantic_to_json_schema():
    schema = pydantic_to_json_schema(UserModel)
    assert "properties" in schema
    assert "name" in schema["properties"]
    assert "age" in schema["properties"]


def test_pydantic_body_in_handler():
    """Integration test: Pydantic model as request body."""
    from hawkapi import HawkAPI
    from hawkapi.testing import TestClient

    app = HawkAPI(openapi_url=None)

    @app.post("/users")
    async def create_user(body: UserModel):
        return {"name": body.name, "age": body.age}

    client = TestClient(app)
    resp = client.post("/users", json={"name": "Charlie", "age": 28})
    assert resp.status_code == 201
    assert resp.json() == {"name": "Charlie", "age": 28}
