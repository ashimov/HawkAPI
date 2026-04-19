"""OpenAPI 3.1 dict → ClientIR parser."""

from __future__ import annotations

import re
from typing import Any, cast

from hawkapi.openapi.codegen.ir import (
    _SENTINEL,  # pyright: ignore[reportPrivateUsage]
    ClientIR,
    FieldIR,
    OperationIR,
    ParamIR,
    SchemaIR,
)

_METHODS = ("get", "post", "put", "patch", "delete")


def _ref_name(ref: str) -> str:
    """Return the last segment of a ``$ref`` string.

    ``"#/components/schemas/Item"`` → ``"Item"``
    """
    return ref.rsplit("/", 1)[-1]


def _schema_to_type_str(schema: dict[str, Any], components: dict[str, Any]) -> str:
    """Convert a JSON-Schema fragment to a Python-dialect type string.

    The TypeScript renderer handles the Python→TS translation internally.

    Examples
    --------
    ``{"type": "integer"}``                        → ``"int"``
    ``{"type": "string"}``                         → ``"str"``
    ``{"type": "boolean"}``                        → ``"bool"``
    ``{"type": "number"}``                         → ``"float"``
    ``{"$ref": "#/components/schemas/Item"}``      → ``"Item"``
    ``{"type": "array", "items": {"$ref": ...}}``  → ``"list[Item]"``
    ``{"type": "object"}``                         → ``"dict[str, Any]"``
    nullable (``anyOf`` with null)                 → ``"T | None"``
    """
    if not schema:
        return "Any"

    # $ref
    if "$ref" in schema:
        return _ref_name(schema["$ref"])

    # anyOf/oneOf — look for nullable pattern: [T, {"type": "null"}]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            variants: list[dict[str, Any]] = schema[key]
            non_null = [v for v in variants if v.get("type") != "null"]
            has_null = any(v.get("type") == "null" for v in variants)
            if len(non_null) == 1:
                inner = _schema_to_type_str(non_null[0], components)
                return f"{inner} | None" if has_null else inner
            # multiple non-null variants — fall through to Any
            return "Any"

    schema_type = schema.get("type", "")
    fmt = schema.get("format", "")

    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "string":
        _ = fmt  # no special handling in v1
        return "str"
    if schema_type == "array":
        items = schema.get("items", {})
        inner = _schema_to_type_str(items, components)
        return f"list[{inner}]"
    if schema_type == "object":
        additional = schema.get("additionalProperties")
        if additional and isinstance(additional, dict):
            val_type = _schema_to_type_str(cast(dict[str, Any], additional), components)
            return f"dict[str, {val_type}]"
        return "dict[str, Any]"

    # nullable shorthand (OpenAPI 3.1 uses `{"type": ["string", "null"]}`)
    if isinstance(schema_type, list):
        type_list: list[str] = [str(t) for t in schema_type]  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
        non_null_types = [t for t in type_list if t != "null"]
        has_null = "null" in type_list
        if len(non_null_types) == 1:
            inner = _schema_to_type_str({**schema, "type": non_null_types[0]}, components)
            return f"{inner} | None" if has_null else inner

    return "Any"


def _parse_schemas(
    raw_schemas: dict[str, Any],
    components: dict[str, Any],
) -> tuple[SchemaIR, ...]:
    """Walk ``components.schemas`` and return a tuple of ``SchemaIR``."""
    result: list[SchemaIR] = []

    for name, schema in raw_schemas.items():
        # enum
        if "enum" in schema:
            values = tuple(str(v) for v in schema["enum"])
            result.append(SchemaIR(name=name, kind="enum", enum_values=values))
            continue

        # $ref at top level → alias
        if "$ref" in schema:
            alias = _schema_to_type_str(schema, components)
            result.append(SchemaIR(name=name, kind="alias", alias_of=alias))
            continue

        schema_type = schema.get("type", "object")

        # array → alias
        if schema_type == "array":
            alias = _schema_to_type_str(schema, components)
            result.append(SchemaIR(name=name, kind="alias", alias_of=alias))
            continue

        # allOf/anyOf/oneOf with no properties → alias
        for compose_key in ("allOf", "anyOf", "oneOf"):
            if compose_key in schema and "properties" not in schema:
                alias = _schema_to_type_str(schema, components)
                result.append(SchemaIR(name=name, kind="alias", alias_of=alias))
                break
        else:
            # object → struct
            properties: dict[str, Any] = schema.get("properties", {})
            required_set: set[str] = set(schema.get("required", []))
            fields: list[FieldIR] = []
            for prop_name, prop_schema in properties.items():
                type_str = _schema_to_type_str(prop_schema, components)
                is_required = prop_name in required_set
                # optional fields default to None
                default: Any = _SENTINEL if is_required else None
                description = prop_schema.get("description")
                fields.append(
                    FieldIR(
                        name=prop_name,
                        type_str=type_str,
                        required=is_required,
                        default=default,
                        description=description,
                    )
                )
            result.append(
                SchemaIR(
                    name=name,
                    kind="struct",
                    fields=tuple(fields),
                )
            )

    return tuple(result)


def _operation_id_fallback(method: str, path: str) -> str:
    """Generate an operation ID from method + path when ``operationId`` is absent."""
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", path).strip("_")
    return f"{method}_{sanitized}"


def _resolve_response_type(
    responses: dict[str, Any],
    components: dict[str, Any],
) -> str | None:
    """Extract the response schema type string from an operation's responses."""
    # Prefer 200, then 201, then first non-"default" numeric response
    candidates = ["200", "201"]
    for status in candidates:
        if status in responses:
            resp = responses[status]
            content = resp.get("content", {})
            json_content = content.get("application/json", {})
            schema = json_content.get("schema", {})
            if schema:
                return _schema_to_type_str(schema, components)
    # Fall through to any non-default response
    for status, resp in responses.items():
        if status == "default":
            continue
        content = resp.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        if schema:
            return _schema_to_type_str(schema, components)
    return None


def _parse_operations(
    paths: dict[str, Any],
    components: dict[str, Any],
) -> tuple[OperationIR, ...]:
    """Walk ``paths`` and return a tuple of ``OperationIR``."""
    result: list[OperationIR] = []

    for path, path_item in paths.items():
        for method in _METHODS:
            op = path_item.get(method)
            if op is None:
                continue

            operation_id: str = op.get("operationId") or _operation_id_fallback(method, path)

            # Parameters
            path_params: list[ParamIR] = []
            query_params: list[ParamIR] = []
            header_params: list[ParamIR] = []

            for param in op.get("parameters", []):
                param_schema = param.get("schema", {})
                type_str = _schema_to_type_str(param_schema, components)
                is_required = param.get("required", False)
                default: Any = _SENTINEL if is_required else None
                pir = ParamIR(
                    name=param["name"],
                    type_str=type_str,
                    required=is_required,
                    default=default,
                    description=param.get("description"),
                )
                location = param.get("in", "query")
                if location == "path":
                    path_params.append(pir)
                elif location == "query":
                    query_params.append(pir)
                elif location == "header":
                    header_params.append(pir)

            # Request body
            body_type: str | None = None
            request_body = op.get("requestBody")
            if request_body:
                content = request_body.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema", {})
                if schema:
                    body_type = _schema_to_type_str(schema, components)

            # Response type
            response_type = _resolve_response_type(op.get("responses", {}), components)

            result.append(
                OperationIR(
                    operation_id=operation_id,
                    method=method,  # type: ignore[arg-type]
                    path=path,
                    path_params=tuple(path_params),
                    query_params=tuple(query_params),
                    header_params=tuple(header_params),
                    body_type=body_type,
                    response_type=response_type,
                    summary=op.get("summary"),
                    description=op.get("description"),
                )
            )

    return tuple(result)


def build_client_ir(spec: dict[str, Any]) -> ClientIR:
    """Parse an OpenAPI 3.1 dict and return a :class:`ClientIR`.

    Parameters
    ----------
    spec:
        A fully-resolved OpenAPI 3.1 document as a Python dict.

    Returns
    -------
    ClientIR
        Language-agnostic intermediate representation ready for rendering.
    """
    info = spec.get("info", {})
    title: str = info.get("title", "API")
    version: str = info.get("version", "0.0.0")
    base_url: str | None = spec.get("servers", [{}])[0].get("url") if spec.get("servers") else None

    components: dict[str, Any] = spec.get("components", {})
    raw_schemas: dict[str, Any] = components.get("schemas", {})

    schemas = _parse_schemas(raw_schemas, components)
    operations = _parse_operations(spec.get("paths", {}), components)

    return ClientIR(
        title=title,
        version=version,
        base_url=base_url,
        schemas=schemas,
        operations=operations,
    )
