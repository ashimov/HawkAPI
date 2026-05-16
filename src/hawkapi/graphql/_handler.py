"""GraphQL-over-HTTP wire handler."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, cast

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


# Match every top-level operation in a GraphQL document.
# A document can contain multiple operations: `query A {…} mutation B {…}`.
# The named-operation check (CWE-352, H-1) must inspect ALL operations, not
# just the first non-comment token.
_OPERATION_PATTERN = re.compile(
    r"\b(query|mutation|subscription)\b\s*([A-Za-z_][A-Za-z0-9_]*)?",
    re.IGNORECASE,
)


def _document_operations(query: str) -> list[tuple[str, str | None]]:
    """Return (operation_type, operation_name|None) for every operation in *query*.

    Strips line comments first. Shorthand documents (a single selection set
    starting with ``{``) implicitly map to a single ``query`` operation.
    """
    # Strip GraphQL line comments — they always start with '#' and end at \n.
    cleaned = re.sub(r"#[^\n]*", "", query)
    ops: list[tuple[str, str | None]] = []
    for m in _OPERATION_PATTERN.finditer(cleaned):
        ops.append((m.group(1).lower(), m.group(2) or None))
    if not ops and cleaned.lstrip().startswith("{"):
        ops.append(("query", None))
    return ops


def _has_non_query_for_get(query: str, operation_name: str | None) -> bool:
    """Return True if the document's selected operation is a mutation/subscription.

    CWE-352 fix: previously we only checked the first non-comment token, so
    ``query A {…} mutation B {…}`` with ``operationName=B`` snuck a mutation
    through GET. Now we look at every top-level operation and pick the one
    matching ``operation_name``; if no name is given we look at all of them
    (a document with a single operation is the only legal case in that mode).
    """
    ops = _document_operations(query)
    if not ops:
        # Unparseable — fail closed: disallow over GET, executor will return a
        # proper error message.
        return True
    if operation_name is None:
        # No operationName: spec requires exactly one operation in the
        # document. Reject GET if any of them is not a query.
        return any(op_type != "query" for op_type, _ in ops)
    for op_type, op_name in ops:
        if op_name == operation_name:
            return op_type != "query"
    # Named operation not found — let the executor handle the error.
    return False


def _document_depth(query: str) -> int:
    """Conservative selection-set depth estimate.

    Counts the maximum brace nesting in the document. Fast path before
    handing the query to the (potentially expensive) executor. Comments and
    strings are stripped to avoid spurious brace counts.
    """
    cleaned = re.sub(r"#[^\n]*", "", query)
    # Strip GraphQL string values so braces inside them are not counted.
    cleaned = re.sub(r'"(?:[^"\\]|\\.)*"', '""', cleaned)
    depth = 0
    max_depth = 0
    for ch in cleaned:
        if ch == "{":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif ch == "}":
            depth -= 1
            if depth < 0:
                depth = 0
    return max_depth


def _error_response(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"errors": [{"message": message}]}, status_code=status)


def make_graphql_handler(
    executor: GraphQLExecutor,
    *,
    graphiql: bool = False,
    allow_get: bool = True,
    context_factory: Callable[[Request], dict[str, Any] | Awaitable[dict[str, Any]]] | None = None,
    max_depth: int | None = 15,
    timeout_s: float | None = 30.0,
) -> Callable[[Request], Awaitable[Response | JSONResponse | HTMLResponse]]:
    """Return an async handler for the GraphQL endpoint.

    Defaults are hardened for production:

    * ``graphiql=False`` — opt-in for the in-browser explorer (CWE-200).
    * ``max_depth=15`` — reject selection sets nested more than 15 levels deep
      (CWE-770). Set ``None`` to disable.
    * ``timeout_s=30`` — wrap executor in ``asyncio.wait_for`` so a single
      malicious query cannot pin a worker indefinitely (CWE-770).
    """

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
            operation_name = request.query_params.get("operationName")
            if _has_non_query_for_get(query, operation_name):
                return _error_response("Mutations and subscriptions are not allowed over GET")
            variables_raw = request.query_params.get("variables")
            variables: dict[str, Any] | None = None
            if variables_raw:
                try:
                    variables = json.loads(variables_raw)
                except (ValueError, TypeError):
                    return _error_response("Invalid 'variables' JSON")

        elif method == "POST":
            try:
                payload = await request.json()
            except Exception:
                return _error_response("Malformed JSON body")
            if not isinstance(payload, dict):
                return _error_response("Request body must be a JSON object")
            payload = cast(dict[str, Any], payload)
            query = payload.get("query")
            if not query or not isinstance(query, str):
                return _error_response("Missing or invalid 'query' field")
            variables = payload.get("variables")
            operation_name = payload.get("operationName")
        else:
            return _error_response(f"Method {method} not allowed", 405)

        # Depth guard — short-circuit before invoking the executor (CWE-770).
        if max_depth is not None and _document_depth(query) > max_depth:
            return _error_response(f"Query exceeds maximum nesting depth ({max_depth})", status=400)

        # Build context
        app = request.scope.get("app")
        context: dict[str, Any] = {"request": request, "app": app}
        if context_factory is not None:
            extra = context_factory(request)
            if inspect.isawaitable(extra):
                extra = await extra
            if extra:
                context.update(extra)

        try:
            coro = executor(
                query=query,
                variables=variables if isinstance(variables, dict) else None,
                operation_name=operation_name if isinstance(operation_name, str) else None,
                context=context,
            )
            if timeout_s is not None:
                result = await asyncio.wait_for(coro, timeout=timeout_s)
            else:
                result = await coro
        except TimeoutError:
            return _error_response(f"Query exceeded execution timeout ({timeout_s}s)", status=504)

        # HTTP 400 when executor returned no data at all (pure request error)
        status = 400 if "data" not in result else 200
        return JSONResponse(result, status_code=status)

    return handler


__all__ = ["make_graphql_handler"]
