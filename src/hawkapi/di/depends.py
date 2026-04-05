"""Depends() marker for dependency injection."""

from __future__ import annotations

from typing import Any


class Depends:
    """Marker to declare a dependency.

    Usage in route handlers:
        async def handler(db: Annotated[DBSession, Depends(get_db)]):
            ...

    Usage in container registration:
        container.scoped(DBSession, factory=lambda pool=Depends(DatabasePool): pool.session())

    Usage with named dependencies:
        async def handler(cache: Annotated[Redis, Depends(name="cache_redis")]):
            ...
    """

    __slots__ = ("dependency", "name")

    def __init__(
        self,
        dependency: Any = None,
        *,
        name: str | None = None,
    ) -> None:
        self.dependency = dependency
        self.name = name

    def __repr__(self) -> str:
        if self.name:
            return f"Depends(name={self.name!r})"
        if self.dependency:
            name = getattr(self.dependency, "__name__", repr(self.dependency))
            return f"Depends({name})"
        return "Depends()"
