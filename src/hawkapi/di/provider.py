"""Dependency providers with lifecycle management."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from enum import Enum
from typing import Any


class Lifecycle(Enum):
    """Dependency lifecycle."""

    SINGLETON = "singleton"  # Created once, shared across all scopes
    SCOPED = "scoped"  # Created once per scope (e.g., per request)
    TRANSIENT = "transient"  # New instance every time


_UNSET = object()


class Provider:
    """Wraps a factory function with lifecycle metadata."""

    __slots__ = ("service_type", "factory", "lifecycle", "name", "_singleton_instance", "_lock")

    def __init__(
        self,
        service_type: type,
        factory: Callable[..., Any],
        lifecycle: Lifecycle,
        name: str | None = None,
    ) -> None:
        self.service_type = service_type
        self.factory = factory
        self.lifecycle = lifecycle
        self.name = name
        self._singleton_instance: Any = _UNSET
        self._lock: asyncio.Lock | None = None

    async def resolve(self) -> Any:
        """Resolve this provider. For singletons, returns cached instance."""
        if self.lifecycle == Lifecycle.SINGLETON:
            if self._singleton_instance is not _UNSET:
                return self._singleton_instance
            if self._lock is None:
                self._lock = asyncio.Lock()
            async with self._lock:
                if self._singleton_instance is not _UNSET:
                    return self._singleton_instance
                self._singleton_instance = await self._create()
                return self._singleton_instance

        return await self._create()

    async def _create(self) -> Any:
        """Call the factory to create an instance."""
        result = self.factory()
        if inspect.isawaitable(result):
            result = await result
        return result

    def __repr__(self) -> str:
        return (
            f"Provider({self.service_type.__name__}, "
            f"lifecycle={self.lifecycle.value}, name={self.name!r})"
        )
