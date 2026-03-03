"""Case-insensitive HTTP headers."""

from __future__ import annotations

from collections.abc import Iterator


class Headers:
    """Case-insensitive, immutable header wrapper over raw ASGI header tuples."""

    __slots__ = ("_raw", "_dict")

    def __init__(self, raw: list[tuple[bytes, bytes]] | None = None) -> None:
        self._raw = raw or []
        # Build lowercase lookup dict (last value wins for single get)
        self._dict: dict[str, str] = {}
        for key, value in self._raw:
            self._dict[key.decode("latin-1").lower()] = value.decode("latin-1")

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._dict.get(key.lower(), default)

    def getlist(self, key: str) -> list[str]:
        """Get all values for a header (e.g., multiple Set-Cookie)."""
        lower_key = key.lower()
        return [
            value.decode("latin-1")
            for k, value in self._raw
            if k.decode("latin-1").lower() == lower_key
        ]

    def __getitem__(self, key: str) -> str:
        try:
            return self._dict[key.lower()]
        except KeyError:
            raise KeyError(key) from None

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key.lower() in self._dict

    def __iter__(self) -> Iterator[tuple[str, str]]:
        for key, value in self._raw:
            yield key.decode("latin-1"), value.decode("latin-1")

    def __len__(self) -> int:
        return len(self._raw)

    def __repr__(self) -> str:
        return f"Headers({self._dict!r})"
