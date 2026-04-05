"""Path parameter type converters."""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable


def _finite_float(value: str) -> float:
    """Convert string to float, rejecting nan/inf."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite float not allowed: {value!r}")
    return result


CONVERTERS: dict[str, Callable[[str], object]] = {
    "str": str,
    "int": int,
    "float": _finite_float,
    "uuid": uuid.UUID,
}


def get_converter(type_name: str) -> Callable[[str], object]:
    """Get a converter function by type name."""
    converter = CONVERTERS.get(type_name)
    if converter is None:
        raise ValueError(f"Unknown path parameter type: {type_name!r}")
    return converter
