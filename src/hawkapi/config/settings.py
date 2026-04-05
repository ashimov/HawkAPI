"""Settings base class using msgspec Struct with environment variable binding.

Unlike FastAPI's BaseSettings (coupled to Pydantic), this is framework-owned
and works with msgspec Structs directly.
"""

from __future__ import annotations

import os
from typing import Any, get_type_hints

from hawkapi.config.profiles import load_profile_env


class _EnvField:
    """Descriptor for environment variable binding."""

    __slots__ = ("env_var", "default", "has_default")

    def __init__(self, env_var: str, default: Any = ...) -> None:
        self.env_var = env_var
        self.default = default
        self.has_default = default is not ...


def env_field(env_var: str, default: Any = ...) -> Any:
    """Bind a settings field to an environment variable.

    Usage:
        class AppSettings(Settings):
            db_url: str = env_field("DATABASE_URL")
            debug: bool = env_field("DEBUG", default=False)
    """
    return _EnvField(env_var, default)


class Settings:
    """Base class for application settings.

    Loads values from environment variables with profile support.
    Uses msgspec for type coercion and validation.

    Usage:
        class AppSettings(Settings):
            db_url: str = env_field("DATABASE_URL")
            debug: bool = env_field("DEBUG", default=False)
            port: int = env_field("PORT", default=8000)

        settings = AppSettings.load(profile="production")
    """

    @classmethod
    def load(
        cls,
        profile: str | None = None,
        base_dir: str | None = None,
        **overrides: Any,
    ) -> Settings:
        """Load settings from environment + .env files.

        Args:
            profile: Environment profile (dev/staging/production).
                     Defaults to HAWK_ENV env var or "development".
            base_dir: Directory containing .env files.
            **overrides: Explicit values that override everything.
        """
        env_vars = load_profile_env(profile, base_dir)
        hints = get_type_hints(cls)

        kwargs: dict[str, Any] = {}
        for field_name, field_type in hints.items():
            if field_name.startswith("_"):
                continue

            # Check for env_field descriptor
            class_val = getattr(cls, field_name, ...)
            if isinstance(class_val, _EnvField):
                env_var = class_val.env_var
                # Use sentinel to preserve falsy override values (0, "", False)
                _MISSING = object()
                raw = overrides.get(field_name, _MISSING)
                if raw is _MISSING:
                    raw = env_vars.get(env_var)
                if raw is None or raw is _MISSING:
                    raw = os.environ.get(env_var)
                if raw is not None:
                    kwargs[field_name] = _coerce(raw, field_type)
                elif class_val.has_default:
                    kwargs[field_name] = class_val.default
                else:
                    raise ValueError(f"Required setting {field_name!r} (env: {env_var}) is not set")
            elif field_name in overrides:
                kwargs[field_name] = overrides[field_name]

        instance = cls.__new__(cls)
        for key, value in kwargs.items():
            object.__setattr__(instance, key, value)
        return instance

    def __repr__(self) -> str:
        hints = get_type_hints(type(self))
        fields: list[str] = []
        for name in hints:
            if not name.startswith("_"):
                val = getattr(self, name, "?")
                # Mask sensitive values
                if any(s in name.lower() for s in ("secret", "password", "token", "key")):
                    val = "***"
                fields.append(f"{name}={val!r}")
        return f"{type(self).__name__}({', '.join(fields)})"


def _unwrap_optional(tp: Any) -> Any:
    """Unwrap Optional[T] / T | None to T."""
    import types as _types
    from typing import Union, get_args, get_origin

    origin = get_origin(tp)
    if origin in (Union, _types.UnionType):
        non_none = [a for a in get_args(tp) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return tp


def _coerce(value: Any, target_type: type) -> Any:
    """Coerce a value to the target type."""
    target_type = _unwrap_optional(target_type)
    if not isinstance(target_type, type):  # pyright: ignore[reportUnnecessaryIsInstance]
        return value  # Unknown generic — return as-is
    if isinstance(value, target_type):
        return value
    if target_type is bool:
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if target_type is str:
        return str(value)
    if target_type is list:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return list(value)
    return value
