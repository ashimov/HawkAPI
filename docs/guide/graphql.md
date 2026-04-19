# GraphQL

HawkAPI ships a thin GraphQL-over-HTTP adapter. You bring your own schema library;
the framework handles the wire protocol, GraphiQL UI, and context injection.

## Quickstart

```python
from hawkapi import HawkAPI
from hawkapi.graphql.adapters import from_graphql_core
from graphql import GraphQLSchema, GraphQLObjectType, GraphQLField, GraphQLString

schema = GraphQLSchema(
    query=GraphQLObjectType(
        "Query",
        {"hello": GraphQLField(GraphQLString, resolve=lambda obj, info: "world")},
    )
)

app = HawkAPI()
app.mount_graphql("/graphql", executor=from_graphql_core(schema))
```

That's it. `POST /graphql` now accepts JSON bodies and `GET /graphql` opens the
GraphiQL explorer in a browser.

## Wire protocol

| Method | Content-Type       | Body / params                                               |
|--------|--------------------|-------------------------------------------------------------|
| POST   | `application/json` | `{"query": "...", "variables": {}, "operationName": "..."}` |
| GET    | —                  | `?query=...&variables=<url-encoded-json>&operationName=...` |

Responses are always `application/json` with `{"data": ..., "errors": [...]}`.

- HTTP **200** when the response contains a `data` key (including partial data with field errors).
- HTTP **400** when the request cannot be parsed (missing/invalid `query`, malformed JSON).
- Mutations over GET are rejected with HTTP **400**.

## Adapter usage

### graphql-core

```python
from hawkapi.graphql.adapters import from_graphql_core

executor = from_graphql_core(schema)
# optional middleware:
executor = from_graphql_core(schema, middleware=[my_middleware])
app.mount_graphql("/graphql", executor=executor)
```

`graphql-core` is imported lazily — it is only required if you actually use this adapter.

### Strawberry

```python
import strawberry
from hawkapi.graphql.adapters import from_strawberry

@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "world"

schema = strawberry.Schema(query=Query)
app.mount_graphql("/graphql", executor=from_strawberry(schema))
```

### Custom executor

Implement the `GraphQLExecutor` protocol directly for any other library:

```python
from typing import Any
from hawkapi.graphql import GraphQLExecutor

async def my_executor(
    query: str,
    variables: dict[str, Any] | None,
    operation_name: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    # call your schema here
    return {"data": {"hello": "world"}}

app.mount_graphql("/graphql", executor=my_executor)
```

## Context factory pattern

Inject custom values into the GraphQL context via `context_factory`:

```python
from hawkapi.requests import Request

def add_user_context(request: Request) -> dict:
    token = request.headers.get("authorization", "")
    return {"current_user": decode_token(token)}

app.mount_graphql("/graphql", executor=executor, context_factory=add_user_context)
```

The factory can also be **async**:

```python
async def async_context(request: Request) -> dict:
    user = await db.get_user(request.headers.get("x-user-id"))
    return {"user": user}
```

Inside a resolver the context is available via `info.context`:

```python
def resolve_me(root, info):
    return info.context["user"]
```

The base context always contains:

| Key       | Value                                   |
|-----------|-----------------------------------------|
| `request` | The current `hawkapi.requests.Request`  |
| `app`     | The `HawkAPI` application instance      |

## GraphiQL toggle

The interactive GraphiQL UI is served on `GET /graphql` when a browser `Accept`
header prefers `text/html`:

```python
# Enabled by default
app.mount_graphql("/graphql", executor=executor, graphiql=True)

# Disable for production APIs that don't need the explorer
app.mount_graphql("/graphql", executor=executor, graphiql=False)
```

## Disabling GET queries

Restrict the endpoint to POST-only:

```python
app.mount_graphql("/graphql", executor=executor, allow_get=False)
```

GET requests will receive HTTP **405** when `allow_get=False`.

## Roadmap

- Multipart request support (file uploads per the GraphQL multipart spec)
- Persisted queries
- WebSocket subscriptions (`graphql-ws` protocol)
- Per-field tracing / OpenTelemetry integration
