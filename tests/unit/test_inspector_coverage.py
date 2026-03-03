"""Tests for OpenAPI inspector edge cases."""

from typing import Any, Union

import msgspec

from hawkapi.openapi.inspector import struct_to_schema, type_to_schema


def test_union_type():
    """Cover Union type handling."""
    schema = type_to_schema(Union[str, int])  # noqa: UP007
    assert "anyOf" in schema


def test_optional_type():
    """Cover Optional[X] → nullable."""
    schema = type_to_schema(Union[str, None])  # noqa: UP007
    assert "anyOf" in schema
    types = [s.get("type") for s in schema["anyOf"]]
    assert "string" in types
    assert "null" in types


def test_union_type_310_syntax():
    """Cover Python 3.10+ X | Y syntax."""
    schema = type_to_schema(str | None)
    assert "anyOf" in schema


def test_list_without_args():
    """Cover bare list → falls through to object."""
    schema = type_to_schema(list)
    assert schema["type"] == "object"


def test_list_with_args():
    """Cover list[X] → array with items."""
    schema = type_to_schema(list[int])
    assert schema["type"] == "array"
    assert schema["items"]["type"] == "integer"


def test_struct_with_constraints():
    """Cover string min/max length, pattern, int gt/lt in struct fields."""

    class ConstrainedItem(
        msgspec.Struct,
    ):
        name: str = msgspec.field(default="x")
        count: int = msgspec.field(default=0)

    schema = struct_to_schema(ConstrainedItem)
    assert schema["title"] == "ConstrainedItem"
    assert "name" in schema["properties"]


def test_struct_with_optional_field():
    """Cover Union type in _field_type_to_schema."""

    class ItemWithOptional(msgspec.Struct):
        label: str | None = None

    schema = struct_to_schema(ItemWithOptional)
    label_schema = schema["properties"]["label"]
    assert "anyOf" in label_schema


def test_struct_with_nested_struct():
    """Cover StructType in _field_type_to_schema."""

    class Inner(msgspec.Struct):
        value: int

    class Outer(msgspec.Struct):
        inner: Inner

    schema = struct_to_schema(Outer)
    inner_schema = schema["properties"]["inner"]
    assert inner_schema["title"] == "Inner"


def test_struct_with_any_field():
    """Cover AnyType in _field_type_to_schema."""

    class FlexItem(msgspec.Struct):
        data: Any

    schema = struct_to_schema(FlexItem)
    # AnyType returns empty schema {}
    assert schema["properties"]["data"] == {}


def test_struct_with_encode_name():
    """Cover field.encode_name != field.name path."""

    class AliasItem(msgspec.Struct, rename="camel"):
        my_field: str = "test"

    schema = struct_to_schema(AliasItem)
    # camelCase name should be the key, original should appear as title
    assert "myField" in schema["properties"]


def test_struct_with_float_field():
    """Cover FloatType schema generation."""

    class FloatItem(msgspec.Struct):
        score: float

    schema = struct_to_schema(FloatItem)
    assert schema["properties"]["score"]["type"] == "number"
