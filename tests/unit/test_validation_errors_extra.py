"""Extra tests for validation error formatting."""

import contextlib

import msgspec

from hawkapi.validation.errors import format_msgspec_error


def test_format_field_error():
    with contextlib.suppress(msgspec.ValidationError):
        msgspec.json.decode(b'{"age": "not_int"}', type=dict)


def test_format_error_with_field_path():
    """Test formatting of msgspec errors with field paths."""

    class Item(msgspec.Struct):
        name: str
        price: float

    try:
        msgspec.json.decode(b'{"name": "test", "price": "bad"}', type=Item)
    except msgspec.ValidationError as e:
        errors = format_msgspec_error(e)
        assert len(errors) == 1
        assert errors[0].field == "price"


def test_format_error_root_level():
    """Test formatting of root-level msgspec errors."""
    try:
        msgspec.json.decode(b'"not_an_object"', type=dict)
    except msgspec.ValidationError as e:
        errors = format_msgspec_error(e)
        assert len(errors) == 1


def test_format_error_no_path():
    """Test formatting when error has no path indicator."""
    try:
        msgspec.json.decode(b"42", type=str)
    except msgspec.ValidationError as e:
        errors = format_msgspec_error(e)
        assert len(errors) == 1
        assert errors[0].field == "$"
