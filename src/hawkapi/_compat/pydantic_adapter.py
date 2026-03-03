"""Optional Pydantic v2 adapter."""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel as _BaseModel

    _has_pydantic = True
except ImportError:
    _has_pydantic = False
    _BaseModel: type[Any] = type  # type: ignore[no-redef]


def is_pydantic_model(tp: Any) -> bool:
    if not _has_pydantic:
        return False
    try:
        return isinstance(tp, type) and issubclass(tp, _BaseModel)
    except TypeError:
        return False


def decode_pydantic(model_class: type[Any], data: bytes) -> Any:
    if not _has_pydantic:
        raise RuntimeError("Pydantic is not installed")
    return model_class.model_validate_json(data)  # type: ignore[attr-defined]


def encode_pydantic(instance: Any) -> bytes:
    if not _has_pydantic:
        raise RuntimeError("Pydantic is not installed")
    result: str = instance.model_dump_json()
    return result.encode("utf-8")


def pydantic_to_json_schema(model_class: type[Any]) -> dict[str, Any]:
    if not _has_pydantic:
        raise RuntimeError("Pydantic is not installed")
    return model_class.model_json_schema()  # type: ignore[attr-defined]
