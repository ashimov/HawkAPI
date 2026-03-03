<p align="center">
  <img src="hawkapi.png" alt="HawkAPI" width="400">
</p>

<p align="center">
  <strong>High-performance Python web framework — a faster alternative to FastAPI.</strong>
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

## Why HawkAPI?

Modern Python APIs deserve a framework that's fast by default, not fast with workarounds.

HawkAPI is built from zero on three principles:

**Speed without compromise** — msgspec handles JSON 6-12x faster than Pydantic. Radix tree routes resolve in ~500ns. Large responses serialize 7x faster than FastAPI. These aren't micro-optimizations — they compound under real traffic.

**Zero hidden dependencies** — No Starlette, no Pydantic (unless you want it), no version-pinning headaches. The entire ASGI layer is custom-built. You control the stack.

**DI that works everywhere** — Dependency injection isn't bolted onto the request cycle. Use it in routes, background workers, CLI commands, tests — same container, same lifecycles.

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

**Requirements:** Python 3.12+ and msgspec >= 0.19.0. No other runtime dependencies.

---

## Quick Start

### Hello World

```python
from hawkapi import HawkAPI

app = HawkAPI()

@app.get("/")
async def hello():
    return {"message": "Hello, World!"}
```

Run with the built-in CLI:

```bash
hawkapi dev app:app
```

Or with uvicorn:

```bash
uvicorn app:app --reload
```

### Routing with Validation

Type annotations drive automatic validation and OpenAPI schema generation:

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

Invalid requests get clean [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) Problem Details responses:

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

### Path and Query Parameters

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

Supported path parameter types: `str`, `int`, `float`, `uuid`.

### Sync and Async Handlers

Both `def` and `async def` handlers work. Sync handlers run in a threadpool automatically:

```python
@app.get("/sync")
def sync_handler():
    import time
    time.sleep(0.1)  # Won't block the event loop
    return {"mode": "sync"}

@app.get("/async")
async def async_handler():
    return {"mode": "async"}
```

---

## Features

### Dependency Injection

Full-featured DI container with three lifecycles:

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
| `transient` | Created fresh every time |

DI works outside routes too:

```python
async def cleanup_task():
    async with container.scope() as scope:
        session = await scope.resolve(Session)
        await session.execute("DELETE FROM expired_tokens")
```

### Generator Dependencies

Dependencies with `yield` for resource lifecycle management — code after `yield` runs as cleanup:

```python
from typing import Annotated
from hawkapi import Depends

async def get_db():
    db = await create_connection()
    try:
        yield db          # Handler receives db
    finally:
        await db.close()  # Runs after handler completes

@app.get("/users")
async def list_users(db: Annotated[Connection, Depends(get_db)]):
    return await db.fetch_all("SELECT * FROM users")
```

Both sync and async generators work. Multiple generators clean up in reverse order. Cleanup runs even if the handler raises an exception.

### response_model

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

### OpenAPI Documentation

OpenAPI 3.1 schema is auto-generated from type annotations and served at:

| URL | UI |
|-----|-----|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/scalar` | Scalar |
| `/openapi.json` | Raw JSON schema |

All security schemes appear in the **Authorize** button automatically.

Disable with:

```python
app = HawkAPI(docs_url=None, openapi_url=None)
```

### Middleware

```python
from hawkapi import Middleware, Request, Response
from hawkapi.middleware.cors import CORSMiddleware

# Built-in middleware
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Custom middleware with hooks
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
| `SecurityHeadersMiddleware` | X-Content-Type-Options, X-Frame-Options, etc. |
| `RequestIDMiddleware` | `X-Request-ID` header (generates UUID4 if missing) |
| `HTTPSRedirectMiddleware` | Redirect HTTP to HTTPS |
| `RateLimitMiddleware` | Per-client rate limiting (token bucket, 429 + Retry-After) |
| `ErrorHandlerMiddleware` | Structured error handling pipeline |
| `ObservabilityMiddleware` | All-in-one tracing, structured logs, metrics |

### Rate Limiting

```python
from hawkapi.middleware import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware, requests_per_second=10.0, burst=20)
```

Uses a token bucket algorithm. Blocked requests get `429 Too Many Requests` with a `Retry-After` header.

### Security

```python
from hawkapi import HTTPBearer, Depends

auth = HTTPBearer()

@app.get("/protected")
async def protected(credentials=Depends(auth)):
    return {"token": credentials.token}
```

#### Built-in Schemes

| Scheme | Description |
|--------|-------------|
| `HTTPBearer` | Authorization: Bearer token |
| `HTTPBasic` | Authorization: Basic base64 |
| `APIKeyHeader` | API key in a custom header |
| `APIKeyQuery` | API key in query parameter |
| `APIKeyCookie` | API key in a cookie |
| `OAuth2PasswordBearer` | OAuth2 password flow |

All schemes integrate with OpenAPI Authorize automatically.

#### HTTP Basic Example

```python
from typing import Annotated
from hawkapi import HTTPBasic, HTTPBasicCredentials, Depends, HTTPException

basic = HTTPBasic()

@app.get("/admin")
async def admin(creds: Annotated[HTTPBasicCredentials, Depends(basic)]):
    if creds.username != "admin" or creds.password != "secret":
        raise HTTPException(401)
    return {"user": creds.username}
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

Run tasks after the response is sent:

```python
from hawkapi import BackgroundTasks

@app.post("/notify")
async def notify(tasks: BackgroundTasks):
    tasks.add_task(send_email, to="user@example.com", subject="Hello")
    tasks.add_task(update_analytics, event="notification_sent")
    return {"status": "queued"}
```

Tasks run in order after the response. Failing tasks don't stop subsequent ones.

### Responses

HawkAPI provides specialized response types:

```python
from hawkapi import (
    JSONResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
    FileResponse,
    EventSourceResponse,
    ServerSentEvent,
)

# JSON (default for dict/struct returns)
return JSONResponse({"key": "value"}, status_code=200)

# HTML
return HTMLResponse("<h1>Hello</h1>")

# File download
return FileResponse("report.pdf")

# Streaming
async def generate():
    for i in range(100):
        yield f"chunk {i}\n".encode()

return StreamingResponse(generate(), content_type="text/plain")

# Server-Sent Events
async def events():
    yield ServerSentEvent(data="connected", event="open")
    yield ServerSentEvent(data='{"temp": 22.5}', event="reading")

return EventSourceResponse(events())
```

### Static Files

```python
from hawkapi import StaticFiles

app.mount("/static", StaticFiles(directory="static"))

# HTML mode — serves index.html for directories
app.mount("/site", StaticFiles(directory="public", html=True))
```

Path traversal attacks are blocked automatically.

### Routers

Organize routes into modules:

```python
from hawkapi import Router

api = Router(prefix="/api/v1", tags=["api"])

@api.get("/health")
async def health():
    return {"status": "ok"}

@api.get("/version")
async def version():
    return {"version": "1.0.0"}

app.include_router(api)
# GET /api/v1/health -> {"status": "ok"}
```

### Class-Based Controllers

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

### WebSocket

```python
from hawkapi import WebSocket

@app.websocket("/ws")
async def websocket_handler(ws: WebSocket):
    await ws.accept()
    async for message in ws:
        await ws.send_text(f"Echo: {message}")
```

### Lifecycle Hooks

```python
@app.on_startup
async def startup():
    print("Starting up...")

@app.on_shutdown
async def shutdown():
    print("Shutting down...")
```

### Configuration

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

### Testing

Sync `TestClient` for pytest — no `async` needed:

```python
from hawkapi.testing import TestClient

client = TestClient(app)

def test_hello():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "Hello, World!"

def test_create_user():
    response = client.post("/users", json={
        "name": "Alice",
        "email": "alice@example.com",
        "age": 30,
    })
    assert response.status_code == 201
```

#### DI Overrides for Tests

```python
from hawkapi.testing import override

with override(app, Database, mock_db):
    response = client.get("/users/1")
    assert response.status_code == 200
```

### Body Size Limits

Protect against oversized payloads:

```python
app = HawkAPI(max_body_size=1024 * 1024)  # 1 MB (default: 10 MB)

# Returns 413 Payload Too Large when exceeded
```

### API Versioning

Version routes declaratively — the version is baked into the path at registration time:

```python
from hawkapi import HawkAPI

app = HawkAPI()

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
from hawkapi import Router
from hawkapi.routing import VersionRouter

v2 = VersionRouter("v2", prefix="/api")

@v2.get("/users")
async def list_users():  # -> /v2/api/users
    return []

@v2.get("/items")
async def list_items():  # -> /v2/api/items
    return []

app.include_router(v2)
```

Generate per-version OpenAPI specs:

```python
full_spec = app.openapi()              # All routes
v1_spec = app.openapi(api_version="v1")  # Only v1 routes
```

#### Breaking Changes Detector

Compare two OpenAPI specs and detect breaking changes:

```python
from hawkapi.openapi import detect_breaking_changes, format_report

old_spec = app.openapi(api_version="v1")
# ... deploy changes ...
new_spec = app.openapi(api_version="v1")

changes = detect_breaking_changes(old_spec, new_spec)
print(format_report(changes))
# BREAKING CHANGES (1):
#   - [GET] /v1/users: Parameter 'page' was removed
```

Detects: path removed, method removed, required parameter added, parameter removed, parameter type changed, response field removed, status code changed.

### Declarative Permissions (RBAC)

Attach permissions directly to routes and enforce them with a pluggable policy:

```python
from hawkapi import HawkAPI, Request
from hawkapi.security import PermissionPolicy

async def get_user_permissions(request: Request) -> set[str]:
    token = request.headers.get("authorization", "")
    user = await decode_token(token)
    return user.permissions  # e.g. {"admin:read", "user:read"}

app = HawkAPI()
app.permission_policy = PermissionPolicy(
    resolver=get_user_permissions,
    mode="all",  # "all" = require all listed, "any" = require at least one
)

@app.get("/admin", permissions=["admin:read"])
async def admin_panel():
    return {"secret": "data"}

@app.get("/public")
async def public():  # No permissions — no check
    return {"data": "public"}
```

Returns `403 Forbidden` with details on missing permissions. Permissions appear as `x-permissions` in the OpenAPI spec.

### Observability

OpenTelemetry tracing, structured JSON logs, and request metrics — enabled with a single flag:

```python
app = HawkAPI(observability=True)
```

That's it. Every request gets:

- **Request ID** — generated or read from `x-request-id` header, echoed back in the response
- **Structured JSON logs** — timestamp, level, method, path, status, duration, request_id
- **Metrics** — request count, error count, average duration
- **Tracing** — OpenTelemetry spans (if `opentelemetry` is installed, zero cost otherwise)

Fine-tune with `ObservabilityConfig`:

```python
from hawkapi.observability import ObservabilityConfig

app = HawkAPI(
    observability=ObservabilityConfig(
        enable_tracing=False,   # Skip OTel spans
        enable_logging=True,
        enable_metrics=True,
        log_level="DEBUG",
        service_name="my-api",
        request_id_header="x-trace-id",
    )
)
```

Install OTel support:

```bash
pip install hawkapi[otel]
```

### Serverless Mode

Optimized for AWS Lambda, Google Cloud Functions, and similar environments:

```python
app = HawkAPI(serverless=True)
```

Serverless mode disables all documentation routes (`/docs`, `/redoc`, `/scalar`, `/openapi.json`) to eliminate unnecessary route registration and imports at startup.

Combined with lazy imports in the package (heavy modules like OpenAPI schema generation, UI templates, and WebSocket are loaded on first use, not at import time), this minimizes cold start overhead.

### Deprecated Routes

Mark endpoints as deprecated in the OpenAPI schema:

```python
@app.get("/v1/users", deprecated=True)
async def old_users():
    return []

@app.get("/v2/users")
async def new_users():
    return []
```

### CLI

```bash
# Development server with auto-reload
hawkapi dev app:app

# Custom host and port
hawkapi dev app:app --host 0.0.0.0 --port 3000

# Disable auto-reload
hawkapi dev app:app --no-reload
```

Requires `pip install hawkapi[uvicorn]`.

---

## Benchmarks

Tested on Apple M3 Pro, Python 3.13, msgspec 0.20.

### HawkAPI vs FastAPI

ASGI-level benchmarks (no HTTP server overhead):

| Scenario | HawkAPI | FastAPI | Speedup |
|----------|---------|---------|---------|
| Simple JSON (`GET /ping`) | 35 us | 43 us | **1.3x** |
| Path param (`GET /users/42`) | 39 us | 55 us | **1.4x** |
| Body decode (`POST /items`) | 40 us | 60 us | **1.5x** |
| Large response (100 items) | 57 us | 417 us | **7.3x** |

Average: **2.9x faster** than FastAPI.

### Serialization vs stdlib json

| Payload | HawkAPI (msgspec) | stdlib json | Speedup |
|---------|-------------------|-------------|---------|
| Small dict (56 bytes) | 13.0M ops/sec | 1.1M ops/sec | **12.2x** |
| 100-item list (8.1 KB) | 189K ops/sec | 32K ops/sec | **6.0x** |
| 1000-item list (198 KB) | 8.7K ops/sec | 1.4K ops/sec | **6.1x** |

### Routing

Radix tree with 48 registered routes:

| Metric | Value |
|--------|-------|
| Lookups/sec | ~2,000,000 |
| Per lookup | ~486 ns |

Run benchmarks yourself:

```bash
python benchmarks/bench_vs_fastapi.py
```

---

## Project Structure

```text
src/hawkapi/
    app.py              # ASGI application core
    cli.py              # CLI tool (hawkapi dev)
    exceptions.py       # HTTPException with Problem Details
    background.py       # BackgroundTasks
    staticfiles.py      # Static file serving
    routing/
        router.py           # Router with prefix/tags
        route.py            # Route dataclass
        version_router.py   # VersionRouter (auto version prefix)
        _radix_tree.py      # Radix tree for O(path) lookups
        controllers.py      # Class-based controllers
        param_converters.py # int/float/uuid converters
    requests/
        request.py      # Request with lazy parsing
        headers.py      # Case-insensitive header access
        query_params.py # Query string parsing
        form_data.py    # Multipart and URL-encoded forms
        state.py        # Request state container
    responses/
        response.py     # Base Response
        json.py         # JSONResponse
        html.py         # HTMLResponse
        streaming.py    # StreamingResponse
        file_response.py    # FileResponse
        sse.py          # Server-Sent Events
    middleware/
        _pipeline.py        # Middleware pipeline builder
        base.py             # Middleware base class with hooks
        cors.py             # CORS
        gzip.py             # GZip compression
        timing.py           # Server-Timing header
        trusted_host.py     # Host validation
        security_headers.py # Security headers
        request_id.py       # X-Request-ID
        https_redirect.py   # HTTP -> HTTPS
        rate_limit.py       # Token bucket rate limiter
        error_handler.py    # Error handling pipeline
    di/
        container.py    # DI container
        depends.py      # Depends() marker
        provider.py     # Singleton/scoped/transient providers
        resolver.py     # Parameter resolver with sub-deps
        scope.py        # Request-scoped container
    validation/
        decoder.py      # Cached msgspec JSON decoders
        constraints.py  # Body, Query, Header, Cookie, Path markers
        errors.py       # RFC 9457 validation errors
    serialization/
        encoder.py      # msgspec JSON encoder
        negotiation.py  # Content negotiation
    openapi/
        schema.py           # OpenAPI 3.1 schema generation
        breaking_changes.py # Breaking changes detector
        inspector.py        # Type-to-schema conversion
        models.py           # OpenAPI spec models
        ui.py               # Swagger/ReDoc/Scalar HTML
    websocket/
        connection.py   # WebSocket connection handler
    security/
        base.py         # SecurityScheme base
        permissions.py  # Declarative RBAC/permissions
        api_key.py      # API Key (header/query/cookie)
        http_bearer.py  # HTTP Bearer
        http_basic.py   # HTTP Basic
        oauth2.py       # OAuth2 Password Bearer
    observability/
        config.py       # ObservabilityConfig
        middleware.py    # ObservabilityMiddleware
        logger.py       # Structured JSON logger
        tracing.py      # Lazy OpenTelemetry integration
        metrics.py      # In-memory metrics collector
    config/
        settings.py     # Settings with env binding
        profiles.py     # Environment profiles
        env.py          # .env file parser
    testing/
        client.py       # Synchronous TestClient
        overrides.py    # DI override context manager
        plugin.py       # pytest plugin
    _compat/
        pydantic_adapter.py  # Optional Pydantic v2 support
```

---

## Development

```bash
# Clone and install
git clone https://github.com/ashimov/HawkAPI.git
cd hawkapi
pip install -e ".[dev]"

# Run tests (634 tests, 95% coverage)
pytest

# With coverage report
pytest --cov=hawkapi --cov-report=term-missing

# Lint
ruff check src/ tests/

# Type check (strict mode, 0 errors)
pyright src/
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
