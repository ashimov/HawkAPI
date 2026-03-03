"""Dependency Injection container.

Standalone — works inside routes, CLI scripts, background tasks, tests.
Supports singleton, scoped, and transient lifecycles.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hawkapi.di.provider import Lifecycle, Provider
from hawkapi.di.scope import Scope


class Container:
    """DI Container with lifecycle management.

    Usage:
        container = Container()
        container.singleton(DatabasePool, factory=create_pool)
        container.scoped(DBSession, factory=create_session)
        container.transient(RequestLogger, factory=RequestLogger)

        # Inside routes (automatic via framework):
        async def handler(session: DBSession): ...

        # Outside routes (manual):
        async with container.scope() as scope:
            session = await scope.resolve(DBSession)
    """

    def __init__(self) -> None:
        self._providers: dict[tuple[type, str | None], Provider] = {}

    def register(
        self,
        service_type: type,
        *,
        factory: Callable[..., Any],
        lifecycle: Lifecycle,
        name: str | None = None,
    ) -> None:
        """Register a dependency provider."""
        key = (service_type, name)
        if key in self._providers:
            raise ValueError(
                f"Provider already registered for {service_type.__name__}"
                + (f" (name={name!r})" if name else "")
            )
        self._providers[key] = Provider(service_type, factory, lifecycle, name)

    def singleton(
        self,
        service_type: type,
        *,
        factory: Callable[..., Any],
        name: str | None = None,
    ) -> None:
        """Register a singleton (created once, shared globally)."""
        self.register(service_type, factory=factory, lifecycle=Lifecycle.SINGLETON, name=name)

    def scoped(
        self,
        service_type: type,
        *,
        factory: Callable[..., Any],
        name: str | None = None,
    ) -> None:
        """Register a scoped dependency (created once per scope/request)."""
        self.register(service_type, factory=factory, lifecycle=Lifecycle.SCOPED, name=name)

    def transient(
        self,
        service_type: type,
        *,
        factory: Callable[..., Any],
        name: str | None = None,
    ) -> None:
        """Register a transient dependency (new instance every time)."""
        self.register(service_type, factory=factory, lifecycle=Lifecycle.TRANSIENT, name=name)

    def scope(self) -> Scope:
        """Create a new dependency scope (e.g., for a request)."""
        return Scope(self._providers)

    def has(self, service_type: type, name: str | None = None) -> bool:
        """Check if a provider is registered."""
        return (service_type, name) in self._providers

    def override(
        self,
        service_type: type,
        *,
        factory: Callable[..., Any],
        name: str | None = None,
    ) -> _OverrideContext:
        """Temporarily replace a provider (for testing)."""
        return _OverrideContext(self, service_type, factory, name)

    async def resolve(self, service_type: type, name: str | None = None) -> Any:
        """Resolve a dependency directly (for singletons or transients).

        For scoped dependencies, use container.scope() instead.
        """
        key = (service_type, name)
        provider = self._providers.get(key)
        if provider is None:
            provider = self._providers.get((service_type, None))
        if provider is None:
            raise LookupError(
                f"No provider registered for {service_type.__name__}"
                + (f" (name={name!r})" if name else "")
            )
        if provider.lifecycle == Lifecycle.SCOPED:
            raise RuntimeError(
                f"Cannot resolve scoped dependency {service_type.__name__} without a scope. "
                f"Use container.scope() context manager."
            )
        return await provider.resolve()


class _OverrideContext:
    """Context manager for temporarily overriding a provider."""

    __slots__ = ("_container", "_key", "_factory", "_original")

    def __init__(
        self,
        container: Container,
        service_type: type,
        factory: Callable[..., Any],
        name: str | None,
    ) -> None:
        self._container = container
        self._key = (service_type, name)
        self._factory = factory
        self._original: Provider | None = None

    def __enter__(self) -> _OverrideContext:
        providers = self._container._providers  # pyright: ignore[reportPrivateUsage]
        self._original = providers.get(self._key)
        service_type, name = self._key
        lifecycle = Lifecycle.TRANSIENT
        if self._original:
            lifecycle = self._original.lifecycle
        providers[self._key] = Provider(service_type, self._factory, lifecycle, name)
        return self

    def __exit__(self, *args: Any) -> None:
        providers = self._container._providers  # pyright: ignore[reportPrivateUsage]
        if self._original is not None:
            providers[self._key] = self._original
        else:
            providers.pop(self._key, None)
