"""Health / liveness / readiness probe route setup (extracted from app.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI


def setup_health_routes(
    app: HawkAPI,
    health_url: str | None,
    readyz_url: str | None,
    livez_url: str | None,
) -> None:
    """Register health probe routes on the app."""
    if health_url is not None:
        _setup_health_route(app, health_url)
    if readyz_url is not None:
        _setup_readyz_route(app, readyz_url)
    if livez_url is not None:
        _setup_livez_route(app, livez_url)


def _setup_health_route(app: HawkAPI, health_url: str) -> None:
    """Register a lightweight health check endpoint."""
    from hawkapi.requests.request import Request

    @app.get(health_url, include_in_schema=False)
    async def healthz(request: Request) -> dict[str, str]:
        return {"status": "ok"}

    _ = healthz


def _setup_livez_route(app: HawkAPI, livez_url: str) -> None:
    """Register the liveness probe endpoint."""
    from hawkapi.requests.request import Request

    @app.get(livez_url, include_in_schema=False)
    async def livez(request: Request) -> dict[str, str]:
        return {"status": "alive"}

    _ = livez


def _setup_readyz_route(app: HawkAPI, readyz_url: str) -> None:
    """Register the readiness probe endpoint."""
    from hawkapi.requests.request import Request
    from hawkapi.responses.response import Response
    from hawkapi.serialization.encoder import encode_response

    @app.get(readyz_url, include_in_schema=False)
    async def readyz(request: Request) -> Response:
        checks: dict[str, dict[str, Any]] = {}
        all_ok = True
        for name, check_fn in app._readiness_checks.items():
            ok, detail = await check_fn()
            checks[name] = {"ok": ok, "detail": detail}
            if not ok:
                all_ok = False
        status = "ready" if all_ok else "not_ready"
        status_code = 200 if all_ok else 503
        body = encode_response({"status": status, "checks": checks})
        return Response(
            content=body,
            status_code=status_code,
            content_type="application/json",
        )

    _ = readyz
