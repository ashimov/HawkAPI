"""Request scope for managing scoped dependency instances."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from hawkapi.di.provider import Lifecycle, Provider


class Scope:
    """A dependency scope — typically one per HTTP request.

    Scoped dependencies are created once per scope and cached.
    On exit, any instances with close/aclose methods are cleaned up.
    """

    __slots__ = ("_providers", "_instances", "_teardown")

    def __init__(self, providers: dict[tuple[type, str | None], Provider]) -> None:
        self._providers = providers
        self._instances: dict[tuple[type, str | None], Any] = {}
        self._teardown: list[tuple[Any, Callable[..., Any]]] = []

    async def resolve(self, service_type: type, name: str | None = None) -> Any:
        """Resolve a dependency within this scope."""
        key = (service_type, name)

        # Check scope cache first
        if key in self._instances:
            return self._instances[key]

        provider = self._providers.get(key)
        actual_key = key
        if provider is None and name is not None:
            # Try without name (unnamed provider), but cache under the unnamed key
            provider = self._providers.get((service_type, None))
            actual_key = (service_type, None)
        if provider is None:
            raise LookupError(
                f"No provider registered for {service_type.__name__}"
                + (f" (name={name!r})" if name else "")
            )

        instance = await provider.resolve()

        # Cache scoped instances under the actual provider key
        if provider.lifecycle == Lifecycle.SCOPED:
            self._instances[actual_key] = instance
            # Pre-resolve the close method at resolve time
            close = getattr(instance, "aclose", None) or getattr(instance, "close", None)
            if close is not None:
                self._teardown.append((instance, close))
        elif provider.lifecycle == Lifecycle.SINGLETON:
            # Singletons are cached in the provider itself
            pass

        return instance

    async def close(self) -> None:
        """Tear down scoped instances (exception-safe).

        Ensures ALL instances are cleaned up even if some raise during teardown.
        """
        errors: list[Exception] = []
        for _instance, close in reversed(self._teardown):
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                errors.append(exc)
        self._instances.clear()
        self._teardown.clear()
        if errors:
            raise ExceptionGroup("DI scope teardown errors", errors)

    async def __aenter__(self) -> Scope:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
