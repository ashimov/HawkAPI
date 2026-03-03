# HawkAPI

**High-performance Python web framework — faster alternative to FastAPI.**

HawkAPI is built on `msgspec` for zero-copy serialization, a radix-tree router for O(1)-like lookups, and a lean middleware pipeline that avoids unnecessary allocations.

## Features

- **Radix-tree routing** — O(log n) path matching with zero allocations on hot paths
- **msgspec serialization** — 2-5x faster than Pydantic for JSON encode/decode
- **Dependency injection** — constructor-based DI with scoped lifetimes
- **OpenAPI 3.1** — auto-generated docs with Swagger UI, ReDoc, and Scalar
- **API versioning** — `VersionRouter` with per-version OpenAPI specs
- **Declarative permissions** — `PermissionPolicy` with pluggable resolvers
- **Observability** — one-flag tracing, structured logs, and metrics
- **WebSocket support** — first-class WebSocket handling
- **Middleware pipeline** — composable ASGI middleware with zero overhead
- **Serverless mode** — skip docs routes for faster cold starts

## Quick Example

```python
from hawkapi import HawkAPI

app = HawkAPI()

@app.get("/hello/{name}")
async def hello(name: str) -> dict:
    return {"message": f"Hello, {name}!"}
```

Run with any ASGI server:

```bash
uvicorn app:app --reload
```

## Installation

```bash
pip install hawkapi
```

With optional extras:

```bash
pip install "hawkapi[all]"         # pydantic + granian + uvloop + uvicorn + otel
pip install "hawkapi[otel]"        # OpenTelemetry tracing
pip install "hawkapi[pydantic]"    # Pydantic model support
```
