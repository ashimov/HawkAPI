"""Internal type aliases and protocols for the ASGI interface."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = dict[str, Any]

Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

RouteHandler = Callable[..., Any]

# Sentinel for lazy-initialized fields
UNSET: Any = object()
