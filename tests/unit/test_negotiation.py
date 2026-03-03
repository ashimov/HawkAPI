"""Tests for content negotiation."""

from hawkapi.serialization.negotiation import (
    encode_for_content_type,
    negotiate_content_type,
)


class TestNegotiateContentType:
    def test_none_header(self):
        assert negotiate_content_type(None) == "application/json"

    def test_empty_header(self):
        assert negotiate_content_type("") == "application/json"

    def test_json_explicit(self):
        assert negotiate_content_type("application/json") == "application/json"

    def test_wildcard(self):
        assert negotiate_content_type("*/*") == "application/json"

    def test_quality_values(self):
        accept = "text/html;q=0.9, application/json;q=1.0"
        assert negotiate_content_type(accept) == "application/json"

    def test_unsupported_falls_back(self):
        accept = "text/xml"
        assert negotiate_content_type(accept) == "application/json"

    def test_multiple_with_wildcard(self):
        accept = "text/html, application/xml;q=0.9, */*;q=0.8"
        assert negotiate_content_type(accept) == "application/json"

    def test_json_preferred_over_wildcard(self):
        accept = "application/json;q=1.0, */*;q=0.5"
        assert negotiate_content_type(accept) == "application/json"

    def test_invalid_quality_defaults_to_1(self):
        accept = "application/json;q=invalid"
        assert negotiate_content_type(accept) == "application/json"

    def test_msgpack_in_registry(self):
        accept = "application/msgpack"
        assert negotiate_content_type(accept) == "application/msgpack"


class TestEncodeForContentType:
    def test_json_encoding(self):
        result = encode_for_content_type({"key": "value"}, "application/json")
        assert b'"key"' in result
        assert b'"value"' in result

    def test_unknown_type_falls_back_to_json(self):
        result = encode_for_content_type({"key": "value"}, "text/xml")
        assert b'"key"' in result

    def test_msgpack_falls_back_to_json(self):
        # msgpack encoder is None (placeholder), so falls back to JSON
        result = encode_for_content_type({"key": "value"}, "application/msgpack")
        assert b'"key"' in result

    def test_encodes_list(self):
        result = encode_for_content_type([1, 2, 3], "application/json")
        assert b"[1,2,3]" in result

    def test_encodes_nested(self):
        data = {"users": [{"name": "Alice"}]}
        result = encode_for_content_type(data, "application/json")
        assert b"Alice" in result
