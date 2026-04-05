"""Tests for MessagePack content negotiation and encoding."""

from __future__ import annotations

import datetime
import uuid

import msgspec

from hawkapi.serialization.encoder import encode_response_msgpack
from hawkapi.serialization.negotiation import encode_for_content_type, negotiate_content_type


class TestMsgpackNegotiation:
    def test_accept_msgpack(self):
        assert negotiate_content_type("application/msgpack") == "application/msgpack"

    def test_accept_x_msgpack(self):
        assert negotiate_content_type("application/x-msgpack") == "application/x-msgpack"

    def test_accept_json_still_works(self):
        assert negotiate_content_type("application/json") == "application/json"

    def test_msgpack_preferred_over_json(self):
        accept = "application/msgpack;q=1.0, application/json;q=0.9"
        assert negotiate_content_type(accept) == "application/msgpack"

    def test_json_preferred_over_msgpack(self):
        accept = "application/json;q=1.0, application/msgpack;q=0.5"
        assert negotiate_content_type(accept) == "application/json"

    def test_wildcard_falls_back_to_json(self):
        assert negotiate_content_type("*/*") == "application/json"

    def test_quality_parsing_with_spaces(self):
        accept = "application/msgpack ; q = 0.8 , application/json ; q = 1.0"
        assert negotiate_content_type(accept) == "application/json"

    def test_no_quality_defaults_to_1(self):
        accept = "application/msgpack, application/json;q=0.9"
        assert negotiate_content_type(accept) == "application/msgpack"


class TestEncodeResponseMsgpack:
    def test_encode_dict(self):
        data = {"key": "value", "num": 42}
        result = encode_response_msgpack(data)
        decoded = msgspec.msgpack.decode(result)
        assert decoded == data

    def test_encode_list(self):
        data = [1, 2, 3, "hello"]
        result = encode_response_msgpack(data)
        decoded = msgspec.msgpack.decode(result)
        assert decoded == data

    def test_encode_nested(self):
        data = {"users": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]}
        result = encode_response_msgpack(data)
        decoded = msgspec.msgpack.decode(result)
        assert decoded == data

    def test_round_trip_consistency(self):
        data = {"items": [1, "two", 3.0, True, None]}
        encoded = encode_response_msgpack(data)
        decoded = msgspec.msgpack.decode(encoded)
        assert decoded == data

    def test_encode_uuid(self):
        u = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = encode_response_msgpack({"id": u})
        decoded = msgspec.msgpack.decode(result)
        assert decoded["id"] == "12345678-1234-5678-1234-567812345678"

    def test_encode_datetime(self):
        dt = datetime.datetime(2024, 1, 15, 12, 30, 0)
        result = encode_response_msgpack({"ts": dt})
        decoded = msgspec.msgpack.decode(result)
        assert decoded["ts"] == "2024-01-15T12:30:00"

    def test_encode_set(self):
        result = encode_response_msgpack({"tags": {1, 2, 3}})
        decoded = msgspec.msgpack.decode(result)
        assert sorted(decoded["tags"]) == [1, 2, 3]

    def test_encode_bytes_natively(self):
        # msgpack handles bytes natively (unlike JSON which base64-encodes them)
        result = encode_response_msgpack({"data": b"hello"})
        decoded = msgspec.msgpack.decode(result)
        assert decoded["data"] == b"hello"


class TestEncodeForContentTypeMsgpack:
    def test_msgpack_content_type(self):
        data = {"key": "value"}
        result = encode_for_content_type(data, "application/msgpack")
        decoded = msgspec.msgpack.decode(result)
        assert decoded == data

    def test_x_msgpack_content_type(self):
        data = {"key": "value"}
        result = encode_for_content_type(data, "application/x-msgpack")
        decoded = msgspec.msgpack.decode(result)
        assert decoded == data

    def test_json_content_type_still_json(self):
        data = {"key": "value"}
        result = encode_for_content_type(data, "application/json")
        assert result == b'{"key":"value"}'

    def test_unknown_type_falls_back_to_json(self):
        data = {"key": "value"}
        result = encode_for_content_type(data, "text/xml")
        assert b'"key"' in result

    def test_msgpack_result_is_bytes(self):
        result = encode_for_content_type({"a": 1}, "application/msgpack")
        assert isinstance(result, bytes)
