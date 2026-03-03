# DX Parity & Killer Features Design

**Date:** 2026-03-04
**Status:** Approved

## Goal

Close the developer-experience gap with FastAPI and introduce differentiating features that give HawkAPI a unique competitive edge.

---

## Section 1: Pagination Helpers

### API

```python
from hawkapi.pagination import Page, CursorPage, PaginationParams, CursorParams

@app.get("/users", response_model=Page[User])
async def list_users(pagination: PaginationParams):
    items = db.query(User).offset(pagination.offset).limit(pagination.limit)
    total = db.query(User).count()
    return Page(items=items, total=total, page=pagination.page, size=pagination.size)

@app.get("/feed", response_model=CursorPage[Post])
async def feed(cursor: CursorParams):
    posts = db.query(Post).where(Post.id > cursor.after).limit(cursor.limit)
    return CursorPage(items=posts, next_cursor=posts[-1].id if posts else None)
```

### Types

- `PaginationParams` (msgspec.Struct): `page: int = 1`, `size: int = 50`, `max_size: int = 100`. Injected via query params. Exposes computed `offset` and `limit` properties.
- `CursorParams` (msgspec.Struct): `after: str | None = None`, `limit: int = 50`, `max_limit: int = 100`. Injected via query params.
- `Page[T]` (Generic msgspec.Struct): `items: list[T]`, `total: int`, `page: int`, `size: int`, `pages: int` (computed).
- `CursorPage[T]` (Generic msgspec.Struct): `items: list[T]`, `next_cursor: str | None`, `has_more: bool` (computed).

### Files

- `src/hawkapi/pagination.py` (new)
- `tests/unit/test_pagination.py` (new)
- OpenAPI schemas auto-generated via msgspec introspection.

---

## Section 2: OpenAPI Examples

### API

```python
from hawkapi.params import Query, Path, Body

@app.post("/items")
async def create_item(
    body: Annotated[Item, Body(example={"name": "Widget", "price": 9.99})],
    q: Annotated[str, Query(example="search term")],
):
    ...
```

### Implementation

- Add `example: Any = None` field to `Query`, `Path`, `Body`, `Header`, `Cookie` marker classes.
- OpenAPI schema generator reads `example` from markers and emits `example` key in the corresponding parameter/requestBody schema.
- No runtime cost (example is schema-generation only).

### Files

- `src/hawkapi/params.py` (modify markers)
- `src/hawkapi/openapi/builder.py` (emit examples)
- `tests/unit/test_openapi_examples.py` (new)

---

## Section 3: Docker & Deployment Template

### Deliverables

- `templates/Dockerfile` multi-stage (builder + runtime), `uv`-based install, non-root user, health check.
- `templates/docker-compose.yml` with app + Postgres + Redis services.
- `docs/guide/deployment.md` covering: Dockerfile walkthrough, environment variables, Gunicorn/Uvicorn tuning, health checks, graceful shutdown.

### Scope

Template files live in `templates/` directory (not shipped in the package). Documentation in `docs/guide/`.

---

## Section 4: Migration from FastAPI Guide

### Deliverables

- `docs/guide/migration-from-fastapi.md`

### Contents

1. **API mapping table**: FastAPI concept -> HawkAPI equivalent (APIRouter -> Router, Depends -> Depends, HTTPException -> HTTPException, etc.)
2. **Step-by-step migration**: import changes, decorator changes, response model changes, middleware changes, DI container setup.
3. **What's different**: msgspec vs Pydantic, DI container vs ad-hoc Depends, route groups, constraint markers.
4. **What's missing** (with workarounds): WebSocket support status, OAuth2 utilities, background tasks differences.
5. **Before/after code examples** for each major pattern.

---

## Section 5: Killer Features

### 5A. Breaking Changes CI (`hawkapi-diff`)

- CLI tool: `hawkapi-diff old_module new_module`
- Compares OpenAPI schemas generated from two module references.
- Reports: removed endpoints, changed signatures, removed fields, type changes.
- Exit code 1 on breaking changes.
- Ships as `hawkapi[ci]` extra with a reusable GitHub Action in `templates/github-actions/api-diff.yml`.

**Files:** `src/hawkapi/cli/diff.py` (new), `tests/unit/test_api_diff.py` (new), `templates/github-actions/api-diff.yml` (new).

### 5B. Prometheus Metrics Export

- `hawkapi[metrics]` extra installs `prometheus-client`.
- `PrometheusMiddleware` collects: `http_requests_total{method,path,status}`, `http_request_duration_seconds{method,path}` histogram, `http_requests_in_progress{method}` gauge.
- `/metrics` endpoint auto-registered when middleware is added.
- Path normalization: uses route template (`/users/{id}`) not actual path to prevent cardinality explosion.

**Files:** `src/hawkapi/middleware/prometheus.py` (new), `tests/unit/test_prometheus.py` (new).

### 5C. Structured Logging

- `hawkapi[logging]` extra installs `structlog`.
- `StructuredLoggingMiddleware` emits JSON-structured request/response logs with: method, path, status, duration_ms, request_id (from header or generated UUID).
- Configurable log level, custom processors, request ID propagation.

**Files:** `src/hawkapi/middleware/logging.py` (new), `tests/unit/test_structured_logging.py` (new).

---

## Section 6: End-to-End Benchmarks

### Setup

- Benchmark runner: uvicorn + httptools, wrk or bombardier as load generator.
- Scenarios: JSON hello-world, path params, body parsing, large response (1000 items), database simulation (async sleep).
- Competitors: FastAPI, Starlette, Litestar.
- Metrics: requests/sec, p50/p95/p99 latency, memory usage.

### Deliverables

- `benchmarks/e2e/` directory with app files and runner script.
- GitHub Action in `.github/workflows/benchmark.yml` (runs on release tags or manual trigger).
- Results published as JSON artifact; README badge from latest run.

**Files:** `benchmarks/e2e/hawkapi_app.py`, `benchmarks/e2e/fastapi_app.py`, `benchmarks/e2e/run_benchmarks.py` (new), `.github/workflows/benchmark.yml` (new).

---

## Implementation Order

1. Pagination helpers (Section 1)
2. OpenAPI examples (Section 2)
3. Docker + deployment template (Section 3)
4. Migration guide (Section 4)
5. Breaking changes CI (Section 5A)
6. Prometheus metrics (Section 5B)
7. Structured logging (Section 5C)
8. E2E benchmarks (Section 6)
