"""Lifecycle hook registry."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("hawkapi")

LifecycleHook = Callable[[], Any]


class HookRegistry:
    """Collects startup and shutdown hooks."""

    __slots__ = ("_startup_hooks", "_shutdown_hooks")

    def __init__(self) -> None:
        self._startup_hooks: list[LifecycleHook] = []
        self._shutdown_hooks: list[LifecycleHook] = []

    def on_startup(self, func: LifecycleHook) -> LifecycleHook:
        """Register a startup hook (also works as a decorator)."""
        self._startup_hooks.append(func)
        return func

    def on_shutdown(self, func: LifecycleHook) -> LifecycleHook:
        """Register a shutdown hook (also works as a decorator)."""
        self._shutdown_hooks.append(func)
        return func

    @property
    def startup_hooks(self) -> list[LifecycleHook]:
        return self._startup_hooks

    @property
    def shutdown_hooks(self) -> list[LifecycleHook]:
        return self._shutdown_hooks

    async def run_startup(self) -> None:
        """Execute all startup hooks in registration order."""
        for hook in self._startup_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result

    async def run_shutdown(self) -> None:
        """Execute all shutdown hooks in reverse registration order."""
        errors: list[Exception] = []
        for hook in reversed(self._shutdown_hooks):
            try:
                result = hook()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.exception("Shutdown hook error: %s", hook)
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Shutdown hook errors", errors)

    def merge(self, other: HookRegistry) -> None:
        """Merge hooks from another registry (e.g., from a sub-router)."""
        self._startup_hooks.extend(other._startup_hooks)
        self._shutdown_hooks.extend(other._shutdown_hooks)
