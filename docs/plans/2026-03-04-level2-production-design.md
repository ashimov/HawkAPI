# HawkAPI Level 2 — Production Features Design

**Goal:** Add 13 production-grade features across 3 waves to make HawkAPI a complete framework for production deployments, CI/CD pipelines, and daily developer experience.

**Approach:** Production Foundation First — ship runtime essentials first, then contract/quality tooling, then DX/introspection. Request/response object pooling dropped (already 2-5x faster than FastAPI).

---

## Wave 1: Production Essentials

### 1. TrustedProxyMiddleware

**File:** `src/hawkapi/middleware/trusted_proxy.py`

Handles `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, and RFC 7239 `Forwarded`. Rewrites `scope["client"]`, `scope["scheme"]`, and host header from trusted sources only. Takes `trusted_proxies: list[str]` (IP ranges via `ipaddress` stdlib).

```python
app.add_middleware(TrustedProxyMiddleware, trusted_proxies=["10.0.0.0/8"])
```

Zero external dependencies. Validates source IP against CIDR ranges before trusting headers.

### 2. RequestLimitsMiddleware

**File:** `src/hawkapi/middleware/request_limits.py`

Configurable limits beyond `max_body_size`:
- `max_header_size`: default 8KB per header value
- `max_headers_count`: default 100
- `max_query_length`: default 2048
- `max_json_depth`: default 64

Returns RFC 9457 `431 Request Header Fields Too Large` or `413 Payload Too Large`. Fast rejection at ASGI scope level before body parsing.

```python
app.add_middleware(RequestLimitsMiddleware, max_query_length=4096, max_json_depth=32)
```

### 3. Health Probes: /readyz + /livez

**Modify:** `src/hawkapi/app.py`

Extend `HawkAPI.__init__` with `readyz_url="/readyz"` and `livez_url="/livez"` parameters.

- `/livez` — always 200 `{"status": "alive"}` (process is running)
- `/readyz` — runs user-registered readiness checks, returns 200 or 503

```python
@app.readiness_check("database")
async def check_db():
    return await db.ping(), "postgres"

# GET /readyz → {"status": "ready", "checks": {"database": {"ok": true, "detail": "postgres"}}}
# 503 → {"status": "not_ready", "checks": {"database": {"ok": false, "detail": "connection refused"}}}
```

Readiness checks registered via `app.readiness_check(name)` decorator. Each returns `(ok: bool, detail: str)`.

### 4. Deprecation Headers

**Modify:** `src/hawkapi/routing/route.py`, `src/hawkapi/app.py`

Add `sunset: str | None` and `deprecation_link: str | None` fields to `Route`. When `deprecated=True`, auto-inject response headers:
- `Deprecation: true`
- `Sunset: <RFC 8594 date>` (if provided)
- `Link: <url>; rel="deprecation"` (if provided)

Handled in `_core_handler_inner` after response construction — no new middleware.

```python
@app.get("/v1/users", deprecated=True, sunset="2026-06-01", deprecation_link="/docs/migration")
async def old_endpoint(): ...
```

### 5. CircuitBreakerMiddleware

**File:** `src/hawkapi/middleware/circuit_breaker.py`

Three-state circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED.

- `failure_threshold`: consecutive failures before opening (default 5)
- `recovery_timeout`: seconds before trying HALF_OPEN (default 30)
- `half_open_max_calls`: probe requests in HALF_OPEN (default 1)

Returns 503 with RFC 9457 body when OPEN. Per-path tracking via dict keyed on `scope["path"]`. Pure Python, `time.monotonic()` for timers.

```python
app.add_middleware(CircuitBreakerMiddleware, failure_threshold=10, recovery_timeout=60)
```

---

## Wave 2: Contract & Quality Pipeline

### 6. OpenAPI Linter (`hawk check`)

**Files:** `src/hawkapi/openapi/linter.py`, modify `src/hawkapi/cli.py`

Built-in rules:
- Operation IDs must be set
- Descriptions required on operations
- Consistent naming convention (configurable: camelCase or snake_case)
- Security scheme defined on non-public endpoints
- No anonymous inline schemas

Each rule: `(spec: dict) -> list[LintIssue]`. Users can add custom rules.

```bash
$ hawkapi check myapp:app --rules all
```

```python
from hawkapi.openapi.linter import lint
issues = lint(app.openapi())
```

### 7. Changelog Generator

**Files:** `src/hawkapi/openapi/changelog.py`, modify `src/hawkapi/cli.py`

Takes output from `detect_breaking_changes()` and formats as Markdown changelog:
- Added (new endpoints, parameters)
- Changed (type changes, renamed)
- Deprecated
- Removed
- Breaking

```bash
$ hawkapi changelog old_app:app new_app:app --format md
```

### 8. Contract Smoke Tests

**File:** `src/hawkapi/testing/contract.py`

Reads app's OpenAPI spec, generates one test per endpoint:
- Correct status code for valid request
- 405 for wrong method
- Response matches declared schema

Returns `pytest.param` objects or a subclassable test suite.

```python
from hawkapi.testing.contract import generate_contract_tests
tests = generate_contract_tests(app)
```

### 9. Client SDK Generation (Templates Only)

**Directory:** `templates/sdk-generator/`

Jinja2 template set for TypeScript and Python clients + documentation on using `openapi-generator-cli` with HawkAPI output. No runtime code — templates and docs only.

---

## Wave 3: DX & Introspection

### 10. `hawk new` Project Scaffold

**Modify:** `src/hawkapi/cli.py`
**New:** `src/hawkapi/_scaffold/` (template strings)

Interactive project generator. Asks for features (DB, auth, Docker), creates project directory with `pyproject.toml`, `main.py`, `Dockerfile`, CI config. Templates as plain Python strings (no Jinja2 dependency).

```bash
$ hawkapi new myproject
```

### 11. DI Introspection

**File:** `src/hawkapi/di/introspection.py`

- `container.graph()` — dict of all providers, lifecycles, dependency edges
- `container.print_graph()` — CLI-friendly output
- `container.to_mermaid()` — Mermaid diagram generation

Uses existing `_providers` data only.

### 12. Debug Endpoints

**File:** `src/hawkapi/middleware/debug.py`

`DebugMiddleware` exposes (only when `app.debug=True`):
- `/_debug/routes` — all registered routes with methods, path params
- `/_debug/stats` — request count, avg latency, error rate per endpoint
- `/_debug/deps` — DI graph

In-memory counters, no external deps. Guarded by configurable auth callback.

### 13. Plugin API

**File:** `src/hawkapi/plugins.py`

Plugin protocol with hook points:
- `on_route_registered(route) -> Route`
- `on_schema_generated(spec) -> dict`
- `on_middleware_added(middleware)`

Registered via `app.add_plugin(plugin)`. Plugins observe and modify, but can't break the pipeline.

```python
class MyPlugin:
    def on_route_registered(self, route: Route) -> Route:
        return route
    def on_schema_generated(self, spec: dict) -> dict:
        return spec
```

---

## Dropped

**Request/response object pooling** — HawkAPI already benchmarks at 2-5x faster than FastAPI. Pooling adds thread-safety complexity for marginal gains. Revisit only if profiling shows allocation pressure.

---

## Testing Strategy

- Each feature gets a dedicated test file in `tests/unit/`
- TDD: write failing test first, implement, verify
- All existing 719+ tests must continue to pass
- Lint: `ruff check`, `ruff format --check`, `pyright`
