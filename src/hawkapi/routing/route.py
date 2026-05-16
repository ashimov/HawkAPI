"""Route definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hawkapi._types import RouteHandler

if TYPE_CHECKING:
    from hawkapi.di.param_plan import DepCallablePlan, HandlerPlan
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
    response_model_exclude_none: bool = False
    response_model_exclude_unset: bool = False
    response_model_exclude_defaults: bool = False
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
    dependencies: tuple[DepCallablePlan, ...] = ()
    required_scopes: tuple[str, ...] = ()
    _handler_plan: HandlerPlan | None = field(default=None, repr=False)
    # Pre-computed fast-path flag: True when the route has no DI, no deps,
    # no permissions, no background tasks, is async, returns a Response
    # directly, and is not deprecated. Set once at registration time by the
    # router so the per-request hot path avoids branching on all these checks.
    _trivial: bool = field(default=False, repr=False)
    # Pre-built ASGI (start, body) message tuple for handlers whose body is
    # exactly ``return SomeResponse(literal_args)`` with no parameters. When
    # set, the dispatcher skips handler invocation entirely and emits the
    # two cached messages directly. Targets the plaintext / static-JSON hot
    # path. ``None`` for any non-matching handler.
    _static_response: tuple[dict[str, Any], dict[str, Any]] | None = field(default=None, repr=False)
