"""Tests for OpenAPI type inspector."""

import datetime
import uuid
from typing import Annotated

import msgspec

from hawkapi.openapi.inspector import struct_to_schema, type_to_schema


def test_str():
    assert type_to_schema(str) == {"type": "string"}


def test_int():
    assert type_to_schema(int) == {"type": "integer"}


def test_float():
    assert type_to_schema(float) == {"type": "number"}


def test_bool():
    assert type_to_schema(bool) == {"type": "boolean"}


def test_bytes():
    assert type_to_schema(bytes) == {"type": "string", "format": "binary"}


def test_none():
    assert type_to_schema(type(None)) == {"type": "null"}


def test_datetime():
    assert type_to_schema(datetime.datetime) == {"type": "string", "format": "date-time"}


def test_date():
    assert type_to_schema(datetime.date) == {"type": "string", "format": "date"}


def test_uuid():
    assert type_to_schema(uuid.UUID) == {"type": "string", "format": "uuid"}


def test_list_of_str():
    assert type_to_schema(list[str]) == {"type": "array", "items": {"type": "string"}}


def test_list_bare():
    # Bare list without type params falls through to fallback
    assert type_to_schema(list) == {"type": "object"}


def test_dict_str_int():
    schema = type_to_schema(dict[str, int])
    assert schema["type"] == "object"
    assert schema["additionalProperties"] == {"type": "integer"}


def test_optional_str():
    schema = type_to_schema(str | None)
    assert schema == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_union_multiple():
    schema = type_to_schema(str | int | float)
    assert "anyOf" in schema
    assert len(schema["anyOf"]) == 3


def test_annotated_with_meta():
    schema = type_to_schema(Annotated[int, msgspec.Meta(ge=0, le=100)])
    assert schema["type"] == "integer"
    assert schema["minimum"] == 0
    assert schema["maximum"] == 100


def test_annotated_str_meta():
    schema = type_to_schema(Annotated[str, msgspec.Meta(min_length=1, max_length=50)])
    assert schema["minLength"] == 1
    assert schema["maxLength"] == 50


def test_annotated_str_pattern():
    schema = type_to_schema(Annotated[str, msgspec.Meta(pattern=r"^\w+$")])
    assert schema["pattern"] == r"^\w+$"


def test_annotated_gt_lt():
    schema = type_to_schema(Annotated[int, msgspec.Meta(gt=0, lt=10)])
    assert schema["exclusiveMinimum"] == 0
    assert schema["exclusiveMaximum"] == 10


def test_struct():
    class Item(msgspec.Struct):
        name: str
        price: float
        description: str = ""

    schema = struct_to_schema(Item)
    assert schema["type"] == "object"
    assert schema["title"] == "Item"
    assert "name" in schema["properties"]
    assert "price" in schema["properties"]
    assert "name" in schema["required"]
    assert "price" in schema["required"]
    assert "description" not in schema["required"]


def test_struct_with_optional_field():
    class User(msgspec.Struct):
        name: str
        email: str | None = None

    schema = struct_to_schema(User)
    assert "name" in schema["required"]
    assert "email" not in schema.get("required", [])


def test_struct_with_list_field():
    class Tags(msgspec.Struct):
        items: list[str]

    schema = struct_to_schema(Tags)
    items_schema = schema["properties"]["items"]
    assert items_schema["type"] == "array"
    assert items_schema["items"]["type"] == "string"


def test_struct_with_nested_struct():
    class Address(msgspec.Struct):
        city: str

    class Person(msgspec.Struct):
        name: str
        address: Address

    schema = struct_to_schema(Person)
    addr_schema = schema["properties"]["address"]
    assert addr_schema["type"] == "object"
    assert "city" in addr_schema["properties"]


def test_struct_with_constrained_field():
    class Bounded(msgspec.Struct):
        age: Annotated[int, msgspec.Meta(ge=0, le=150)]

    schema = struct_to_schema(Bounded)
    age = schema["properties"]["age"]
    assert age["type"] == "integer"
    assert age["minimum"] == 0
    assert age["maximum"] == 150


def test_struct_with_dict_field():
    class Meta(msgspec.Struct):
        data: dict[str, int]

    schema = struct_to_schema(Meta)
    data_schema = schema["properties"]["data"]
    assert data_schema["type"] == "object"


def test_struct_with_datetime_field():
    class Event(msgspec.Struct):
        at: datetime.datetime

    schema = struct_to_schema(Event)
    assert schema["properties"]["at"]["format"] == "date-time"


def test_struct_with_uuid_field():
    class Entity(msgspec.Struct):
        id: uuid.UUID

    schema = struct_to_schema(Entity)
    assert schema["properties"]["id"]["format"] == "uuid"


def test_struct_with_bool_field():
    class Flags(msgspec.Struct):
        active: bool

    schema = struct_to_schema(Flags)
    assert schema["properties"]["active"]["type"] == "boolean"


def test_struct_with_bytes_field():
    class Blob(msgspec.Struct):
        data: bytes

    schema = struct_to_schema(Blob)
    assert schema["properties"]["data"]["format"] == "binary"


def test_struct_with_date_field():
    class Birthday(msgspec.Struct):
        date: datetime.date

    schema = struct_to_schema(Birthday)
    assert schema["properties"]["date"]["format"] == "date"


def test_struct_with_none_field():
    class Nullable(msgspec.Struct):
        value: None

    schema = struct_to_schema(Nullable)
    assert schema["properties"]["value"]["type"] == "null"


def test_unknown_type_fallback():
    schema = type_to_schema(object)
    assert schema == {"type": "object"}
