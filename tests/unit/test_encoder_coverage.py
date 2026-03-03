"""Tests for serialization encoder edge cases."""

import datetime
import uuid

from hawkapi.serialization.encoder import _enc_hook, encode_response


def test_enc_hook_datetime():
    dt = datetime.datetime(2024, 1, 15, 12, 30, 0)
    assert _enc_hook(dt) == "2024-01-15T12:30:00"


def test_enc_hook_date():
    d = datetime.date(2024, 1, 15)
    assert _enc_hook(d) == "2024-01-15"


def test_enc_hook_uuid():
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert _enc_hook(u) == "12345678-1234-5678-1234-567812345678"


def test_enc_hook_set():
    result = _enc_hook({1, 2, 3})
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}


def test_enc_hook_frozenset():
    result = _enc_hook(frozenset([4, 5]))
    assert isinstance(result, list)
    assert set(result) == {4, 5}


def test_enc_hook_bytes():
    result = _enc_hook(b"hello")
    assert result == "aGVsbG8="


def test_enc_hook_unsupported_type():
    import pytest

    with pytest.raises(TypeError, match="Cannot serialize"):
        _enc_hook(object())


def test_encode_response_with_datetime():
    """Exercises the fallback encoder path."""
    data = {"created": datetime.datetime(2024, 1, 15, 12, 0)}
    result = encode_response(data)
    assert b"2024-01-15" in result
