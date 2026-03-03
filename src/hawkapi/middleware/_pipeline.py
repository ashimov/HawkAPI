"""Middleware pipeline builder.

Builds the middleware chain once at startup (not per-request).
Each middleware wraps the next as an onion model.
"""

from __future__ import annotations

from typing import Any

from hawkapi._types import ASGIApp
from hawkapi.middleware.base import Middleware


def build_pipeline(
    middleware_stack: list[type[Middleware] | tuple[type[Middleware], dict[str, Any]]],
    app: ASGIApp,
) -> ASGIApp:
    """Build middleware chain. Applied in reverse order (first added = outermost).

    Each item is either a middleware class or a tuple of (class, kwargs).
    """
    handler = app
    for item in reversed(middleware_stack):
        if isinstance(item, tuple):
            cls, kwargs = item
            handler = cls(handler, **kwargs)
        else:
            handler = item(handler)
    return handler
