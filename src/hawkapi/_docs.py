"""OpenAPI documentation route setup (extracted from app.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI


def setup_docs_routes(
    app: HawkAPI,
    openapi_url: str | None,
    docs_url: str | None,
    redoc_url: str | None,
    scalar_url: str | None,
) -> None:
    """Register OpenAPI documentation routes on the app."""
    from hawkapi.requests.request import Request
    from hawkapi.responses.response import Response

    if openapi_url is None:
        return

    @app.get(openapi_url, include_in_schema=False)
    async def openapi_schema(request: Request) -> dict[str, Any]:
        spec = app.openapi()
        root_path = request.scope.get("root_path", "")
        if root_path:
            spec = {**spec, "servers": [{"url": root_path}]}
        return spec

    _ = openapi_schema  # registered via decorator

    if docs_url is not None:

        @app.get(docs_url, include_in_schema=False)
        async def swagger_ui(request: Request) -> Response:
            from hawkapi.openapi.ui import get_swagger_ui_html

            root_path = request.scope.get("root_path", "")
            html = get_swagger_ui_html(app.title, root_path + openapi_url)
            return Response(
                content=html.encode(),
                status_code=200,
                content_type="text/html; charset=utf-8",
            )

        _ = swagger_ui  # registered via decorator

    if redoc_url is not None:

        @app.get(redoc_url, include_in_schema=False)
        async def redoc_ui(request: Request) -> Response:
            from hawkapi.openapi.ui import get_redoc_html

            root_path = request.scope.get("root_path", "")
            html = get_redoc_html(app.title, root_path + openapi_url)
            return Response(
                content=html.encode(),
                status_code=200,
                content_type="text/html; charset=utf-8",
            )

        _ = redoc_ui  # registered via decorator

    if scalar_url is not None:

        @app.get(scalar_url, include_in_schema=False)
        async def scalar_ui(request: Request) -> Response:
            from hawkapi.openapi.ui import get_scalar_ui_html

            root_path = request.scope.get("root_path", "")
            html = get_scalar_ui_html(app.title, root_path + openapi_url)
            return Response(
                content=html.encode(),
                status_code=200,
                content_type="text/html; charset=utf-8",
            )

        _ = scalar_ui  # registered via decorator
