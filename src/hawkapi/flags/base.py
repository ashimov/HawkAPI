"""Feature-flag protocol, context, and facade."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


class FlagDisabled(Exception):
    """Raised by Flags.require when a required flag evaluates falsy."""

    def __init__(self, key: str) -> None:
        super().__init__(f"feature flag {key!r} is disabled")
        self.key = key


@dataclass(frozen=True, slots=True)
class EvalContext:
    """Per-request targeting context for flag evaluation."""

    user_id: str | None = None
    tenant_id: str | None = None
    headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    attrs: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@runtime_checkable
class FlagProvider(Protocol):
    async def get_bool(
        self, key: str, default: bool, *, context: EvalContext | None = None
    ) -> bool: ...

    async def get_string(
        self, key: str, default: str, *, context: EvalContext | None = None
    ) -> str: ...

    async def get_number(
        self, key: str, default: float, *, context: EvalContext | None = None
    ) -> float: ...


class Flags:
    """Handler-facing facade returned by ``Depends(get_flags)``."""

    __slots__ = ("_provider", "_context", "_app")

    def __init__(
        self,
        provider: FlagProvider,
        context: EvalContext | None = None,
        *,
        app: Any = None,
    ) -> None:
        self._provider = provider
        self._context = context
        self._app = app  # for plugin hook dispatch

    async def bool(
        self, key: str, default: bool = False, *, context: EvalContext | None = None
    ) -> bool:
        ctx = context or self._context
        v = await self._provider.get_bool(key, default, context=ctx)
        self._dispatch_hook(key, v, ctx)
        return v

    async def string(
        self, key: str, default: str = "", *, context: EvalContext | None = None
    ) -> str:
        ctx = context or self._context
        v = await self._provider.get_string(key, default, context=ctx)
        self._dispatch_hook(key, v, ctx)
        return v

    async def number(
        self, key: str, default: float = 0.0, *, context: EvalContext | None = None
    ) -> float:
        ctx = context or self._context
        v = await self._provider.get_number(key, default, context=ctx)
        self._dispatch_hook(key, v, ctx)
        return v

    async def require(self, key: str, *, context: EvalContext | None = None) -> None:
        if not await self.bool(key, default=False, context=context):
            raise FlagDisabled(key)

    def _dispatch_hook(self, key: str, value: Any, context: EvalContext | None) -> None:
        """Fire on_flag_evaluated on any registered plugin."""
        app = self._app
        if app is None:
            return
        plugins = getattr(app, "_plugins", None) or getattr(app, "plugins", None) or []
        for plugin in plugins:
            hook = getattr(plugin, "on_flag_evaluated", None)
            if hook is None:
                continue
            try:
                result = hook(key, value, context)
                if result is not None and hasattr(result, "__await__"):
                    import asyncio  # noqa: PLC0415

                    asyncio.create_task(result)
            except Exception:  # noqa: BLE001,S110
                pass  # Hooks must never break evaluation.


__all__ = ["EvalContext", "FlagDisabled", "FlagProvider", "Flags"]
