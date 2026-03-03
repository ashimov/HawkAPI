"""Tests for response encoder with enc_hook support."""

import datetime
import uuid

import pytest

from hawkapi.serialization.encoder import encode_response


def test_encode_dict():
    result = encode_response({"key": "value"})
    assert result == b'{"key":"value"}'


def test_encode_list():
    result = encode_response([1, 2, 3])
    assert result == b"[1,2,3]"


def test_encode_datetime():
    dt = datetime.datetime(2024, 1, 15, 12, 30, 0)
    result = encode_response({"ts": dt})
    assert b"2024-01-15T12:30:00" in result


def test_encode_date():
    d = datetime.date(2024, 1, 15)
    result = encode_response({"d": d})
    assert b"2024-01-15" in result


def test_encode_uuid():
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    result = encode_response({"id": u})
    assert b"12345678-1234-5678-1234-567812345678" in result


def test_encode_set():
    result = encode_response({"tags": {1, 2, 3}})
    assert b"[" in result  # converted to list


def test_encode_frozenset():
    result = encode_response({"items": frozenset(["a"])})
    assert b'"a"' in result


def test_encode_bytes():
    result = encode_response({"data": b"hello"})
    assert b"aGVsbG8=" in result  # base64 for "hello"


def test_encode_unsupported_type():
    class Custom:
        pass

    with pytest.raises(TypeError):
        encode_response({"obj": Custom()})
