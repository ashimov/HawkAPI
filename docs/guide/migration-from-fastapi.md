# Migrating from FastAPI

This guide helps you migrate an existing FastAPI application to HawkAPI. Most concepts map directly — the biggest changes are msgspec instead of Pydantic and a proper DI container instead of ad-hoc `Depends()`.

## API Mapping Table

| FastAPI | HawkAPI | Notes |
|---------|---------|-------|
| `FastAPI()` | `HawkAPI()` | Same constructor pattern |
| `APIRouter()` | `Router()` | Same `include_router()` API |
| `Depends(func)` | `Depends(func)` | Same pattern, plus DI container |
| `HTTPException` | `HTTPException` | Same `status_code` + `detail` |
| `BaseModel` | `msgspec.Struct` | Faster serialization |
| `Query()` | `Query()` | Same `Annotated[]` pattern |
| `Path()` | `Path()` | Same `Annotated[]` pattern |
| `Header()` | `Header()` | Same `Annotated[]` pattern |
| `Body()` | `Body()` | Same `Annotated[]` pattern |
| `Cookie()` | `Cookie()` | Same `Annotated[]` pattern |
| `BackgroundTasks` | `BackgroundTasks` | Same API |
| `response_model=X` | `response_model=X` | Same |
| `status_code=201` | `status_code=201` | Same |
| `@app.middleware("http")` | `class M(Middleware)` | Class-based |
| `Request` | `Request` | Same interface |
| `Response` | `Response` | Same interface |
| `JSONResponse` | `JSONResponse` | Same interface |
| `TestClient` | `TestClient` | Same interface (httpx-based) |

## Step 1: Replace Imports

**Before (FastAPI):**

```python
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request
from fastapi import Query, Path, Header, Body, Cookie
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
```

**After (HawkAPI):**

```python
from hawkapi import HawkAPI, Router, Depends, HTTPException, Request
from hawkapi import Query, Path, Header, Body, Cookie
from hawkapi import JSONResponse, HTMLResponse
from hawkapi import TestClient
import msgspec
```

## Step 2: Replace Pydantic Models with msgspec Structs

**Before:**

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    name: str
    email: str
    age: int = Field(ge=0, le=150)
```

**After:**

```python
from typing import Annotated
import msgspec

class User(msgspec.Struct):
    name: str
    email: str
    age: Annotated[int, msgspec.Meta(ge=0, le=150)]
```

Key differences:
- `msgspec.Struct` replaces `BaseModel`
- `msgspec.Meta()` inside `Annotated[]` replaces `Field()` for validation
- No `.model_dump()` needed — HawkAPI serializes Structs directly
- Structs are faster to create and serialize than Pydantic models

## Step 3: Replace `app = FastAPI()` with `app = HawkAPI()`

**Before:**

```python
app = FastAPI(title="My API", version="1.0.0")
```

**After:**

```python
app = HawkAPI(title="My API", version="1.0.0")
```

Route decorators work identically:

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}

@app.post("/users", status_code=201)
async def create_user(body: User):
    return body
```

## Step 4: Replace APIRouter with Router

**Before:**

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["users"])

@router.get("/users")
async def list_users():
    ...

app.include_router(router)
```

**After:**

```python
from hawkapi import Router

router = Router(prefix="/api/v1", tags=["users"])

@router.get("/users")
async def list_users():
    ...

app.include_router(router)
```

## Step 5: Migrate Middleware

**Before (FastAPI):**

```python
@app.middleware("http")
async def add_timing(request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start)
    return response
```

**After (HawkAPI):**

```python
from hawkapi import Middleware, Response

class TimingMiddleware(Middleware):
    async def before_request(self, request):
        request.state.start_time = time.time()
        return None  # continue processing

    async def after_response(self, request, response):
        duration = time.time() - request.state.start_time
        response.headers["X-Process-Time"] = str(duration)
        return response

app.add_middleware(TimingMiddleware)
```

Or use raw ASGI mode for maximum performance:

```python
class TimingMiddleware(Middleware):
    async def __call__(self, scope, receive, send):
        start = time.time()
        await self.app(scope, receive, send)
        # Note: headers must be set before response starts
```

## Step 6: Migrate Dependency Injection

FastAPI's `Depends()` works the same way in HawkAPI:

```python
from hawkapi import Depends

async def get_db():
    db = await connect()
    try:
        yield db
    finally:
        await db.close()

@app.get("/users")
async def list_users(db = Depends(get_db)):
    return await db.fetch_all("SELECT * FROM users")
```

**HawkAPI also offers a DI container** for larger applications:

```python
from hawkapi import HawkAPI, Container

container = Container()
container.register(Database, factory=create_database, lifecycle="singleton")
container.register(UserService, lifecycle="scoped")

app = HawkAPI(container=container)

@app.get("/users")
async def list_users(service: UserService):
    # UserService auto-injected from container — no Depends() needed
    return await service.list_all()
```

## Step 7: Migrate Exception Handlers

**Before:**

```python
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
```

**After (same API):**

```python
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(content={"detail": str(exc)}, status_code=400)
```

## What's Different

### Serialization
HawkAPI uses **msgspec** instead of Pydantic. msgspec is 5-20x faster for JSON encoding/decoding. If you need Pydantic support, install `hawkapi[pydantic]` — both are supported.

### DI Container
HawkAPI includes a built-in DI container with proper lifecycle management (singleton, scoped, transient). This replaces ad-hoc `Depends()` chains for service injection.

### Middleware
HawkAPI uses class-based middleware with `before_request`/`after_response` hooks instead of the `call_next` pattern. This avoids background task issues and provides better control flow.

### Performance
HawkAPI pre-computes parameter resolution at route registration time. No `inspect.signature()` or `get_type_hints()` per request. Route matching uses a radix tree instead of linear search.

## What's the Same

- Route decorators (`@app.get`, `@app.post`, etc.)
- Path parameters with type conversion (`{user_id:int}`)
- `Annotated[]` parameter markers (`Query`, `Path`, `Header`, `Body`, `Cookie`)
- `Depends()` for function-based dependencies
- `BackgroundTasks` for post-response work
- `HTTPException` for error responses
- `TestClient` for testing (httpx-based)
- OpenAPI/Swagger UI auto-generation
- CORS, GZip, and other built-in middleware
