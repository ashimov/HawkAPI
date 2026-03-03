"""Query string parser."""

from __future__ import annotations

from urllib.parse import parse_qs


class QueryParams:
    """Parsed query string with multi-value support."""

    __slots__ = ("_dict", "_raw")

    def __init__(self, query_string: bytes) -> None:
        self._raw = query_string
        self._dict: dict[str, list[str]] = parse_qs(
            query_string.decode("latin-1"), keep_blank_values=True
        )

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get first value for a key."""
        values = self._dict.get(key)
        if values:
            return values[0]
        return default

    def getlist(self, key: str) -> list[str]:
        """Get all values for a key."""
        return self._dict.get(key, [])

    def __getitem__(self, key: str) -> str:
        values = self._dict.get(key)
        if not values:
            raise KeyError(key)
        return values[0]

    def __contains__(self, key: object) -> bool:
        return key in self._dict

    def __iter__(self) -> object:
        return iter(self._dict)

    def __len__(self) -> int:
        return len(self._dict)

    def __repr__(self) -> str:
        return f"QueryParams({self._dict!r})"

    def to_dict(self) -> dict[str, str]:
        """Single-value dict (first value per key)."""
        return {k: v[0] for k, v in self._dict.items() if v}
