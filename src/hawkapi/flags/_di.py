"""DI helper — inject Flags via ``Depends(get_flags)``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from hawkapi.flags.base import EvalContext, Flags
from hawkapi.requests.request import Request


async def get_flags(request: Request) -> Flags:
    """DI helper — inject via ``Depends(get_flags)``.

    The returned ``Flags`` carries an empty ``EvalContext``. Operators who
    need user / tenant targeting MUST derive identity from an authenticated
    dependency and build their own ``Flags(app.flags, EvalContext(user_id=…))``.
    Previously this helper read ``X-User-Id`` / ``X-Tenant-Id`` headers
    directly — that trusted attacker-controlled input as the identity for
    flag targeting (CWE-290). The headers are still exposed on the context
    for *non-identity* targeting (region, A/B variant, …) but never used as
    a user or tenant identifier here.
    """
    app = request.scope.get("app")
    if app is None or getattr(app, "flags", None) is None:
        # Defensive: no app/flags bound — return a disabled-everywhere Flags.
        from hawkapi.flags.providers import StaticFlagProvider  # noqa: PLC0415

        return Flags(StaticFlagProvider({}), EvalContext())
    ctx = EvalContext(
        # user_id and tenant_id MUST NOT come from request headers — that
        # would trust client-supplied identity for flag targeting.
        user_id=None,
        tenant_id=None,
        # Headers satisfies the Mapping[str, str] protocol at runtime;
        # cast tells pyright the types align without changing behaviour.
        headers=cast(Mapping[str, str], request.headers),
    )
    return Flags(app.flags, ctx, app=app)


__all__ = ["get_flags"]
