"""GraphQL-over-HTTP wire handler."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any

from hawkapi.graphql._graphiql import GRAPHIQL_HTML
from hawkapi.graphql._protocol import GraphQLExecutor
from hawkapi.requests.request import Request
from hawkapi.responses.html_response import HTMLResponse
from hawkapi.responses.json_response import JSONResponse
from hawkapi.responses.response import Response


def _prefers_html(accept: str | None) -> bool:
    """Return True when the Accept header prefers text/html over application/json."""
    if not accept:
        return False
    html_q = 0.0
    json_q = 0.0
    for part in accept.split(","):
        part = part.strip()
        media, *params = part.split(";")
        media = media.strip().lower()
        q = 1.0
        for p in params:
            p = p.strip()
            if p.startswith("q="):
                try:
                    q = float(p[2:])
                except ValueError:
                    q = 1.0
        if media in ("text/html", "text/*", "*/*"):
            html_q = max(html_q, q)
        if media in ("application/json", "application/*", "*/*"):
            json_q = max(json_q, q)
    return html_q > json_q


def _is_mutation(query: str) -> bool:
    """Return True if the query's first meaningful token is 'mutation'."""
    stripped = query.lstrip()
    # Skip comment lines at the start
    while stripped.startswith("#"):
        nl = stripped.find("\n")
        stripped = stripped[nl + 1 :].lstrip() if nl != -1 else ""
    return stripped.lower().startswith("mutation")


def _error_response(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"errors": [{"message": message}]}, status_code=status)


def make_graphql_handler(
    executor: GraphQLExecutor,
    *,
    graphiql: bool = True,
    allow_get: bool = True,
    context_factory: Callable[[Request], dict[str, Any] | Awaitable[dict[str, Any]]] | None = None,
) -> Callable[[Request], Awaitable[Response | JSONResponse | HTMLResponse]]:
    """Return an async handler for the GraphQL endpoint."""

    async def handler(request: Request) -> Response | JSONResponse | HTMLResponse:
        method = request.method.upper()
        accept = request.headers.get("accept")

        # GraphiQL UI: GET + browser Accept
        if method == "GET" and _prefers_html(accept):
            if graphiql:
                return HTMLResponse(GRAPHIQL_HTML)
            return Response(status_code=404)

        if method == "GET":
            if not allow_get:
                return _error_response("GET method not allowed", 405)
            query = request.query_params.get("query")
            if not query:
                return _error_response("Missing 'query' parameter")
            if _is_mutation(query):
                return _error_response("Mutations are not allowed over GET")
            variables_raw = request.query_params.get("variables")
            variables: dict[str, Any] | None = None
            if variables_raw:
                try:
                    variables = json.loads(variables_raw)
                except (ValueError, TypeError):
                    return _error_response("Invalid 'variables' JSON")
            operation_name = request.query_params.get("operationName")

        elif method == "POST":
            try:
                payload = await request.json()
            except Exception:
                return _error_response("Malformed JSON body")
            if not isinstance(payload, dict):
                return _error_response("Request body must be a JSON object")
            query = payload.get("query")
            if not query or not isinstance(query, str):
                return _error_response("Missing or invalid 'query' field")
            variables = payload.get("variables")
            operation_name = payload.get("operationName")
        else:
            return _error_response(f"Method {method} not allowed", 405)

        # Build context
        app = request.scope.get("app")
        context: dict[str, Any] = {"request": request, "app": app}
        if context_factory is not None:
            extra = context_factory(request)
            if inspect.isawaitable(extra):
                extra = await extra
            if extra:
                context.update(extra)

        result = await executor(
            query=query,
            variables=variables if isinstance(variables, dict) else None,
            operation_name=operation_name if isinstance(operation_name, str) else None,
            context=context,
        )

        # HTTP 400 when executor returned no data at all (pure request error)
        status = 400 if "data" not in result else 200
        return JSONResponse(result, status_code=status)

    return handler


__all__ = ["make_graphql_handler"]
