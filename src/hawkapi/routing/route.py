"""Route definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hawkapi._types import RouteHandler

if TYPE_CHECKING:
    from hawkapi.di.param_plan import HandlerPlan
    from hawkapi.middleware.base import Middleware


@dataclass(frozen=True, slots=True)
class Route:
    """Represents a single registered route."""

    path: str
    handler: RouteHandler
    methods: frozenset[str]
    name: str | None = None
    status_code: int = 200
    response_model: type[Any] | None = None
    tags: list[str] = field(default_factory=lambda: [])
    summary: str | None = None
    description: str | None = None
    include_in_schema: bool = True
    deprecated: bool = False
    sunset: str | None = None
    deprecation_link: str | None = None
    version: str | None = None
    permissions: list[str] | None = None
    middleware: tuple[type[Middleware] | tuple[type[Middleware], dict[str, Any]], ...] | None = None
    _handler_plan: HandlerPlan | None = field(default=None, repr=False)
