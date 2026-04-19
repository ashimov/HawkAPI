# Tier 2 — GraphQL (thin mount) — design spec

**Status:** Approved — ready for implementation
**Date:** 2026-04-18
**Scope:** Ship `app.mount_graphql(path, executor=...)` — a thin GraphQL-over-HTTP adapter. Users bring their own schema library (graphql-core / strawberry / ariadne). Framework ships: wire-protocol handler, GraphiQL UI, context injection, and two optional adapters (graphql-core, strawberry) behind lazy imports.

---

## Goal

```python
from hawkapi import HawkAPI

app = HawkAPI()

async def executor(
    query: str,
    variables: dict | None,
    operation_name: str | None,
    context: dict,
) -> dict:
    # Return {"data": ..., "errors": [...]} — standard GraphQL response.
    ...

app.mount_graphql("/graphql", executor=executor)
```

Adapters for popular libraries — opt-in, lazy-imported:

```python
# graphql-core
from hawkapi.graphql.adapters import from_graphql_core
from graphql import build_schema
app.mount_graphql("/graphql", executor=from_graphql_core(build_schema("type Query { hello: String }")))

# strawberry
from hawkapi.graphql.adapters import from_strawberry
import strawberry
@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str: return "world"
app.mount_graphql("/graphql", executor=from_strawberry(strawberry.Schema(query=Query)))
```

Zero runtime deps on the default path — `hawkapi.graphql` does not import graphql-core or strawberry unless the adapters are called.

## Semantics

### Wire protocol (GraphQL over HTTP)

- **POST** `Content-Type: application/json` with JSON body `{"query": "...", "variables": {...}, "operationName": "..."}`. Primary path.
- **GET** with query string (`?query=...&variables=<urlencoded-json>&operationName=...`) — optional. Default enabled; opt out via `allow_get=False`. Mutations over GET are rejected with 400.
- **Response**:
  - `Content-Type: application/json`.
  - Body: `{"data": ..., "errors": [...]}` — per the GraphQL spec.
  - HTTP status: `200` when the response has any data or field-level errors; `400` when the request fails to parse/validate (no data produced).
- **Malformed JSON / missing query**: `400` with `{"errors": [{"message": "..."}]}`.

### `GraphQLExecutor` Protocol

```python
class GraphQLExecutor(Protocol):
    async def __call__(
        self,
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]: ...
```

A plain async callable; no class hierarchy needed. Returns a dict that can be JSON-encoded as-is.

### Context injection

On each request, the handler builds:

```python
context = {
    "request": request,
    "app": app,
}
if context_factory is not None:
    context.update(await _maybe_await(context_factory(request)))
```

User's `context_factory(request)` can return a dict (sync or async). The merged dict is passed to the executor.

### GraphiQL UI

Single HTML file bundled as a string (no third-party CDN at runtime beyond the browser fetching `graphiql` from jsdelivr — standard GraphiQL pattern). Served from the same path on `GET` when the `Accept` header prefers `text/html` over `application/json`. Toggle via `graphiql=True` (default `True`).

### HawkAPI method

New method on the `HawkAPI` class (`src/hawkapi/app.py`):

```python
def mount_graphql(
    self,
    path: str,
    *,
    executor: GraphQLExecutor,
    graphiql: bool = True,
    allow_get: bool = True,
    context_factory: Callable[[Request], dict | Awaitable[dict]] | None = None,
) -> None:
    """Register a GraphQL endpoint at ``path``."""
```

Internally the method builds a callable ASGI-like handler and registers it as a regular HawkAPI route (POST + optional GET).

## Adapters (`src/hawkapi/graphql/adapters.py`)

Two thin wrappers, each imports its target library only inside the function body:

### `from_graphql_core(schema, *, middleware=None) -> GraphQLExecutor`

```python
def from_graphql_core(schema, *, middleware=None):
    async def executor(query, variables, operation_name, context):
        from graphql import graphql
        result = await graphql(
            schema, query,
            variable_values=variables,
            operation_name=operation_name,
            context_value=context,
            middleware=middleware,
        )
        response = {}
        if result.data is not None:
            response["data"] = result.data
        if result.errors:
            response["errors"] = [
                {"message": str(e), "path": getattr(e, "path", None)} for e in result.errors
            ]
        return response
    return executor
```

### `from_strawberry(schema, *, root_value=None) -> GraphQLExecutor`

```python
def from_strawberry(schema, *, root_value=None):
    async def executor(query, variables, operation_name, context):
        result = await schema.execute(
            query,
            variable_values=variables,
            operation_name=operation_name,
            context_value=context,
            root_value=root_value,
        )
        response = {}
        if result.data is not None:
            response["data"] = result.data
        if result.errors:
            response["errors"] = [{"message": str(e)} for e in result.errors]
        return response
    return executor
```

## Module layout

```
src/hawkapi/graphql/
    __init__.py        # re-exports GraphQLExecutor Protocol + ParseError exception
    _handler.py        # core handler: parse, dispatch, format
    _graphiql.py       # GRAPHIQL_HTML constant string
    adapters.py        # from_graphql_core + from_strawberry (lazy imports)
```

All four files < 150 lines each.

## Tests — `tests/unit/test_graphql.py`

~15 tests using a minimal stub executor (no library dep):

```python
async def stub_executor(query, variables, operation_name, context):
    if "error" in query:
        return {"errors": [{"message": "stub error"}]}
    return {"data": {"query": query, "variables": variables or {}}}
```

- POST with valid JSON query → 200 + data echo.
- POST with variables → variables reach the executor.
- POST with missing `query` → 400.
- POST with malformed JSON → 400.
- GET with `?query=` → 200 when `allow_get=True`.
- GET with `?query=` → 405 when `allow_get=False`.
- GET with mutation query → 400 (by inspecting first non-whitespace token).
- `Accept: text/html` + `graphiql=True` → 200 + HTML.
- `Accept: text/html` + `graphiql=False` → 404 (or 406).
- `context_factory` return dict merged into context.
- `context_factory` returning a coroutine is awaited.
- `context["request"]` is a valid Request object.
- `from_graphql_core(schema)` returns a working executor (guarded by `pytest.importorskip("graphql")`).
- `from_strawberry(schema)` — guarded by `pytest.importorskip("strawberry")`.
- End-to-end integration via TestClient.

## Docs — `docs/guide/graphql.md`

Covers:
- Quickstart with stub executor.
- Adapter usage for graphql-core / strawberry.
- Context-factory pattern for injecting user info, DI.
- GraphiQL toggle.
- Roadmap (subscriptions, file uploads, APQ, batching, caching).

## Mkdocs nav + CHANGELOG

- `mkdocs.yml`: `- GraphQL: guide/graphql.md` after Feature flags, before Bulkhead.
- `CHANGELOG.md`: one `[Unreleased] ### Added` bullet.

## Out of scope

- **Subscriptions over WebSocket** (graphql-ws protocol) — v2.
- **File uploads (GraphQL multipart spec)** — v2.
- **Automatic Persisted Queries (APQ)** — v2.
- **Batching** (`[{query}, {query}]`) — v2.
- **Caching / `@cacheControl` directive** — v2.
- **Native schema DSL** — we won't re-invent graphql-core.
- **Auto-schema from HawkAPI routes** — separate huge project.

## Success criteria

1. `app.mount_graphql("/graphql", executor=fn)` handles POST + GET.
2. GraphiQL renders on HTML `Accept` when enabled.
3. Adapters work for graphql-core and strawberry behind `pytest.importorskip`.
4. Context dict contains `{"request": Request, "app": HawkAPI}` at minimum.
5. Malformed JSON → 400 with GraphQL-spec error shape.
6. Zero runtime deps on the default path.
7. Full suite + ruff + mkdocs strict clean.

## Files touched

- `src/hawkapi/graphql/__init__.py` — new
- `src/hawkapi/graphql/_handler.py` — new
- `src/hawkapi/graphql/_graphiql.py` — new
- `src/hawkapi/graphql/adapters.py` — new
- `src/hawkapi/app.py` — `mount_graphql` method
- `src/hawkapi/__init__.py` — re-exports
- `tests/unit/test_graphql.py` — new
- `docs/guide/graphql.md` — new
- `mkdocs.yml` — nav entry
- `CHANGELOG.md` — bullet

## Rollback

New module + new method + new docs. No existing paths change. Revert = delete `graphql/` package, revert one method on HawkAPI, revert doc diffs.
