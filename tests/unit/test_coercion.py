"""Tests for safe query parameter coercion."""

import pytest

from hawkapi.di.resolver import _coerce_value
from hawkapi.validation.errors import RequestValidationError


def test_coerce_int_valid():
    assert _coerce_value("42", int) == 42


def test_coerce_int_invalid():
    with pytest.raises(RequestValidationError) as exc_info:
        _coerce_value("abc", int)
    assert exc_info.value.errors[0].field == "query"
    assert "integer" in exc_info.value.errors[0].message.lower()


def test_coerce_float_valid():
    assert _coerce_value("3.14", float) == 3.14


def test_coerce_float_invalid():
    with pytest.raises(RequestValidationError) as exc_info:
        _coerce_value("notanumber", float)
    assert "number" in exc_info.value.errors[0].message.lower()


def test_coerce_bool_true():
    assert _coerce_value("true", bool) is True
    assert _coerce_value("1", bool) is True
    assert _coerce_value("yes", bool) is True
    assert _coerce_value("TRUE", bool) is True


def test_coerce_bool_false():
    assert _coerce_value("false", bool) is False
    assert _coerce_value("0", bool) is False
    assert _coerce_value("no", bool) is False


def test_coerce_string():
    assert _coerce_value("hello", str) == "hello"


def test_coerce_int_empty_string():
    with pytest.raises(RequestValidationError):
        _coerce_value("", int)


def test_coerce_float_empty_string():
    with pytest.raises(RequestValidationError):
        _coerce_value("", float)
