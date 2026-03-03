"""OpenAPI documentation UI routes (Swagger UI, Scalar)."""

from __future__ import annotations

SWAGGER_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Swagger UI</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({{
            url: "{openapi_url}",
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            layout: "StandaloneLayout",
        }});
    </script>
</body>
</html>"""

SCALAR_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - API Reference</title>
</head>
<body>
    <script id="api-reference" data-url="{openapi_url}"></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>"""

REDOC_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - ReDoc</title>
</head>
<body>
    <redoc spec-url="{openapi_url}"></redoc>
    <script src="https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js"></script>
</body>
</html>"""


def get_swagger_ui_html(title: str, openapi_url: str) -> str:
    """Return a self-contained Swagger UI HTML page."""
    return SWAGGER_UI_HTML.format(title=title, openapi_url=openapi_url)


def get_scalar_ui_html(title: str, openapi_url: str) -> str:
    """Return a self-contained Scalar API Reference HTML page."""
    return SCALAR_UI_HTML.format(title=title, openapi_url=openapi_url)


def get_redoc_html(title: str, openapi_url: str) -> str:
    """Return a self-contained ReDoc HTML page."""
    return REDOC_HTML.format(title=title, openapi_url=openapi_url)
