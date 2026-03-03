"""Path parameter type converters."""

from __future__ import annotations

import uuid
from collections.abc import Callable

CONVERTERS: dict[str, Callable[[str], object]] = {
    "str": str,
    "int": int,
    "float": float,
    "uuid": uuid.UUID,
}


def get_converter(type_name: str) -> Callable[[str], object]:
    """Get a converter function by type name."""
    converter = CONVERTERS.get(type_name)
    if converter is None:
        raise ValueError(f"Unknown path parameter type: {type_name!r}")
    return converter
