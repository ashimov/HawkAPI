"""Type introspection — convert Python/msgspec types to JSON Schema."""

from __future__ import annotations

import types
import uuid
from datetime import date, datetime
from typing import Any, Union, get_args, get_origin

import msgspec
import msgspec.inspect


def type_to_schema(tp: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema dict."""
    # Handle None / NoneType
    if tp is type(None):
        return {"type": "null"}

    # Handle basic types
    if tp is str:
        return {"type": "string"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is bytes:
        return {"type": "string", "format": "binary"}

    # Handle special types
    if tp is datetime:
        return {"type": "string", "format": "date-time"}
    if tp is date:
        return {"type": "string", "format": "date"}
    if tp is uuid.UUID:
        return {"type": "string", "format": "uuid"}

    # Handle Annotated
    origin = get_origin(tp)
    args = get_args(tp)

    if origin is not None and args:
        # Check for Annotated
        first_arg = args[0]
        has_meta = any(isinstance(a, msgspec.Meta) for a in args[1:]) if len(args) > 1 else False
        if has_meta and isinstance(first_arg, type):
            schema = type_to_schema(first_arg)
            # Apply msgspec.Meta constraints
            for arg in args[1:]:
                if isinstance(arg, msgspec.Meta):
                    if arg.ge is not None:
                        schema["minimum"] = arg.ge
                    if arg.le is not None:
                        schema["maximum"] = arg.le
                    if arg.gt is not None:
                        schema["exclusiveMinimum"] = arg.gt
                    if arg.lt is not None:
                        schema["exclusiveMaximum"] = arg.lt
                    if arg.min_length is not None:
                        schema["minLength"] = arg.min_length
                    if arg.max_length is not None:
                        schema["maxLength"] = arg.max_length
                    if arg.pattern is not None:
                        schema["pattern"] = arg.pattern
            return schema

    # Handle Union (including Optional)
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and len(args) == 2:
            # Optional[X] -> nullable
            schema = type_to_schema(non_none[0])
            return {"anyOf": [schema, {"type": "null"}]}
        return {"anyOf": [type_to_schema(a) for a in args]}

    # Handle Python 3.10+ X | Y syntax (types.UnionType)
    if isinstance(tp, types.UnionType):
        union_args = get_args(tp)
        non_none = [a for a in union_args if a is not type(None)]
        if len(non_none) == 1 and len(union_args) == 2:
            schema = type_to_schema(non_none[0])
            return {"anyOf": [schema, {"type": "null"}]}
        return {"anyOf": [type_to_schema(a) for a in union_args]}

    # Handle list
    if origin is list:
        if args:
            return {"type": "array", "items": type_to_schema(args[0])}
        return {"type": "array"}

    # Handle dict
    if origin is dict:
        schema: dict[str, Any] = {"type": "object"}
        if len(args) >= 2:
            schema["additionalProperties"] = type_to_schema(args[1])
        return schema

    # Handle msgspec Struct
    if isinstance(tp, type) and issubclass(tp, msgspec.Struct):
        return struct_to_schema(tp)

    # Fallback
    return {"type": "object"}


def struct_to_schema(struct_type: type[msgspec.Struct]) -> dict[str, Any]:
    """Convert a msgspec Struct to a JSON Schema dict."""
    info = msgspec.inspect.type_info(struct_type)
    if not isinstance(info, msgspec.inspect.StructType):
        return {"type": "object"}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for field in info.fields:
        field_schema = _field_type_to_schema(field.type)
        if field.encode_name != field.name:
            field_schema["title"] = field.name
        properties[field.encode_name] = field_schema

        if field.required:
            required.append(field.encode_name)

    schema: dict[str, Any] = {
        "type": "object",
        "title": struct_type.__name__,
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


def _field_type_to_schema(type_info: msgspec.inspect.Type) -> dict[str, Any]:
    """Convert a msgspec inspect Type to JSON Schema."""
    if isinstance(type_info, msgspec.inspect.StrType):
        schema: dict[str, Any] = {"type": "string"}
        if type_info.min_length is not None:
            schema["minLength"] = type_info.min_length
        if type_info.max_length is not None:
            schema["maxLength"] = type_info.max_length
        if type_info.pattern is not None:
            schema["pattern"] = type_info.pattern
        return schema

    if isinstance(type_info, msgspec.inspect.IntType):
        schema = {"type": "integer"}
        if type_info.ge is not None:
            schema["minimum"] = type_info.ge
        if type_info.le is not None:
            schema["maximum"] = type_info.le
        if type_info.gt is not None:
            schema["exclusiveMinimum"] = type_info.gt
        if type_info.lt is not None:
            schema["exclusiveMaximum"] = type_info.lt
        return schema

    if isinstance(type_info, msgspec.inspect.FloatType):
        schema = {"type": "number"}
        if type_info.ge is not None:
            schema["minimum"] = type_info.ge
        if type_info.le is not None:
            schema["maximum"] = type_info.le
        return schema

    if isinstance(type_info, msgspec.inspect.BoolType):
        return {"type": "boolean"}

    if isinstance(type_info, msgspec.inspect.BytesType):
        return {"type": "string", "format": "binary"}

    if isinstance(type_info, msgspec.inspect.DateTimeType):
        return {"type": "string", "format": "date-time"}

    if isinstance(type_info, msgspec.inspect.DateType):
        return {"type": "string", "format": "date"}

    if isinstance(type_info, msgspec.inspect.UUIDType):
        return {"type": "string", "format": "uuid"}

    if isinstance(type_info, msgspec.inspect.NoneType):
        return {"type": "null"}

    if isinstance(type_info, msgspec.inspect.ListType):
        return {"type": "array", "items": _field_type_to_schema(type_info.item_type)}

    if isinstance(type_info, msgspec.inspect.DictType):
        return {
            "type": "object",
            "additionalProperties": _field_type_to_schema(type_info.value_type),
        }

    if isinstance(type_info, msgspec.inspect.UnionType):
        types = type_info.types
        non_none = [t for t in types if not isinstance(t, msgspec.inspect.NoneType)]
        if len(non_none) == 1 and len(types) == 2:
            schema = _field_type_to_schema(non_none[0])
            return {"anyOf": [schema, {"type": "null"}]}
        return {"anyOf": [_field_type_to_schema(t) for t in types]}

    if isinstance(type_info, msgspec.inspect.StructType):
        return struct_to_schema(type_info.cls)

    if isinstance(type_info, msgspec.inspect.AnyType):
        return {}

    return {"type": "object"}
