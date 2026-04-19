"""Built-in FlagProvider implementations."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hawkapi.flags.base import EvalContext

# ---------------------------------------------------------------------------
# Shared coercion helpers
# ---------------------------------------------------------------------------


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce a stored value to bool; ints/floats are coerced, strings are not."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_string(value: Any, default: str) -> str:
    """Only actual str values are accepted; everything else yields default."""
    if isinstance(value, str):
        return value
    return default


def _coerce_number(value: Any, default: float) -> float:
    """int and float are accepted; bool (subclass of int) yields default."""
    if isinstance(value, bool):
        # bool is subclass of int — treat as default to avoid surprising coercion
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


# ---------------------------------------------------------------------------
# StaticFlagProvider
# ---------------------------------------------------------------------------


class StaticFlagProvider:
    """Simple dict-backed flag provider.  Thread-safe (read-only after init)."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values: dict[str, Any] = dict(values)

    async def get_bool(
        self, key: str, default: bool, *, context: EvalContext | None = None
    ) -> bool:
        if key not in self._values:
            return default
        return _coerce_bool(self._values[key], default)

    async def get_string(
        self, key: str, default: str, *, context: EvalContext | None = None
    ) -> str:
        if key not in self._values:
            return default
        return _coerce_string(self._values[key], default)

    async def get_number(
        self, key: str, default: float, *, context: EvalContext | None = None
    ) -> float:
        if key not in self._values:
            return default
        return _coerce_number(self._values[key], default)


# ---------------------------------------------------------------------------
# EnvFlagProvider
# ---------------------------------------------------------------------------

_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "off"})


class EnvFlagProvider:
    """Read flags from environment variables.

    The env-var name is ``prefix + key.upper().replace('.', '_').replace('-', '_')``.
    Default prefix: ``HAWKAPI_FLAG_``.
    """

    def __init__(self, prefix: str = "HAWKAPI_FLAG_") -> None:
        self._prefix = prefix

    def _env_name(self, key: str) -> str:
        return self._prefix + key.upper().replace(".", "_").replace("-", "_")

    async def get_bool(
        self, key: str, default: bool, *, context: EvalContext | None = None
    ) -> bool:
        raw = os.environ.get(self._env_name(key))
        if raw is None:
            return default
        low = raw.lower()
        if low in _BOOL_TRUE:
            return True
        if low in _BOOL_FALSE:
            return False
        return default

    async def get_string(
        self, key: str, default: str, *, context: EvalContext | None = None
    ) -> str:
        raw = os.environ.get(self._env_name(key))
        if raw is None:
            return default
        return raw

    async def get_number(
        self, key: str, default: float, *, context: EvalContext | None = None
    ) -> float:
        raw = os.environ.get(self._env_name(key))
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default


# ---------------------------------------------------------------------------
# FileFlagProvider
# ---------------------------------------------------------------------------


class FileFlagProvider:
    """Load flags from a JSON, TOML, or YAML file with mtime-based hot-reload.

    The file is re-read whenever its mtime changes — no background thread required.
    Supported extensions: ``.json``, ``.toml``, ``.yaml``, ``.yml``.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._mtime: float = -1.0
        self._cache: dict[str, Any] = {}

    def _ensure_loaded(self) -> None:
        """Reload the file if it has changed since last load."""
        try:
            current_mtime = self._path.stat().st_mtime
        except OSError:
            # File missing — keep whatever was cached (or empty).
            return

        if current_mtime == self._mtime:
            return

        ext = self._path.suffix.lower()
        if ext == ".json":
            with self._path.open("rb") as fh:
                data = json.load(fh)
        elif ext == ".toml":
            import tomllib  # stdlib 3.11+  # noqa: PLC0415

            with self._path.open("rb") as fh:
                data: Any = tomllib.load(fh)
        elif ext in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore[import-untyped]  # noqa: PLC0415
            except ImportError as exc:
                raise ImportError(
                    "pyyaml is required to load YAML flag files. "
                    "Install it with: pip install pyyaml"
                ) from exc
            with self._path.open() as fh:
                data = yaml.safe_load(fh) or {}
        else:
            raise ValueError(
                f"Unsupported flag file extension {ext!r}. Use .json, .toml, .yaml, or .yml."
            )

        # Order matters under concurrent reads (free-threaded CPython or
        # thread-pool workers): if we updated _mtime first, another thread
        # could see the new mtime, skip the reload, and read the stale
        # _cache. Assigning _cache first and _mtime last means readers that
        # observe the new mtime always observe the new cache too. Both
        # assignments are atomic at the Python level.
        self._cache = data if isinstance(data, dict) else {}
        self._mtime = current_mtime

    async def get_bool(
        self, key: str, default: bool, *, context: EvalContext | None = None
    ) -> bool:
        self._ensure_loaded()
        if key not in self._cache:
            return default
        return _coerce_bool(self._cache[key], default)

    async def get_string(
        self, key: str, default: str, *, context: EvalContext | None = None
    ) -> str:
        self._ensure_loaded()
        if key not in self._cache:
            return default
        return _coerce_string(self._cache[key], default)

    async def get_number(
        self, key: str, default: float, *, context: EvalContext | None = None
    ) -> float:
        self._ensure_loaded()
        if key not in self._cache:
            return default
        return _coerce_number(self._cache[key], default)


__all__ = ["EnvFlagProvider", "FileFlagProvider", "StaticFlagProvider"]
