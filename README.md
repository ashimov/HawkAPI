<p align="center">
  <img src="hawkapi.png" alt="HawkAPI" width="400">
</p>

<p align="center">
  <strong>High-performance Python web framework.</strong>
</p>

<p align="center">
  <a href="https://github.com/ashimov/HawkAPI/actions"><img src="https://github.com/ashimov/HawkAPI/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/hawkapi/"><img src="https://img.shields.io/pypi/v/hawkapi.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/hawkapi/"><img src="https://img.shields.io/pypi/pyversions/hawkapi.svg" alt="Python"></a>
  <a href="https://github.com/ashimov/HawkAPI/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ashimov/HawkAPI.svg" alt="License"></a>
  <a href="https://github.com/ashimov/HawkAPI"><img src="https://img.shields.io/badge/coverage-95%25-brightgreen.svg" alt="Coverage"></a>
  <a href="https://hawkapi.ashimov.com"><img src="https://img.shields.io/badge/docs-hawkapi.ashimov.com-blue.svg" alt="Docs"></a>
  <a href="https://pypi.org/project/hawkapi/"><img src="https://img.shields.io/pypi/dm/hawkapi.svg" alt="Downloads"></a>
</p>

---

Built from scratch on **msgspec** and a custom ASGI layer. No Starlette, no Pydantic (by default), no compromises on speed.

```python
from hawkapi import HawkAPI

app = HawkAPI()

@app.get("/")
async def hello():
    return {"message": "Hello, World!"}
```

```bash
hawkapi dev app:app
```

---

## Installation

```bash
pip install hawkapi
```

With extras:

```bash
pip install hawkapi[uvicorn]      # ASGI server
pip install hawkapi[pydantic]     # Optional Pydantic v2 support
pip install hawkapi[granian]      # Granian ASGI server
pip install hawkapi[otel]         # OpenTelemetry tracing
pip install hawkapi[all]          # Everything
```

**Requirements:** Python 3.12+ and msgspec >= 0.19.0.

---

## Quick Start

```python
import msgspec
from typing import Annotated
from hawkapi import HawkAPI

app = HawkAPI()

class CreateUser(msgspec.Struct):
    name: str
    email: str
    age: Annotated[int, msgspec.Meta(ge=0, le=150)]

class UserResponse(msgspec.Struct):
    id: int
    name: str
    email: str

@app.post("/users", status_code=201)
async def create_user(body: CreateUser) -> UserResponse:
    return UserResponse(id=1, name=body.name, email=body.email)
```

Type annotations drive validation, serialization, and OpenAPI schema generation. Invalid requests return [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) Problem Details:

```json
{
    "type": "https://hawkapi.ashimov.com/errors/validation",
    "title": "Validation Error",
    "status": 400,
    "detail": "1 validation error",
    "errors": [
        {"field": "age", "message": "Expected `int` >= 0", "value": -5}
    ]
}
```

---

## Core Features

### Routing

Radix tree router with typed path parameters (`str`, `int`, `float`, `uuid`), query parameter coercion, and ~500ns lookups:

```python
import uuid

@app.get("/users/{user_id:int}")
async def get_user(user_id: int):
    return {"id": user_id}

@app.get("/items/{item_id:uuid}")
async def get_item(item_id: uuid.UUID):
    return {"id": str(item_id)}

@app.get("/search")
async def search(q: str, limit: int = 10):
    return {"query": q, "limit": limit}
```

Both `def` and `async def` handlers work. Sync handlers run in a threadpool automatically.

#### Parameter Markers

Fine-tune parameter sources with `Body`, `Query`, `Header`, `Cookie`, and `Path`:

```python
from typing import Annotated
from hawkapi import Query, Header

@app.get("/items")
async def list_items(
    q: Annotated[str, Query(alias="search")],
    x_token: Annotated[str, Header()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return {"query": q, "token": x_token, "limit": limit}
```

### Dependency Injection

Full-featured DI container with three lifecycles — works in routes, background tasks, CLI commands, and tests:

```python
from hawkapi import HawkAPI, Container, Depends

container = Container()
container.singleton(Database, factory=lambda: Database(url=DB_URL))
container.scoped(Session, factory=lambda db=Depends(Database): db.session())

app = HawkAPI(container=container)

@app.get("/users/{user_id}")
async def get_user(user_id: int, session: Session):
    return await session.get(User, user_id)
```

| Lifecycle | Behavior |
|-----------|----------|
| `singleton` | Created once, shared globally |
| `scoped` | Created once per request |
| `transient` | Created fresh every injection |

Generator dependencies with `yield` manage resource lifecycles — cleanup code runs after the handler completes, even on exceptions:

```python
async def get_db():
    db = await create_connection()
    try:
        yield db
    finally:
        await db.close()

@app.get("/users")
async def list_users(db: Annotated[Connection, Depends(get_db)]):
    return await db.fetch_all("SELECT * FROM users")
```

#### DI Introspection

Inspect the container at runtime or export a Mermaid dependency graph:

```python
from hawkapi.di.introspection import container_graph, to_mermaid

print(container_graph(container))  # JSON-serializable dict of all providers
print(to_mermaid(container))       # Mermaid graph TD diagram
```

### OpenAPI Documentation

OpenAPI 3.1 schema auto-generated from type annotations:

| URL | UI |
|-----|-----|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/scalar` | Scalar |
| `/openapi.json` | Raw JSON schema |

All security schemes appear in the **Authorize** button automatically. Disable with `app = HawkAPI(docs_url=None, openapi_url=None)`.

### Response Model

Filter and validate responses — hide internal fields from API output:

```python
class UserFull(msgspec.Struct):
    id: int
    name: str
    email: str
    password_hash: str  # Internal field

class UserOut(msgspec.Struct):
    id: int
    name: str
    email: str

@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int):
    # password_hash is automatically filtered out
    return await db.get_user(user_id)
```

Works with both msgspec Structs and Pydantic models.

### Pagination

Built-in offset and cursor pagination helpers:

```python
from hawkapi import Page, PaginationParams, CursorPage, CursorParams

@app.get("/users")
async def list_users(params: PaginationParams) -> Page[UserOut]:
    users, total = await db.get_users(offset=params.offset, limit=params.limit)
    return Page(items=users, total=total, page=params.page, size=params.limit)

@app.get("/feed")
async def feed(params: CursorParams) -> CursorPage[PostOut]:
    posts, next_cursor = await db.get_feed(after=params.after, limit=params.limit)
    return CursorPage(items=posts, next_cursor=next_cursor)
```

### Middleware

```python
from hawkapi import Middleware, Request, Response

class AuthMiddleware(Middleware):
    async def before_request(self, request: Request) -> Request | Response:
        token = request.headers.get("authorization")
        if not token:
            return Response(status_code=401)
        request.state.user = verify_token(token)
        return request
```

#### Built-in Middleware

| Middleware | Description |
|-----------|-------------|
| `CORSMiddleware` | Cross-Origin Resource Sharing |
| `GZipMiddleware` | Response compression (streaming-aware) |
| `TimingMiddleware` | `Server-Timing` header |
| `TrustedHostMiddleware` | Host header validation |
| `TrustedProxyMiddleware` | X-Forwarded-For/Proto/Host from trusted CIDRs |
| `SecurityHeadersMiddleware` | X-Content-Type-Options, X-Frame-Options, etc. |
| `RequestIDMiddleware` | `X-Request-ID` header (generates UUID4 if missing) |
| `HTTPSRedirectMiddleware` | Redirect HTTP to HTTPS |
| `RateLimitMiddleware` | Token bucket rate limiting (429 + Retry-After) |
| `RequestLimitsMiddleware` | Max query string / header size enforcement |
| `CircuitBreakerMiddleware` | Three-state circuit breaker (per-path tracking) |
| `ErrorHandlerMiddleware` | Structured error handling pipeline |
| `PrometheusMiddleware` | Prometheus-compatible `/metrics` endpoint |
| `StructuredLoggingMiddleware` | JSON request/response logs |
| `DebugMiddleware` | `/_debug/routes` and `/_debug/stats` endpoints |
| `ObservabilityMiddleware` | All-in-one tracing, structured logs, metrics |

### Security

```python
from hawkapi import HTTPBearer, Depends

auth = HTTPBearer()

@app.get("/protected")
async def protected(credentials=Depends(auth)):
    return {"token": credentials.credentials}
```

Built-in schemes: `HTTPBearer`, `HTTPBasic`, `APIKeyHeader`, `APIKeyQuery`, `APIKeyCookie`, `OAuth2PasswordBearer`.

#### Declarative Permissions (RBAC)

```python
from hawkapi.security import PermissionPolicy

app.permission_policy = PermissionPolicy(
    resolver=get_user_permissions,
    mode="all",  # "all" = require all listed, "any" = require at least one
)

@app.get("/admin", permissions=["admin:read"])
async def admin_panel():
    return {"secret": "data"}
```

### Responses

```python
from hawkapi import (
    JSONResponse, HTMLResponse, PlainTextResponse,
    RedirectResponse, StreamingResponse, FileResponse,
    EventSourceResponse, ServerSentEvent,
)

# Server-Sent Events
async def events():
    yield ServerSentEvent(data="connected", event="open")
    yield ServerSentEvent(data='{"temp": 22.5}', event="reading")

return EventSourceResponse(events())
```

### WebSocket

```python
from hawkapi import WebSocket

@app.websocket("/ws")
async def websocket_handler(ws: WebSocket):
    await ws.accept()
    async for message in ws:
        await ws.send_text(f"Echo: {message}")
```

### HTTPException

Raise HTTP errors from anywhere with custom status, detail, and headers:

```python
from hawkapi import HTTPException

@app.get("/items/{item_id:int}")
async def get_item(item_id: int):
    item = await db.get(item_id)
    if item is None:
        raise HTTPException(404, detail="Item not found")
    return item

@app.get("/admin")
async def admin():
    raise HTTPException(
        401,
        detail="Token expired",
        headers={"WWW-Authenticate": "Bearer"},
    )
```

### Custom Exception Handlers

```python
@app.exception_handler(ValueError)
async def handle_value_error(request, exc):
    return Response(
        content=b'{"error": "bad value"}',
        status_code=400,
        content_type="application/json",
    )
```

### Background Tasks

```python
from hawkapi import BackgroundTasks

@app.post("/notify")
async def notify(tasks: BackgroundTasks):
    tasks.add_task(send_email, to="user@example.com", subject="Hello")
    return {"status": "queued"}
```

### Lifecycle Hooks

```python
@app.on_startup
async def startup():
    await db.connect()

@app.on_shutdown
async def shutdown():
    await db.disconnect()
```

### Body Size Limits

```python
app = HawkAPI(max_body_size=1024 * 1024)  # 1 MB (default: 10 MB)

# Returns 413 Payload Too Large when exceeded
```

### Routers and Controllers

```python
from hawkapi import Router

api = Router(prefix="/api/v1", tags=["api"])

@api.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(api)
```

Class-based controllers:

```python
from hawkapi import Controller, get, post

class UserController(Controller):
    prefix = "/users"
    tags = ["users"]

    @get("/")
    async def list_users(self):
        return []

    @post("/")
    async def create_user(self, body: CreateUser):
        return {"id": 1}

app.include_controller(UserController)
```

### Static Files

```python
from hawkapi import StaticFiles

app.mount("/static", StaticFiles(directory="static"))
app.mount("/site", StaticFiles(directory="public", html=True))
```

---

## Production Features

### Health Probes

Built-in Kubernetes-ready health endpoints:

```python
app = HawkAPI(readyz_url="/readyz", livez_url="/livez")

@app.readiness_check("database")
async def check_db():
    return await db.ping()
```

`/livez` always returns 200. `/readyz` runs all registered checks and returns 200 or 503 with aggregated results.

### Circuit Breaker

```python
from hawkapi.middleware.circuit_breaker import CircuitBreakerMiddleware

app.add_middleware(
    CircuitBreakerMiddleware,
    failure_threshold=5,
    recovery_timeout=30.0,
    half_open_max_calls=2,
)
```

Three-state circuit breaker (CLOSED → OPEN → HALF_OPEN) with per-path tracking. Returns 503 with `application/problem+json` when the circuit is open.

### Trusted Proxy

```python
from hawkapi.middleware.trusted_proxy import TrustedProxyMiddleware

app.add_middleware(
    TrustedProxyMiddleware,
    trusted_proxies=["10.0.0.0/8", "172.16.0.0/12"],
)
```

Extracts real client IP, scheme, and host from `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` — only from trusted CIDR ranges.

### Request Limits

```python
from hawkapi.middleware.request_limits import RequestLimitsMiddleware

app.add_middleware(
    RequestLimitsMiddleware,
    max_query_length=2048,
    max_headers_count=100,
    max_header_size=8192,
)
```

Rejects oversized requests at the ASGI scope level before body parsing. Returns 414 (query) or 431 (headers).

### Deprecation Headers

Mark routes as deprecated with RFC 8594 Sunset headers:

```python
@app.get("/v1/users", deprecated=True, sunset="2025-06-01", deprecation_link="https://docs.example.com/migration")
async def old_users():
    return []
```

Adds `Deprecation: true`, `Sunset`, and `Link` headers to responses automatically.

### Observability

```python
app = HawkAPI(observability=True)
```

Every request gets: request ID, structured JSON logs, metrics, and OpenTelemetry spans (if installed).

### Serverless Mode

```python
app = HawkAPI(serverless=True)
```

Disables documentation routes to minimize cold start. Combined with lazy imports, heavy modules load only on first use.

---

## API Versioning

```python
@app.get("/users", version="v1")
async def list_users_v1():
    return [{"id": 1, "name": "Alice"}]

@app.get("/users", version="v2")
async def list_users_v2():
    return [{"id": 1, "name": "Alice", "email": "alice@example.com"}]

# GET /v1/users -> v1 handler
# GET /v2/users -> v2 handler
```

Use `VersionRouter` to scope an entire router to a version:

```python
from hawkapi.routing import VersionRouter

v2 = VersionRouter("v2", prefix="/api")

@v2.get("/users")
async def list_users():  # -> /v2/api/users
    return []

app.include_router(v2)
```

---

## API Governance

### Breaking Changes Detection

Compare two OpenAPI specs and detect breaking changes:

```python
from hawkapi.openapi import detect_breaking_changes, format_report

old_spec = app.openapi(api_version="v1")
# ... make changes ...
new_spec = app.openapi(api_version="v1")

changes = detect_breaking_changes(old_spec, new_spec)
print(format_report(changes))
```

Detects: path removed, method removed, required parameter added, parameter removed, parameter type changed, response field removed, status code changed.

### OpenAPI Linter

```python
from hawkapi.openapi.linter import lint, format_lint_report

issues = lint(app.openapi())
print(format_lint_report(issues))
```

Built-in rules: `operation-id-required`, `operation-summary-required`, `response-description-required`. Custom rules are simple functions.

### Changelog Generator

```python
from hawkapi.openapi import detect_breaking_changes
from hawkapi.openapi.changelog import generate_changelog

changes = detect_breaking_changes(old_spec, new_spec)
print(generate_changelog(changes))
```

### Contract Smoke Tests

Auto-generate test cases from your OpenAPI schema:

```python
from hawkapi.testing.contract import generate_contract_tests

tests = generate_contract_tests(app)
for t in tests:
    response = client.request(t.method, t.path)
    assert response.status_code == t.expected_status
```

---

## Plugin API

Extend HawkAPI behavior with plugins:

```python
from hawkapi.plugins import Plugin

class AuditPlugin(Plugin):
    def on_route_registered(self, route):
        print(f"Route registered: {route.path}")
        return route

    def on_schema_generated(self, spec):
        spec["info"]["x-audited"] = True
        return spec

app.add_plugin(AuditPlugin())
```

---

## CLI

```bash
# Development server with auto-reload
hawkapi dev app:app
hawkapi dev app:app --host 0.0.0.0 --port 3000

# Detect API breaking changes
hawkapi diff app:app --base openapi-v1.json

# Lint OpenAPI spec
hawkapi check app:app

# Generate API changelog
hawkapi changelog app:app --base openapi-v1.json

# Scaffold a new project
hawkapi new myproject
hawkapi new myproject --docker
```

---

## Configuration

```python
from hawkapi import Settings, env_field

class AppSettings(Settings):
    db_url: str = env_field("DATABASE_URL")
    debug: bool = env_field("DEBUG", default=False)
    port: int = env_field("PORT", default=8000)
    allowed_hosts: list = env_field("ALLOWED_HOSTS", default=["*"])

settings = AppSettings.load(profile="production")
```

Supports `.env` files and environment profiles (`.env.development`, `.env.production`).

---

## Testing

Sync `TestClient` for pytest — no `async` needed:

```python
from hawkapi.testing import TestClient, override

client = TestClient(app)

def test_hello():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "Hello, World!"

def test_with_mock_db():
    with override(app, Database, mock_db):
        response = client.get("/users/1")
        assert response.status_code == 200
```

---

## Benchmarks

Tested on Apple M3 Pro, Python 3.13, msgspec 0.20. ASGI-level benchmarks (no HTTP server overhead — pure framework performance).

### Request/Response

| Scenario | Latency | Throughput |
| -------- | ------- | ---------- |
| Simple JSON (`GET /ping`) | 35 us | ~28,500 req/s |
| Path param (`GET /users/42`) | 39 us | ~25,600 req/s |
| Body decode (`POST /items`) | 40 us | ~25,000 req/s |
| Large response (100 items) | 57 us | ~17,500 req/s |

### Serialization

| Payload | Ops/sec | vs stdlib json |
| ------- | ------- | -------------- |
| Small dict (56 bytes) | 13.0M | **12.2x** |
| 100-item list (8.1 KB) | 189K | **6.0x** |
| 1000-item list (198 KB) | 8.7K | **6.1x** |

### Radix Tree Routing

Radix tree with 48 registered routes:

| Metric | Value |
|--------|-------|
| Lookups/sec | ~2,000,000 |
| Per lookup | ~486 ns |

Run benchmarks yourself:

```bash
python benchmarks/bench_request_response.py
python benchmarks/bench_serialization.py
python benchmarks/bench_routing.py
python benchmarks/bench_vs_fastapi.py
```

---

## Development

```bash
git clone https://github.com/ashimov/HawkAPI.git
cd HawkAPI
pip install -e ".[dev]"

# Run tests (816 tests)
pytest

# Lint and type check
ruff check src/ tests/
pyright src/
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
