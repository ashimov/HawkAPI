"""Tests for serialization encoder."""

import datetime
import uuid

import msgspec

from hawkapi.serialization.encoder import encode_response


class TestEncodeResponse:
    def test_dict(self):
        result = encode_response({"key": "value"})
        assert msgspec.json.decode(result) == {"key": "value"}

    def test_list(self):
        result = encode_response([1, 2, 3])
        assert msgspec.json.decode(result) == [1, 2, 3]

    def test_struct(self):
        class Item(msgspec.Struct):
            name: str
            price: float

        result = encode_response(Item(name="Widget", price=9.99))
        data = msgspec.json.decode(result)
        assert data == {"name": "Widget", "price": 9.99}

    def test_nested_struct(self):
        class Address(msgspec.Struct):
            city: str

        class User(msgspec.Struct):
            name: str
            address: Address

        user = User(name="Alice", address=Address(city="NYC"))
        result = encode_response(user)
        data = msgspec.json.decode(result)
        assert data == {"name": "Alice", "address": {"city": "NYC"}}

    def test_none(self):
        result = encode_response(None)
        assert msgspec.json.decode(result) is None

    def test_string(self):
        result = encode_response("hello")
        assert msgspec.json.decode(result) == "hello"

    def test_int(self):
        result = encode_response(42)
        assert msgspec.json.decode(result) == 42

    def test_datetime_fallback(self):
        dt = datetime.datetime(2024, 1, 15, 12, 30, 0)
        result = encode_response(dt)
        assert msgspec.json.decode(result) == "2024-01-15T12:30:00"

    def test_uuid_fallback(self):
        u = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        result = encode_response(u)
        assert msgspec.json.decode(result) == "550e8400-e29b-41d4-a716-446655440000"

    def test_set_fallback(self):
        result = encode_response({1, 2, 3})
        decoded = msgspec.json.decode(result)
        assert sorted(decoded) == [1, 2, 3]
