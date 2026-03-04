"""Parameter source markers for Annotated[] type hints."""

from __future__ import annotations

from typing import Any


class ParamMarker:
    """Base class for parameter source markers."""

    __slots__ = ("alias", "description", "default", "default_factory", "example")

    def __init__(
        self,
        *,
        alias: str | None = None,
        description: str | None = None,
        default: Any = ...,
        default_factory: Any = None,
        example: Any = ...,
    ) -> None:
        self.alias = alias
        self.description = description
        self.default = default
        self.default_factory = default_factory
        self.example = example

    def has_default(self) -> bool:
        """Return True if a default value or factory is configured."""
        return self.default is not ... or self.default_factory is not None

    def get_default(self) -> Any:
        """Return the default value, invoking the factory if set."""
        if self.default_factory is not None:
            return self.default_factory()
        return self.default


class Path(ParamMarker):
    """Mark a parameter as coming from the URL path."""


class Query(ParamMarker):
    """Mark a parameter as coming from the query string."""


class Header(ParamMarker):
    """Mark a parameter as coming from HTTP headers."""


class Body(ParamMarker):
    """Mark a parameter as coming from the request body."""


class Cookie(ParamMarker):
    """Mark a parameter as coming from cookies."""
