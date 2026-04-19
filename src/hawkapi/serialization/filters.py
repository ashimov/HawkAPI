"""FastAPI-parity ``response_model_exclude_*`` filter helpers.

The framework calls :func:`apply_exclude_filters` after ``response_model`` has
coerced a handler's return value into its declared model type (msgspec Struct
or Pydantic BaseModel). The helper produces a plain ``dict``/``list``/scalar
tree with the requested fields removed; the encoder then serialises that tree
to JSON.

Three flags, each a boolean:

* ``exclude_none``    — drop keys whose value is ``None``, recursively.
* ``exclude_defaults`` — drop keys whose value equals the model field's default.
* ``exclude_unset``   — drop keys the user never explicitly set.

Pydantic exposes all three natively via ``BaseModel.model_dump(...)``. For
msgspec Structs, ``exclude_defaults`` compares each field against the struct
metadata, and ``exclude_unset`` relies on fields declared with
``msgspec.UNSET``/``UnsetType``. Plain Structs that don't use the UNSET
sentinel can't distinguish set-from-default, so ``exclude_unset`` is a no-op
there — documented behaviour, not a bug.
"""

from __future__ import annotations

from typing import Any, cast

import msgspec


def apply_exclude_filters(
    data: Any,
    model: type[Any] | None,
    *,
    exclude_none: bool,
    exclude_unset: bool,
    exclude_defaults: bool,
) -> Any:
    """Apply the three ``response_model_exclude_*`` flags and return a
    JSON-ready dict/list/primitive tree.

    Callers pass either an already-coerced model instance (msgspec Struct or
    Pydantic model) or a raw dict. No flag set? Callers should skip this
    function for the zero-overhead hot path.
    """
    if not (exclude_none or exclude_unset or exclude_defaults):
        return data

    # --- Pydantic path ----------------------------------------------------
    if _is_pydantic_instance(data):
        return data.model_dump(
            exclude_none=exclude_none,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
        )

    # --- msgspec Struct path ---------------------------------------------
    if isinstance(data, msgspec.Struct):
        raw = msgspec.to_builtins(data)
        if isinstance(raw, dict):
            struct_type = type(data)
            result = _filter_struct_dict(
                cast(dict[str, Any], raw),
                struct_type,
                data,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
            )
        else:
            result = raw
        if exclude_none:
            result = _drop_none(result)
        return result

    # --- Plain dict path --------------------------------------------------
    # No model metadata → we can honour exclude_none only.
    if exclude_none:
        return _drop_none(data)
    return data


def _is_pydantic_instance(obj: Any) -> bool:
    """Return True for an instance of a Pydantic v2 BaseModel."""
    try:
        import pydantic  # noqa: PLC0415
    except ImportError:
        return False
    return isinstance(obj, pydantic.BaseModel)


def _filter_struct_dict(
    raw: dict[str, Any],
    struct_type: type[msgspec.Struct],
    instance: msgspec.Struct,
    *,
    exclude_unset: bool,
    exclude_defaults: bool,
) -> Any:
    """Apply exclude_defaults / exclude_unset to a msgspec-generated dict.

    ``raw`` is the ``msgspec.to_builtins`` result; ``struct_type`` and
    ``instance`` carry the metadata needed for default comparison.
    """
    if not (exclude_unset or exclude_defaults):
        return raw

    fields_meta = msgspec.structs.fields(struct_type)
    out: dict[str, Any] = {}
    for field_info in fields_meta:
        raw_key = field_info.encode_name
        if raw_key not in raw:
            continue
        value = raw[raw_key]
        attr = getattr(instance, field_info.name)
        if exclude_unset and attr is msgspec.UNSET:
            continue
        if exclude_defaults and _is_default(field_info, attr):
            continue
        # Recurse into nested Structs.
        if isinstance(attr, msgspec.Struct):
            nested_raw: dict[str, Any] = cast(
                dict[str, Any],
                value if isinstance(value, dict) else msgspec.to_builtins(attr),
            )
            value = _filter_struct_dict(
                nested_raw,
                type(attr),
                attr,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
            )
        out[raw_key] = value
    return out


def _is_default(field_info: msgspec.structs.FieldInfo, value: Any) -> bool:
    """True when ``value`` equals the declared default for this field."""
    default = field_info.default
    if default is not msgspec.NODEFAULT:
        try:
            return bool(value == default)
        except Exception:
            return False
    factory = field_info.default_factory
    if factory is not msgspec.NODEFAULT:
        try:
            return bool(value == factory())
        except Exception:
            return False
    return False


def _drop_none(data: Any) -> Any:
    """Recursively remove keys with ``None`` values from dict/list trees."""
    if isinstance(data, dict):
        d = cast(dict[str, Any], data)
        return {k: _drop_none(v) for k, v in d.items() if v is not None}
    if isinstance(data, list):
        return [_drop_none(v) for v in cast(list[Any], data)]
    return data


__all__ = ["apply_exclude_filters"]
