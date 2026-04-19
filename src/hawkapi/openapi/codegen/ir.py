"""Language-agnostic intermediate representation for client SDK codegen."""

from __future__ import annotations

from dataclasses import dataclass, field  # noqa: F401 — field kept for subclassers
from typing import Any, Literal

_SENTINEL = object()


@dataclass(frozen=True, slots=True)
class FieldIR:
    """A single field on a struct schema."""

    name: str
    type_str: str
    required: bool
    default: Any = _SENTINEL  # _SENTINEL → no default
    description: str | None = None


@dataclass(frozen=True, slots=True)
class SchemaIR:
    """One entry from components.schemas."""

    name: str
    kind: Literal["struct", "alias", "enum"]
    fields: tuple[FieldIR, ...] = ()
    alias_of: str | None = None
    enum_values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParamIR:
    """A path, query, or header parameter."""

    name: str
    type_str: str
    required: bool
    default: Any = _SENTINEL
    description: str | None = None


@dataclass(frozen=True, slots=True)
class OperationIR:
    """One HTTP operation from paths."""

    operation_id: str
    method: Literal["get", "post", "put", "patch", "delete"]
    path: str
    path_params: tuple[ParamIR, ...] = ()
    query_params: tuple[ParamIR, ...] = ()
    header_params: tuple[ParamIR, ...] = ()
    body_type: str | None = None
    response_type: str | None = None
    summary: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ClientIR:
    """Top-level IR for a complete client SDK."""

    title: str
    version: str
    base_url: str | None = None
    schemas: tuple[SchemaIR, ...] = ()
    operations: tuple[OperationIR, ...] = ()


# Exported sentinel so renderers can check ``field.default is SENTINEL``
SENTINEL = _SENTINEL
