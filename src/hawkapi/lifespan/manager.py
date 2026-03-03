"""Lifespan manager — handles ASGI lifespan protocol.

Unlike FastAPI:
- on_startup/on_shutdown are NEVER silently ignored
- Both lifespan context manager AND decorator hooks work together
- Router-level hooks are supported
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from hawkapi._types import Receive, Scope, Send
from hawkapi.lifespan.hooks import HookRegistry

logger = logging.getLogger("hawkapi")


class LifespanManager:
    """Manages application lifecycle events."""

    def __init__(
        self,
        hook_registry: HookRegistry,
        lifespan: Callable[..., Any] | None = None,
    ) -> None:
        self._hooks = hook_registry
        self._lifespan = lifespan
        self._state: dict[str, Any] = {}

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle ASGI lifespan protocol messages."""
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                try:
                    await self._startup(scope)
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send(
                        {
                            "type": "lifespan.startup.failed",
                            "message": str(exc),
                        }
                    )
                    return

            elif message["type"] == "lifespan.shutdown":
                try:
                    await self._shutdown()
                except Exception:
                    logger.exception("Error during shutdown")
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _startup(self, scope: Scope) -> None:
        """Run all startup hooks + lifespan context manager."""
        # Run decorator-based hooks first
        await self._hooks.run_startup()

        # Enter lifespan context manager if provided
        if self._lifespan is not None:
            # The lifespan function should be an async context manager
            # or an async generator function decorated with @asynccontextmanager
            ctx = self._lifespan(self._get_app_proxy())
            if hasattr(ctx, "__aenter__"):
                self._state["_lifespan_ctx"] = ctx
                await ctx.__aenter__()

        # Populate scope state
        scope["state"] = self._state

    async def _shutdown(self) -> None:
        """Run shutdown in reverse order."""
        errors: list[Exception] = []

        # Exit lifespan context manager first
        ctx = self._state.pop("_lifespan_ctx", None)
        if ctx is not None:
            try:
                await ctx.__aexit__(None, None, None)
            except Exception as exc:
                logger.exception("Lifespan context manager exit error")
                errors.append(exc)

        # Then run decorator-based shutdown hooks (always, even if ctx failed)
        try:
            await self._hooks.run_shutdown()
        except ExceptionGroup as eg:
            errors.extend(eg.exceptions)
        except Exception as exc:
            errors.append(exc)

        if errors:
            raise ExceptionGroup("Shutdown errors", errors)

    def _get_app_proxy(self) -> _AppProxy:
        """Create a minimal app proxy for the lifespan function."""
        return _AppProxy(self._state)


class _AppProxy:
    """Minimal proxy passed to lifespan context managers."""

    __slots__ = ("state",)

    def __init__(self, state: dict[str, Any]) -> None:
        self.state = _StateProxy(state)


class _StateProxy:
    """Attribute-based proxy over the state dict."""

    __slots__ = ("_data",)

    _data: dict[str, Any]

    def __init__(self, data: dict[str, Any]) -> None:
        object.__setattr__(self, "_data", data)

    def __setattr__(self, name: str, value: Any) -> None:
        self._data[name] = value

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"State has no attribute {name!r}") from None
