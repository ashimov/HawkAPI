# DX Parity & Killer Features Implementation Plan

**Goal:** Close the developer-experience gap with FastAPI and introduce differentiating features (pagination, OpenAPI examples, Prometheus, structured logging, migration guide, Docker template, API diff CI, e2e benchmarks).

**Architecture:** Each feature is a standalone module in `src/hawkapi/` with its own test file. Features that require external dependencies use optional extras (`hawkapi[metrics]`, `hawkapi[logging]`). All new public types are exposed via `hawkapi.__init__` lazy imports.

**Tech Stack:** Python 3.12+, msgspec (Structs + JSON), pytest + pytest-asyncio (TDD), prometheus-client (optional), structlog (optional).

---

## Task 1: Pagination Helpers — `Page[T]` and `CursorPage[T]`

**Files:**
- Create: `src/hawkapi/pagination.py`
- Create: `tests/unit/test_pagination.py`
- Modify: `src/hawkapi/__init__.py` (add lazy imports)

### Step 1: Write the failing tests

```python
# tests/unit/test_pagination.py
"""Tests for pagination helpers."""

import msgspec
import pytest

from hawkapi.pagination import CursorPage, CursorParams, Page, PaginationParams


class Item(msgspec.Struct):
    id: int
    name: str


class TestPaginationParams:
    def test_defaults(self):
        p = PaginationParams()
        assert p.page == 1
        assert p.size == 50

    def test_offset_and_limit(self):
        p = PaginationParams(page=3, size=20)
        assert p.offset == 40
        assert p.limit == 20

    def test_size_clamped_to_max(self):
        p = PaginationParams(size=200, max_size=100)
        assert p.limit == 100

    def test_page_minimum_is_1(self):
        p = PaginationParams(page=0)
        assert p.page == 1
        assert p.offset == 0


class TestPage:
    def test_basic_page(self):
        items = [Item(id=1, name="a"), Item(id=2, name="b")]
        page = Page(items=items, total=10, page=1, size=2)
        assert page.pages == 5
        assert len(page.items) == 2

    def test_pages_rounds_up(self):
        page = Page[Item](items=[], total=11, page=1, size=5)
        assert page.pages == 3

    def test_zero_total(self):
        page = Page[Item](items=[], total=0, page=1, size=10)
        assert page.pages == 0

    def test_serializable(self):
        page = Page(items=[Item(id=1, name="x")], total=1, page=1, size=10)
        data = msgspec.json.encode(page)
        assert b'"total":1' in data
        assert b'"pages":' in data


class TestCursorParams:
    def test_defaults(self):
        c = CursorParams()
        assert c.after is None
        assert c.limit == 50

    def test_limit_clamped(self):
        c = CursorParams(limit=500, max_limit=100)
        assert c.limit == 100


class TestCursorPage:
    def test_has_more_with_cursor(self):
        page = CursorPage(items=[Item(id=1, name="a")], next_cursor="abc")
        assert page.has_more is True

    def test_no_more_without_cursor(self):
        page = CursorPage[Item](items=[], next_cursor=None)
        assert page.has_more is False

    def test_serializable(self):
        page = CursorPage(items=[Item(id=1, name="x")], next_cursor="cur123")
        data = msgspec.json.encode(page)
        assert b'"next_cursor":"cur123"' in data
        assert b'"has_more":true' in data
```

### Step 2: Run tests to verify they fail

Run: `uv run pytest tests/unit/test_pagination.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hawkapi.pagination'`

### Step 3: Write minimal implementation

```python
# src/hawkapi/pagination.py
"""Pagination helpers — Page[T], CursorPage[T], PaginationParams, CursorParams."""

from __future__ import annotations

import math
from typing import Generic, TypeVar

import msgspec

T = TypeVar("T")


class PaginationParams(msgspec.Struct, frozen=True):
    """Offset-based pagination parameters (injected from query string)."""

    page: int = 1
    size: int = 50
    max_size: int = 100

    @property
    def offset(self) -> int:
        return (max(self.page, 1) - 1) * self.limit

    @property
    def limit(self) -> int:
        return min(self.size, self.max_size)


class CursorParams(msgspec.Struct, frozen=True):
    """Cursor-based pagination parameters (injected from query string)."""

    after: str | None = None
    limit: int = 50
    max_limit: int = 100

    def __post_init__(self) -> None:
        if self.limit > self.max_limit:
            object.__setattr__(self, "limit", self.max_limit)


class Page(msgspec.Struct, Generic[T]):
    """Offset-paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        if self.total == 0:
            return 0
        return math.ceil(self.total / self.size)


class CursorPage(msgspec.Struct, Generic[T]):
    """Cursor-paginated response wrapper."""

    items: list[T]
    next_cursor: str | None = None

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None
```

### Step 4: Run tests to verify they pass

Run: `uv run pytest tests/unit/test_pagination.py -v`
Expected: All PASS

### Step 5: Add lazy imports to `__init__.py`

In `src/hawkapi/__init__.py`:

1. Add to `_LAZY_IMPORTS` dict:
```python
    # pagination
    "Page": ("hawkapi.pagination", "Page"),
    "CursorPage": ("hawkapi.pagination", "CursorPage"),
    "PaginationParams": ("hawkapi.pagination", "PaginationParams"),
    "CursorParams": ("hawkapi.pagination", "CursorParams"),
```

2. Add to `TYPE_CHECKING` block:
```python
    from hawkapi.pagination import CursorPage, CursorParams, Page, PaginationParams
```

3. Add to `__all__` list (alphabetical order):
```python
    "CursorPage",
    "CursorParams",
    "Page",
    "PaginationParams",
```

### Step 6: Run full test suite

Run: `uv run pytest tests/ -x -q`
Expected: All 696+ tests pass

### Step 7: Lint and type check

Run: `uv run ruff check src/hawkapi/pagination.py tests/unit/test_pagination.py && uv run ruff format --check src/hawkapi/pagination.py tests/unit/test_pagination.py && uv run pyright src/hawkapi/pagination.py`
Expected: 0 errors

### Step 8: Commit

```bash
git add src/hawkapi/pagination.py tests/unit/test_pagination.py src/hawkapi/__init__.py
git commit -m "feat: add pagination helpers (Page[T], CursorPage[T], PaginationParams, CursorParams)"
```

---

## Task 2: OpenAPI Examples Support

**Files:**
- Modify: `src/hawkapi/validation/constraints.py` (add `example` field)
- Modify: `src/hawkapi/openapi/schema.py` (emit examples)
- Create: `tests/unit/test_openapi_examples.py`

### Step 1: Write the failing tests

```python
# tests/unit/test_openapi_examples.py
"""Tests for OpenAPI example support in parameter markers."""

from typing import Annotated

import msgspec
import pytest

from hawkapi import HawkAPI
from hawkapi.openapi.schema import generate_openapi
from hawkapi.validation.constraints import Body, Header, Path, Query


class _CreateUser(msgspec.Struct):
    name: str
    email: str


class TestOpenAPIExamples:
    def test_query_example(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/search")
        async def search(q: Annotated[str, Query(example="python")]):
            return {"q": q}

        spec = generate_openapi(app.routes)
        param = spec["paths"]["/search"]["get"]["parameters"][0]
        assert param["example"] == "python"

    def test_path_example(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/users/{user_id:int}")
        async def get_user(user_id: Annotated[int, Path(example=42)]):
            return {"id": user_id}

        spec = generate_openapi(app.routes)
        param = spec["paths"]["/users/{user_id}"]["get"]["parameters"][0]
        assert param["example"] == 42

    def test_header_example(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/protected")
        async def protected(x_token: Annotated[str, Header(example="secret-token")]):
            return {"ok": True}

        spec = generate_openapi(app.routes)
        param = spec["paths"]["/protected"]["get"]["parameters"][0]
        assert param["example"] == "secret-token"

    def test_body_example(self):
        app = HawkAPI(openapi_url=None)

        @app.post("/users")
        async def create_user(
            body: Annotated[_CreateUser, Body(example={"name": "Alice", "email": "a@b.com"})],
        ):
            return {"name": body.name}

        spec = generate_openapi(app.routes)
        rb = spec["paths"]["/users"]["post"]["requestBody"]
        assert rb["content"]["application/json"]["example"] == {
            "name": "Alice",
            "email": "a@b.com",
        }

    def test_no_example_omits_key(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/plain")
        async def plain(q: Annotated[str, Query()]):
            return {"q": q}

        spec = generate_openapi(app.routes)
        param = spec["paths"]["/plain"]["get"]["parameters"][0]
        assert "example" not in param
```

### Step 2: Run tests to verify they fail

Run: `uv run pytest tests/unit/test_openapi_examples.py -v`
Expected: FAIL — `TypeError: Query.__init__() got an unexpected keyword argument 'example'`

### Step 3: Add `example` field to `ParamMarker`

In `src/hawkapi/validation/constraints.py`, add `example` to `__slots__` and `__init__`:

```python
class ParamMarker:
    """Base class for parameter source markers."""

    __slots__ = ("alias", "description", "default", "default_factory", "example")

    def __init__(
        self,
        *,
        alias: str | None = None,
        description: str | None = None,
        default: Any = ...,
        default_factory: Any = None,
        example: Any = ...,
    ) -> None:
        self.alias = alias
        self.description = description
        self.default = default
        self.default_factory = default_factory
        self.example = example
```

### Step 4: Emit examples in OpenAPI schema generator

In `src/hawkapi/openapi/schema.py`:

1. In `_build_parameter()`, add example support:
```python
def _build_parameter(
    name: str,
    location: str,
    required: bool,
    annotation: Any,
    description: str | None = None,
    example: Any = ...,
) -> dict[str, Any]:
    param: dict[str, Any] = {
        "name": name,
        "in": location,
        "required": required,
        "schema": (
            type_to_schema(annotation)
            if annotation is not inspect.Parameter.empty
            else {"type": "string"}
        ),
    }
    if description:
        param["description"] = description
    if example is not ...:
        param["example"] = example
    return param
```

2. In `_build_operation()`, pass `example` from markers to `_build_parameter()` calls. For each marker type (Path, Query, Header, Cookie), add `example=marker.example` to the `_build_parameter()` call.

3. For Body markers with example, add to the request body content:
```python
if request_body_type is not None:
    body_schema = type_to_schema(request_body_type)
    # ... existing $ref logic ...
    content: dict[str, Any] = {"schema": body_schema}
    if body_example is not ...:
        content["example"] = body_example
    operation["requestBody"] = {
        "required": True,
        "content": {"application/json": content},
    }
```

Where `body_example` is captured from the Body marker in the parameter loop.

### Step 5: Run tests to verify they pass

Run: `uv run pytest tests/unit/test_openapi_examples.py -v`
Expected: All PASS

### Step 6: Run full test suite (ensure nothing broke)

Run: `uv run pytest tests/ -x -q`
Expected: All 696+ tests pass

### Step 7: Lint and type check

Run: `uv run ruff check src/hawkapi/validation/constraints.py src/hawkapi/openapi/schema.py tests/unit/test_openapi_examples.py && uv run pyright src/hawkapi/validation/constraints.py src/hawkapi/openapi/schema.py`
Expected: 0 errors

### Step 8: Commit

```bash
git add src/hawkapi/validation/constraints.py src/hawkapi/openapi/schema.py tests/unit/test_openapi_examples.py
git commit -m "feat: add OpenAPI example support to parameter markers"
```

---

## Task 3: Docker & Deployment Template

**Files:**
- Create: `templates/Dockerfile`
- Create: `templates/docker-compose.yml`
- Create: `docs/guide/deployment.md`

### Step 1: Create Dockerfile

```dockerfile
# templates/Dockerfile
# Multi-stage build for HawkAPI applications
# Usage: copy this file into your project root and customize

# --- Builder stage ---
FROM python:3.12-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-editable

COPY src/ src/

# --- Runtime stage ---
FROM python:3.12-slim AS runtime

RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

USER app

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Step 2: Create docker-compose.yml

```yaml
# templates/docker-compose.yml
# Development docker-compose for HawkAPI applications

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: app
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

### Step 3: Create deployment guide

```markdown
# docs/guide/deployment.md
# Deployment Guide

(Write a deployment guide covering: Dockerfile walkthrough, environment variables,
Uvicorn/Granian tuning tips, health check endpoints, graceful shutdown, docker-compose usage.)
```

Content should cover:
1. Quick start with the template Dockerfile
2. Environment variables pattern (using `hawkapi.config.Settings`)
3. Choosing a server: Uvicorn vs Granian
4. Worker count tuning (`2 * CPU + 1`)
5. Health check endpoint (`/healthz` auto-registered by HawkAPI)
6. Graceful shutdown (HawkAPI lifespan hooks)
7. Using docker-compose for local development
8. Production tips (non-root user, read-only filesystem, resource limits)

### Step 4: Commit

```bash
git add templates/Dockerfile templates/docker-compose.yml docs/guide/deployment.md
git commit -m "docs: add Docker template and deployment guide"
```

---

## Task 4: Migration from FastAPI Guide

**Files:**
- Create: `docs/guide/migration-from-fastapi.md`

### Step 1: Write the migration guide

The guide should contain these sections:

**1. API Mapping Table:**

| FastAPI | HawkAPI | Notes |
|---------|---------|-------|
| `FastAPI()` | `HawkAPI()` | Same constructor pattern |
| `APIRouter()` | `Router()` | Same `include_router()` pattern |
| `Depends()` | `Depends()` | Same, plus DI Container |
| `HTTPException` | `HTTPException` | Same signature |
| `BaseModel` | `msgspec.Struct` | Faster serialization |
| `Query()` | `Query()` | Same Annotated pattern |
| `Path()` | `Path()` | Same Annotated pattern |
| `Header()` | `Header()` | Same Annotated pattern |
| `Body()` | `Body()` | Same Annotated pattern |
| `BackgroundTasks` | `BackgroundTasks` | Same API |
| `@app.middleware("http")` | `class MyMiddleware(Middleware)` | Class-based |
| `response_model=X` | `response_model=X` | Same |

**2. Step-by-step migration examples (before/after code)**

**3. Key differences:** msgspec vs Pydantic, DI container, route groups, constraint markers, performance characteristics

**4. What's different with workarounds**

### Step 2: Commit

```bash
git add docs/guide/migration-from-fastapi.md
git commit -m "docs: add FastAPI migration guide"
```

---

## Task 5: Breaking Changes CI (`hawkapi-diff`)

**Files:**
- Create: `src/hawkapi/cli/diff.py`
- Create: `tests/unit/test_api_diff.py`
- Create: `templates/github-actions/api-diff.yml`
- Modify: `pyproject.toml` (add `[project.scripts]` entry)

**Note:** HawkAPI already has a `detect_breaking_changes()` function in `src/hawkapi/openapi/breaking_changes.py`. The CLI tool wraps this existing functionality.

### Step 1: Read existing breaking_changes module

Read `src/hawkapi/openapi/breaking_changes.py` to understand the existing API:
- `detect_breaking_changes(old_spec, new_spec) -> list[Change]`
- `Change` dataclass with `path`, `method`, `description`, `change_type`, `severity`
- `ChangeType` enum: ENDPOINT_REMOVED, METHOD_REMOVED, PARAMETER_ADDED, etc.
- `Severity` enum: BREAKING, WARNING, INFO

### Step 2: Write failing tests

```python
# tests/unit/test_api_diff.py
"""Tests for the hawkapi-diff CLI tool."""

import pytest

from hawkapi.cli.diff import diff_specs, load_app_spec


class TestDiffSpecs:
    def test_no_changes(self):
        spec = {"openapi": "3.1.0", "paths": {"/ping": {"get": {"responses": {"200": {}}}}}}
        changes = diff_specs(spec, spec)
        assert len(changes) == 0

    def test_removed_endpoint_is_breaking(self):
        old = {"openapi": "3.1.0", "paths": {"/a": {"get": {"responses": {"200": {}}}}}}
        new = {"openapi": "3.1.0", "paths": {}}
        changes = diff_specs(old, new)
        assert any(c.severity.name == "BREAKING" for c in changes)

    def test_added_endpoint_is_info(self):
        old = {"openapi": "3.1.0", "paths": {}}
        new = {"openapi": "3.1.0", "paths": {"/a": {"get": {"responses": {"200": {}}}}}}
        changes = diff_specs(old, new)
        breaking = [c for c in changes if c.severity.name == "BREAKING"]
        assert len(breaking) == 0


class TestLoadAppSpec:
    def test_load_from_module(self):
        """Test loading OpenAPI spec from a HawkAPI app module reference."""
        # Create a temporary module with a HawkAPI app
        import types

        mod = types.ModuleType("_test_mod")
        from hawkapi import HawkAPI

        app = HawkAPI(openapi_url=None)

        @app.get("/hello")
        async def hello():
            return {"msg": "hi"}

        mod.app = app
        spec = load_app_spec(mod, "app")
        assert "/hello" in spec["paths"]
```

### Step 3: Run tests to verify they fail

Run: `uv run pytest tests/unit/test_api_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hawkapi.cli.diff'`

### Step 4: Implement `src/hawkapi/cli/diff.py`

```python
# src/hawkapi/cli/diff.py
"""CLI tool for detecting API breaking changes between two HawkAPI app versions."""

from __future__ import annotations

import argparse
import importlib
import sys
from types import ModuleType
from typing import Any

from hawkapi.openapi.breaking_changes import Change, detect_breaking_changes
from hawkapi.openapi.schema import generate_openapi


def load_app_spec(
    module: ModuleType, attr_name: str = "app"
) -> dict[str, Any]:
    """Load a HawkAPI app from a module and generate its OpenAPI spec."""
    app = getattr(module, attr_name)
    return generate_openapi(app.routes, title=app.title, version=app.version)


def diff_specs(
    old_spec: dict[str, Any], new_spec: dict[str, Any]
) -> list[Change]:
    """Compare two OpenAPI specs and return changes."""
    return detect_breaking_changes(old_spec, new_spec)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for hawkapi-diff."""
    parser = argparse.ArgumentParser(
        prog="hawkapi-diff",
        description="Detect breaking API changes between two HawkAPI app versions.",
    )
    parser.add_argument("old", help="Old module:attr (e.g. myapp.main:app)")
    parser.add_argument("new", help="New module:attr (e.g. myapp.main:app)")
    args = parser.parse_args(argv)

    old_module_path, old_attr = _parse_ref(args.old)
    new_module_path, new_attr = _parse_ref(args.new)

    old_mod = importlib.import_module(old_module_path)
    new_mod = importlib.import_module(new_module_path)

    old_spec = load_app_spec(old_mod, old_attr)
    new_spec = load_app_spec(new_mod, new_attr)

    changes = diff_specs(old_spec, new_spec)

    if not changes:
        print("No API changes detected.")
        return 0

    has_breaking = False
    for change in changes:
        severity = change.severity.name
        if severity == "BREAKING":
            has_breaking = True
        print(f"[{severity}] {change.description}")

    return 1 if has_breaking else 0


def _parse_ref(ref: str) -> tuple[str, str]:
    """Parse 'module.path:attr' into (module_path, attr_name)."""
    if ":" in ref:
        module_path, attr = ref.rsplit(":", 1)
        return module_path, attr
    return ref, "app"


if __name__ == "__main__":
    sys.exit(main())
```

### Step 5: Add CLI entry point to pyproject.toml

In `pyproject.toml` under `[project.scripts]`:
```toml
[project.scripts]
hawkapi = "hawkapi.cli:main"
hawkapi-diff = "hawkapi.cli.diff:main"
```

### Step 6: Run tests to verify they pass

Run: `uv run pytest tests/unit/test_api_diff.py -v`
Expected: All PASS

### Step 7: Create GitHub Action template

```yaml
# templates/github-actions/api-diff.yml
name: API Breaking Changes Check

on:
  pull_request:
    paths:
      - "src/**"

jobs:
  api-diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install hawkapi

      - name: Check for breaking changes
        run: |
          git stash
          OLD_SPEC=$(python -c "
          from myapp.main import app
          from hawkapi.openapi.schema import generate_openapi
          import json
          print(json.dumps(generate_openapi(app.routes)))
          ")
          git stash pop

          NEW_SPEC=$(python -c "
          from myapp.main import app
          from hawkapi.openapi.schema import generate_openapi
          import json
          print(json.dumps(generate_openapi(app.routes)))
          ")

          python -c "
          import json, sys
          from hawkapi.openapi.breaking_changes import detect_breaking_changes
          old = json.loads('$OLD_SPEC')
          new = json.loads('$NEW_SPEC')
          changes = detect_breaking_changes(old, new)
          for c in changes:
              print(f'[{c.severity.name}] {c.description}')
          sys.exit(1 if any(c.severity.name == 'BREAKING' for c in changes) else 0)
          "
```

### Step 8: Lint and type check

Run: `uv run ruff check src/hawkapi/cli/diff.py tests/unit/test_api_diff.py && uv run pyright src/hawkapi/cli/diff.py`
Expected: 0 errors

### Step 9: Run full test suite

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

### Step 10: Commit

```bash
git add src/hawkapi/cli/diff.py tests/unit/test_api_diff.py templates/github-actions/api-diff.yml pyproject.toml
git commit -m "feat: add hawkapi-diff CLI for API breaking changes detection"
```

---

## Task 6: Prometheus Metrics Middleware

**Files:**
- Create: `src/hawkapi/middleware/prometheus.py`
- Create: `tests/unit/test_prometheus.py`
- Modify: `pyproject.toml` (add `metrics` extra)
- Modify: `src/hawkapi/__init__.py` (add lazy import)

### Step 1: Add `metrics` optional dependency to pyproject.toml

In `pyproject.toml` under `[project.optional-dependencies]`:
```toml
metrics = ["prometheus-client>=0.20"]
```

Also update `all` extra:
```toml
all = ["hawkapi[pydantic,granian,uvloop,uvicorn,otel,metrics]"]
```

### Step 2: Install the dependency

Run: `uv sync --extra metrics --extra dev`

### Step 3: Write failing tests

```python
# tests/unit/test_prometheus.py
"""Tests for Prometheus metrics middleware."""

import pytest

pytest.importorskip("prometheus_client")

from hawkapi import HawkAPI
from hawkapi.middleware.prometheus import PrometheusMiddleware


async def _call_app(app, method, path, headers=None, body=b""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestPrometheusMiddleware:
    @pytest.fixture(autouse=True)
    def _reset_registry(self):
        """Reset Prometheus registry between tests."""
        from prometheus_client import REGISTRY, CollectorRegistry

        # Use a fresh registry per test
        self.registry = CollectorRegistry()

    @pytest.mark.asyncio
    async def test_metrics_endpoint_registered(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(PrometheusMiddleware, registry=self.registry)

        @app.get("/hello")
        async def hello():
            return {"msg": "hi"}

        resp = await _call_app(app, "GET", "/metrics")
        assert resp["status"] == 200
        assert b"http_requests_total" in resp["body"]

    @pytest.mark.asyncio
    async def test_request_counted(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(PrometheusMiddleware, registry=self.registry)

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        await _call_app(app, "GET", "/ping")
        await _call_app(app, "GET", "/ping")

        resp = await _call_app(app, "GET", "/metrics")
        body = resp["body"].decode()
        assert "http_requests_total" in body

    @pytest.mark.asyncio
    async def test_duration_histogram(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(PrometheusMiddleware, registry=self.registry)

        @app.get("/slow")
        async def slow():
            return {"ok": True}

        await _call_app(app, "GET", "/slow")

        resp = await _call_app(app, "GET", "/metrics")
        body = resp["body"].decode()
        assert "http_request_duration_seconds" in body

    @pytest.mark.asyncio
    async def test_skips_non_http(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(PrometheusMiddleware, registry=self.registry)

        scope = {"type": "websocket", "path": "/ws"}
        sent = []

        # Should pass through without error
        # (no websocket handler registered, but middleware shouldn't crash)
```

### Step 4: Run tests to verify they fail

Run: `uv run pytest tests/unit/test_prometheus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hawkapi.middleware.prometheus'`

### Step 5: Implement PrometheusMiddleware

```python
# src/hawkapi/middleware/prometheus.py
"""Prometheus metrics middleware for HawkAPI."""

from __future__ import annotations

import time
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class PrometheusMiddleware(Middleware):
    """Collect HTTP metrics and expose a /metrics endpoint.

    Tracks:
    - http_requests_total{method, path, status} — counter
    - http_request_duration_seconds{method, path} — histogram
    - http_requests_in_progress{method} — gauge

    Usage:
        app.add_middleware(PrometheusMiddleware)
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics_path: str = "/metrics",
        registry: Any = None,
    ) -> None:
        super().__init__(app)
        from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

        self._metrics_path = metrics_path
        self._registry = registry or CollectorRegistry()

        self._requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
            registry=self._registry,
        )
        self._request_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "path"],
            registry=self._registry,
        )
        self._in_progress = Gauge(
            "http_requests_in_progress",
            "HTTP requests currently in progress",
            ["method"],
            registry=self._registry,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]

        # Serve /metrics endpoint
        if path == self._metrics_path:
            await self._serve_metrics(scope, receive, send)
            return

        method: str = scope["method"]
        # Use route template if available, fall back to path
        route_path = scope.get("route_path", path)

        self._in_progress.labels(method=method).inc()
        start = time.monotonic()
        status_code = 500

        async def metrics_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, metrics_send)
        finally:
            duration = time.monotonic() - start
            self._requests_total.labels(
                method=method, path=route_path, status=str(status_code)
            ).inc()
            self._request_duration.labels(method=method, path=route_path).observe(duration)
            self._in_progress.labels(method=method).dec()

    async def _serve_metrics(self, scope: Scope, receive: Receive, send: Send) -> None:
        from prometheus_client import generate_latest

        body = generate_latest(self._registry)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain; version=0.0.4; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
```

### Step 6: Run tests to verify they pass

Run: `uv run pytest tests/unit/test_prometheus.py -v`
Expected: All PASS

### Step 7: Add lazy import to `__init__.py`

Add to `_LAZY_IMPORTS`:
```python
    "PrometheusMiddleware": ("hawkapi.middleware.prometheus", "PrometheusMiddleware"),
```

Add to `TYPE_CHECKING`:
```python
    from hawkapi.middleware.prometheus import PrometheusMiddleware
```

Add to `__all__`:
```python
    "PrometheusMiddleware",
```

### Step 8: Lint, type check, full test suite

Run: `uv run ruff check src/hawkapi/middleware/prometheus.py tests/unit/test_prometheus.py && uv run pyright src/hawkapi/middleware/prometheus.py && uv run pytest tests/ -x -q`
Expected: 0 errors, all tests pass

### Step 9: Commit

```bash
git add src/hawkapi/middleware/prometheus.py tests/unit/test_prometheus.py pyproject.toml src/hawkapi/__init__.py
git commit -m "feat: add Prometheus metrics middleware (hawkapi[metrics])"
```

---

## Task 7: Structured Logging Middleware

**Files:**
- Create: `src/hawkapi/middleware/logging.py`
- Create: `tests/unit/test_structured_logging.py`
- Modify: `pyproject.toml` (add `logging` extra)
- Modify: `src/hawkapi/__init__.py` (add lazy import)

### Step 1: Add `logging` optional dependency

In `pyproject.toml` under `[project.optional-dependencies]`:
```toml
logging = ["structlog>=24.0"]
```

Update `all` extra:
```toml
all = ["hawkapi[pydantic,granian,uvloop,uvicorn,otel,metrics,logging]"]
```

### Step 2: Install the dependency

Run: `uv sync --extra logging --extra dev`

### Step 3: Write failing tests

```python
# tests/unit/test_structured_logging.py
"""Tests for structured logging middleware."""

import json

import pytest

pytest.importorskip("structlog")

from hawkapi import HawkAPI
from hawkapi.middleware.structured_logging import StructuredLoggingMiddleware


async def _call_app(app, method, path, headers=None, body=b""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestStructuredLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_adds_request_id_header(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(StructuredLoggingMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test")
        assert resp["status"] == 200
        assert (b"x-request-id", resp["headers"].get(b"x-request-id", b"")) != (
            b"x-request-id",
            b"",
        )

    @pytest.mark.asyncio
    async def test_preserves_incoming_request_id(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(StructuredLoggingMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(
            app,
            "GET",
            "/test",
            headers=[(b"x-request-id", b"custom-id-123")],
        )
        assert resp["headers"].get(b"x-request-id") == b"custom-id-123"

    @pytest.mark.asyncio
    async def test_logs_request(self, capsys):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(StructuredLoggingMiddleware)

        @app.get("/hello")
        async def hello():
            return {"msg": "hi"}

        await _call_app(app, "GET", "/hello")
        # Structured log should have been emitted (exact format depends on config)

    @pytest.mark.asyncio
    async def test_skips_non_http(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(StructuredLoggingMiddleware)
        # Non-http scope should pass through
        scope = {"type": "lifespan"}
        sent = []
        await app(scope, lambda: None, lambda msg: sent.append(msg))
```

### Step 4: Run tests to verify they fail

Run: `uv run pytest tests/unit/test_structured_logging.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 5: Implement StructuredLoggingMiddleware

```python
# src/hawkapi/middleware/structured_logging.py
"""Structured logging middleware using structlog."""

from __future__ import annotations

import time
import uuid
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class StructuredLoggingMiddleware(Middleware):
    """Emit JSON-structured request/response logs with request ID tracking.

    Usage:
        app.add_middleware(StructuredLoggingMiddleware)
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        request_id_header: str = "x-request-id",
        log_level: str = "info",
    ) -> None:
        super().__init__(app)
        import structlog

        self._request_id_header = request_id_header.lower().encode("latin-1")
        self._log_level = log_level

        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.add_log_level,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.BoundLogger,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
        self._logger = structlog.get_logger("hawkapi")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope["method"]
        path: str = scope["path"]

        # Extract or generate request ID
        request_id: str | None = None
        raw_headers: list[Any] = scope.get("headers", [])
        for key, value in raw_headers:
            if key == self._request_id_header:
                request_id = value.decode("latin-1")
                break
        if request_id is None:
            request_id = str(uuid.uuid4())

        start = time.monotonic()
        status_code = 500

        async def logging_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((self._request_id_header, request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, logging_send)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 3)
            log_fn = getattr(self._logger, self._log_level)
            log_fn(
                "request",
                method=method,
                path=path,
                status=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )
```

### Step 6: Run tests to verify they pass

Run: `uv run pytest tests/unit/test_structured_logging.py -v`
Expected: All PASS

### Step 7: Add lazy import to `__init__.py`

Add to `_LAZY_IMPORTS`:
```python
    "StructuredLoggingMiddleware": ("hawkapi.middleware.structured_logging", "StructuredLoggingMiddleware"),
```

Add to `TYPE_CHECKING`:
```python
    from hawkapi.middleware.structured_logging import StructuredLoggingMiddleware
```

Add to `__all__`:
```python
    "StructuredLoggingMiddleware",
```

### Step 8: Lint, type check, full test suite

Run: `uv run ruff check src/hawkapi/middleware/structured_logging.py tests/unit/test_structured_logging.py && uv run pyright src/hawkapi/middleware/structured_logging.py && uv run pytest tests/ -x -q`
Expected: 0 errors, all tests pass

### Step 9: Commit

```bash
git add src/hawkapi/middleware/structured_logging.py tests/unit/test_structured_logging.py pyproject.toml src/hawkapi/__init__.py
git commit -m "feat: add structured logging middleware (hawkapi[logging])"
```

---

## Task 8: End-to-End Benchmarks

**Files:**
- Create: `benchmarks/e2e/hawkapi_app.py`
- Create: `benchmarks/e2e/fastapi_app.py`
- Create: `benchmarks/e2e/run_benchmarks.py`
- Create: `.github/workflows/benchmark.yml`

### Step 1: Create HawkAPI benchmark app

```python
# benchmarks/e2e/hawkapi_app.py
"""HawkAPI benchmark application."""

import msgspec

from hawkapi import HawkAPI

app = HawkAPI(openapi_url=None)


class Item(msgspec.Struct):
    id: int
    name: str
    price: float


ITEMS = [Item(id=i, name=f"item-{i}", price=i * 1.99) for i in range(1000)]


@app.get("/json")
async def json_hello():
    return {"message": "Hello, World!"}


@app.get("/users/{user_id:int}")
async def get_user(user_id: int):
    return {"id": user_id, "name": "Alice"}


@app.post("/items")
async def create_item(body: Item):
    return {"id": body.id, "name": body.name, "price": body.price}


@app.get("/items")
async def list_items():
    return ITEMS
```

### Step 2: Create FastAPI benchmark app

```python
# benchmarks/e2e/fastapi_app.py
"""FastAPI benchmark application (for comparison)."""

from pydantic import BaseModel
from fastapi import FastAPI

app = FastAPI(docs_url=None, redoc_url=None)


class Item(BaseModel):
    id: int
    name: str
    price: float


ITEMS = [Item(id=i, name=f"item-{i}", price=i * 1.99) for i in range(1000)]


@app.get("/json")
async def json_hello():
    return {"message": "Hello, World!"}


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id, "name": "Alice"}


@app.post("/items")
async def create_item(body: Item):
    return {"id": body.id, "name": body.name, "price": body.price}


@app.get("/items")
async def list_items():
    return [item.model_dump() for item in ITEMS]
```

### Step 3: Create benchmark runner

```python
# benchmarks/e2e/run_benchmarks.py
"""End-to-end HTTP benchmark runner.

Requires: uvicorn, httpx
Usage: python benchmarks/e2e/run_benchmarks.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

SCENARIOS = [
    {"name": "JSON hello", "method": "GET", "path": "/json"},
    {"name": "Path params", "method": "GET", "path": "/users/42"},
    {
        "name": "POST body",
        "method": "POST",
        "path": "/items",
        "body": '{"id": 1, "name": "Widget", "price": 9.99}',
    },
    {"name": "Large response (1000 items)", "method": "GET", "path": "/items"},
]

FRAMEWORKS = [
    {"name": "HawkAPI", "module": "benchmarks.e2e.hawkapi_app:app"},
    {"name": "FastAPI", "module": "benchmarks.e2e.fastapi_app:app"},
]

DURATION = 10  # seconds per scenario
CONNECTIONS = 50


def main():
    print("=" * 60)
    print("End-to-End HTTP Benchmark")
    print("=" * 60)
    # Implementation: start uvicorn for each framework,
    # run wrk/bombardier for each scenario,
    # collect results, print comparison table
    print("\nNote: Requires uvicorn and wrk/bombardier installed.")
    print("This is a template — customize for your environment.")


if __name__ == "__main__":
    main()
```

### Step 4: Create GitHub Action

```yaml
# .github/workflows/benchmark.yml
name: Benchmark

on:
  release:
    types: [published]
  workflow_dispatch:

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install uv
          uv sync --extra uvicorn --extra dev

      - name: Run ASGI-level benchmark
        run: uv run python benchmarks/bench_request_response.py

      - name: Save results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: benchmark_results.json
          if-no-files-found: ignore
```

### Step 5: Commit

```bash
git add benchmarks/e2e/ .github/workflows/benchmark.yml
git commit -m "feat: add e2e benchmark suite and GitHub Action"
```

---

## Final Verification

After all tasks are complete:

1. **Tests:** `uv run pytest tests/ -x -q` — all tests pass
2. **Lint:** `uv run ruff check src/ tests/` — 0 errors
3. **Format:** `uv run ruff format --check src/ tests/` — 0 errors
4. **Types:** `uv run pyright src/` — 0 errors
5. **Benchmark:** `uv run python benchmarks/bench_request_response.py` — no regression
