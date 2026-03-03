"""Per-request state container."""

from __future__ import annotations

from typing import Any


class State:
    """Attribute-based dict for storing per-request data."""

    __slots__ = ("_data",)
    _data: dict[str, Any]

    def __init__(self) -> None:
        object.__setattr__(self, "_data", {})

    def __setattr__(self, name: str, value: Any) -> None:
        self._data[name] = value

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"State has no attribute {name!r}") from None

    def __delattr__(self, name: str) -> None:
        try:
            del self._data[name]
        except KeyError:
            raise AttributeError(f"State has no attribute {name!r}") from None

    def __contains__(self, name: str) -> bool:
        return name in self._data

    def __repr__(self) -> str:
        return f"State({self._data!r})"
