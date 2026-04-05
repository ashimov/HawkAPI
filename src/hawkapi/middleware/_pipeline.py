"""Middleware pipeline builder.

Builds the middleware chain once at startup (not per-request).
Each middleware wraps the next as an onion model.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from hawkapi._types import ASGIApp
from hawkapi.middleware.base import Middleware


@dataclass(frozen=True, slots=True)
class MiddlewareEntry:
    """A middleware class with optional configuration."""

    cls: type[Middleware]
    kwargs: dict[str, Any] = dataclasses.field(default_factory=lambda: {})


def build_pipeline(
    middleware_stack: list[MiddlewareEntry],
    app: ASGIApp,
) -> ASGIApp:
    """Build middleware chain. Applied in reverse order (first added = outermost).

    Each entry contains a middleware class and optional kwargs.
    """
    handler = app
    for entry in reversed(middleware_stack):
        handler = entry.cls(handler, **entry.kwargs)
    return handler
