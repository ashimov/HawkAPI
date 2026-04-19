"""DI helper — inject Flags via ``Depends(get_flags)``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from hawkapi.flags.base import EvalContext, Flags
from hawkapi.requests.request import Request


async def get_flags(request: Request) -> Flags:
    """DI helper — inject via ``Depends(get_flags)``."""
    app = request.scope.get("app")
    if app is None or getattr(app, "flags", None) is None:
        # Defensive: no app/flags bound — return a disabled-everywhere Flags.
        from hawkapi.flags.providers import StaticFlagProvider  # noqa: PLC0415

        return Flags(StaticFlagProvider({}), EvalContext())
    ctx = EvalContext(
        user_id=request.headers.get("x-user-id"),
        tenant_id=request.headers.get("x-tenant-id"),
        # Headers satisfies the Mapping[str, str] protocol at runtime;
        # cast tells pyright the types align without changing behaviour.
        headers=cast(Mapping[str, str], request.headers),
    )
    return Flags(app.flags, ctx, app=app)


__all__ = ["get_flags"]
