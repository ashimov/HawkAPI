# HawkAPI DX audit vs FastAPI

**Date:** 2026-04-18 (corrected 2026-04-18)
**Scope:** Feature-parity snapshot of HawkAPI vs FastAPI. Research-only; no code changes here.
**Spec:** [docs/plans/2026-04-18-dx-audit-design.md](../plans/2026-04-18-dx-audit-design.md)

---

## Executive summary

HawkAPI **matches or exceeds FastAPI on ~90 % of the tutorial-level DX surface** and meaningfully exceeds on differentiators FastAPI does not ship at all (API versioning, permission policies, built-in bulkhead/circuit-breaker/rate-limiter, observability, migration codemod, PEP 703 wheels).

The five gaps below were identified in the initial audit as the items hurting migration from a real FastAPI codebase the most. Four of the five are **closed** at this revision; one remains.

| # | Gap | Severity | Effort | Status |
|---|---|---|---|---|
| 1 | **Yield-dependencies with per-request finalization** | Critical | M | ✅ always shipped (see correction below) |
| 2 | **Route-level `dependencies=[Depends(...)]`** on decorators | Important | S | ✅ shipped (commit `14a7a28`) |
| 3 | **`response_model_exclude_none/unset/defaults`** flags | Important | S | ✅ shipped (commit `10b3655`) |
| 4 | **OAuth2 scopes enforcement + OpenAPI reflection** | Important | M | ❌ open — last remaining |
| 5 | **`status` module with HTTP_NNN constants** | Minor (cosmetic) | XS | ✅ shipped (commit `de14afc`) |

**Correction (2026-04-18):** Gap #1 was incorrectly flagged ⚠️ partial in the original matrix. A second-pass re-verification confirmed yield-dependencies with per-request teardown are **fully working**: `src/hawkapi/di/resolver.py:_execute_dep_plan` pushes generators onto a per-request cleanup stack, and `src/hawkapi/app.py:534-548` advances (success) or closes (exception) every generator in reverse order. 6 tests in `tests/unit/test_generator_deps.py` cover sync/async generators, cleanup on error, and multi-gen ordering. No work needed for Gap #1.

---

## Feature-parity matrix

Legend: ✅ full, ⚠️ partial, ❌ missing.

### Routing & path operations

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `@app.get/post/put/patch/delete/head/options` | `src/hawkapi/routing/router.py` | ✅ | |
| `APIRouter` with `prefix=`, `tags=`, `dependencies=` | `Router` class + `include_router` | ⚠️ | `prefix`/`tags` supported; `dependencies=` on routers not wired |
| Typed path params `{id}` with `int`/`str`/... inference | `routing/_radix_tree.py` | ✅ | `/items/{id:int}` |
| Route-level `tags=`, `summary=`, `description=` | `routing/route.py` | ✅ | |
| Route-level `response_model=` | Router.add_route | ✅ | |
| Route-level `status_code=` | Router.add_route | ✅ | |
| Route-level `include_in_schema=False` | Router.add_route | ✅ | |
| Route-level `dependencies=[...]` (side-effect deps) | Router + route decorators (commit `14a7a28`) | ✅ | Shipped in Gap #2; router-level also supported |
| `include_router(responses=...)` default-response map | — | ❌ | Not supported |
| Sub-app mount `app.mount("/x", subapp)` | app.py | ✅ | |

### Parameters (path / query / header / cookie / body)

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `Query()` marker (alias, validation) | `validation/constraints.py` | ✅ | Via `Annotated[T, Query(...)]` |
| `Path()` marker | validation/constraints.py | ✅ | |
| `Header()` marker with `_`→`-` auto-conversion | validation/constraints.py + di/param_plan.py | ✅ | |
| `Cookie()` marker | validation/constraints.py | ✅ | |
| `Body()` marker | validation/constraints.py | ✅ | |
| `Annotated[T, Query(...)]` form | di/param_plan.py | ✅ | First-class |
| `Form()` marker | — | ⚠️ | Forms are parsed when `FormData` is declared, but no explicit `Form()` class for per-field validation |
| `File()` / `UploadFile` | `requests/form_data.py` | ✅ | `.read()`, `.seek()`, `.close()` |
| Multiple body params in one handler | di/param_plan.py | ✅ | |

### Dependency injection

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `Depends(callable)` | `src/hawkapi/di/depends.py` | ✅ | |
| Sub-dependencies (transitive) | di/param_plan.py | ✅ | Resolved recursively |
| `yield` dependencies with teardown after response | `di/resolver.py` `_execute_dep_plan` + `app.py` cleanup finalizer | ✅ | Sync + async generators; reverse-order cleanup on success or exception; 6 tests in `test_generator_deps.py` |
| Class-callable as dependency | di/param_plan.py | ✅ | |
| Path-operation-level `dependencies=[...]` | Router + route decorators (commit `14a7a28`) | ✅ | Shipped in Gap #2 |
| Global (app-level) dependencies | — | ⚠️ | Available as `Router(dependencies=[...])` subclass pattern; no `HawkAPI(dependencies=[...])` kwarg yet |
| Within-request caching of same `Depends(fn)` | di/scope.py | ✅ | Scope-level caching |
| `dependency_overrides` for tests | `testing/overrides.py` | ✅ | `override()` context manager |

### Security

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `OAuth2PasswordBearer` | `security/oauth2.py` | ✅ | |
| `OAuth2PasswordRequestForm` | — | ❌ | Form helper class not shipped |
| `HTTPBasic` / `HTTPBasicCredentials` | `security/http_basic.py` | ✅ | |
| `APIKeyHeader` / `APIKeyQuery` / `APIKeyCookie` | `security/api_key.py` | ✅ | |
| OAuth2 scopes enforcement + OpenAPI reflection | security/oauth2.py | ❌ | `scopes` placeholder present but not enforced (**Gap #4**) |
| `SecurityScheme` propagation into OpenAPI | security/base.py | ✅ | |

### Responses

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `JSONResponse` | responses/json_response.py | ✅ | |
| `HTMLResponse`, `PlainTextResponse`, `RedirectResponse`, `FileResponse`, `StreamingResponse` | `src/hawkapi/responses/` | ✅ | |
| Return `Response` directly from handler (bypass serialization) | responses/response.py | ✅ | |
| `response_model_exclude_none/unset/defaults` | `serialization/filters.py` (commit `10b3655`) | ✅ | Shipped in Gap #3; recursive over msgspec + Pydantic |
| `jsonable_encoder` equivalent | `serialization/encoder.py` | ✅ | `encode_response()` |
| Content negotiation (Accept → JSON vs MessagePack) | serialization/negotiation.py | ✅ | Exceeds FastAPI |

### Exception handling

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `HTTPException(status_code, detail, headers)` | `exceptions.py` | ✅ | Returns RFC 7807 `application/problem+json` |
| `@app.exception_handler(Cls)` registration | app.py | ✅ | |
| Default `RequestValidationError` handler | validation/errors.py | ✅ | RFC 9457 `ProblemDetail` |

### OpenAPI customization

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `title=`, `description=`, `version=` on constructor | app.py | ✅ | |
| `contact=`, `license_info=` on constructor | — | ⚠️ | Not surfaced |
| `openapi_tags=[{name, description, externalDocs}, ...]` | — | ❌ | Route-level tags only |
| `servers=[{url, description}, ...]` | — | ❌ | |
| Per-route `openapi_extra={}` | — | ❌ | No hook to inject arbitrary OpenAPI extensions per route |
| Customizable `docs_url`, `redoc_url`, `openapi_url` (or `None` to disable) | app.py | ✅ | |
| Swagger UI / ReDoc / **Scalar** shipped | _docs.py | ✅ | Scalar = exceeds FastAPI |

### Middleware & hooks

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `app.add_middleware(Cls, **kwargs)` | app.py | ✅ | |
| Raw ASGI middleware supported | middleware/base.py | ✅ | |
| Lifespan context manager (`@asynccontextmanager` on app) | lifespan/manager.py | ✅ | |
| Legacy `@app.on_event("startup"/"shutdown")` | — | ⚠️ | Have `on_startup()` / `on_shutdown()` decorators; not the `on_event()` string-discriminant form |

### Testing

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `TestClient(app)` (sync httpx-style) | testing/client.py | ✅ | |
| Async test helpers | testing/client.py | ✅ | `async_get()` et al. |
| DI override mechanism | testing/overrides.py | ✅ | |
| Lifespan fires in TestClient | testing/client.py | ✅ | |

### Background tasks & lifespan

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `BackgroundTasks` injection + `add_task()` | `background.py` | ✅ | |
| Tasks run after response sent | app.py | ✅ | |
| Longer-running job primitive beyond per-request tasks | — | ❌ | No built-in scheduler / worker (also not in FastAPI) |

### WebSockets

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `WebSocket` injected into handler | websocket/connection.py | ✅ | |
| `Depends(...)` inside WebSocket handlers | websocket | ⚠️ | Basic resolution; security schemes not enforced the same way as HTTP |
| WebSocket routes visible in OpenAPI/AsyncAPI | — | ⚠️ | No first-class AsyncAPI story |

### Static files & templates

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `StaticFiles` mount | staticfiles.py | ✅ | |
| `Jinja2Templates` + `TemplateResponse` | — | ❌ | Server-rendered apps need external integration |

### Forms & file uploads

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `application/x-www-form-urlencoded` auto-parsing | requests/form_data.py | ✅ | Via `FormData` declaration |
| `multipart/form-data` streaming `UploadFile` | requests/form_data.py | ✅ | |

### Other DX conveniences

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `from fastapi import status` → `status.HTTP_201_CREATED` | `status.py` (commit `de14afc`) | ✅ | Shipped in Gap #5; Starlette-compatible names |
| CORS middleware | middleware/cors.py | ✅ | |
| GZip middleware | middleware/gzip.py | ✅ | |
| Session (signed cookies) middleware | middleware/session.py | ✅ | |
| TrustedHost middleware | middleware/trusted_host.py | ✅ | |
| Official starter scaffold CLI | cli.py (`hawkapi new`) | ✅ | Exceeds FastAPI |
| FastAPI → framework migration codemod | _migrate/codemod.py | ✅ | Exceeds FastAPI |

---

## Top-5 gaps (detailed)

### Gaps #1, #2, #3, #5 — closed

| Gap | Outcome | Commit / file |
|---|---|---|
| #1 Yield-dependencies | Confirmed always shipped; re-verification found full sync + async generator support, reverse-order teardown, cleanup-on-error, multi-gen ordering | `di/resolver.py:_execute_dep_plan` + `app.py` finally block + `tests/unit/test_generator_deps.py` (6 tests) |
| #2 Route / router `dependencies=[...]` | Shipped | commit `14a7a28`, `tests/unit/test_route_dependencies.py` |
| #3 `response_model_exclude_*` flags | Shipped (msgspec + Pydantic + nested recursion) | commit `10b3655`, `serialization/filters.py`, `tests/unit/test_response_model_exclude.py` |
| #5 `hawkapi.status` constants | Shipped (Starlette-compat naming; `http.HTTPStatus`-derived) | commit `de14afc`, `status.py`, `tests/unit/test_status.py` |

---

### Gap #4 — OAuth2 scopes enforcement + OpenAPI reflection

**Severity:** Important  **Effort:** M

**What FastAPI has:**

```python
from fastapi import Security
from fastapi.security import SecurityScopes

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="token",
    scopes={"read:items": "Read items", "admin": "Admin"}
)

async def get_current_user(
    scopes: SecurityScopes,
    token: str = Depends(oauth2_scheme),
) -> User:
    # validate token, verify required scopes against user scopes
    ...

@app.get("/items", dependencies=[Security(get_current_user, scopes=["read:items"])])
async def list_items() -> ...:
    ...
```

- Scopes are declared in OpenAPI under `components.securitySchemes` with full descriptions.
- Each route's required scopes appear in its `security` entry.
- Framework enforces by collecting required scopes down the dep chain and passing them to the scheme's `authenticate()` call.

**What HawkAPI has:** `OAuth2PasswordBearer` exists with a `scopes` dict placeholder, but nothing enforces or propagates scopes.

**Work required:**
- Add a `Security()` marker parallel to `Depends()` carrying `scopes: Sequence[str]`.
- Track route-level required scopes; inject a `SecurityScopes`-like context into the scheme's callable.
- Propagate `securitySchemes.oauth2.flows.password.scopes` into the OpenAPI document.
- Annotate each route's OpenAPI `security` field with required scopes.
- Tests: scope subset check; 403 on insufficient scope; multi-route aggregation.

**Payoff:** Largest "production OAuth2 users" gap. A real-world API without scopes rolled-your-own is unusual.

---

---

## Where HawkAPI already exceeds FastAPI

Not gaps — differentiators we should not accidentally dilute while closing the gaps above:

- **API versioning** — `VersionRouter` with per-version OpenAPI specs. FastAPI has no first-class story.
- **Permission policies** — `PermissionPolicy` with pluggable resolvers. FastAPI users hand-roll.
- **Observability** — one-flag tracing, structured logs, Prometheus metrics out of the box.
- **Bulkhead** (just shipped) + Redis-distributed variant.
- **Circuit breaker** — local + Redis variant.
- **Adaptive concurrency limiter** — Netflix gradient2 auto-tune.
- **Rate limiter** — local + Redis variant.
- **CSRF middleware** with double-submit cookie.
- **Session middleware** with signed cookies.
- **Content negotiation** — Accept-based JSON vs MessagePack serialization.
- **Scalar UI** for API docs (in addition to Swagger + ReDoc).
- **mypyc-compiled hot paths** — routing / route record / param converters / middleware pipeline.
- **Free-threaded Python 3.13 wheels** (PEP 703).
- **`hawkapi migrate` codemod** — FastAPI → HawkAPI AST rewriter.
- **`hawkapi new` scaffold CLI** — project starter.
- **Perf regression gate in CI** — 5 % mean threshold.
- **Memory budget tests** — pytest-memray.

---

## Follow-ups

**Top-5 progress (4/5 closed):**

1. ✅ Gap #5 (`status` constants) — commit `de14afc`.
2. ✅ Gap #3 (`response_model_exclude_*`) — commit `10b3655`.
3. ✅ Gap #2 (`dependencies=[...]` kwarg) — commit `14a7a28`.
4. ✅ Gap #1 (yield-dependencies) — confirmed always shipped; no code change needed, audit corrected.
5. ❌ Gap #4 (OAuth2 scopes) — **next**.

**Second-tier gaps (not in top-5 but worth tracking):**

- `Form()` marker class (multipart field validation)
- `OAuth2PasswordRequestForm` helper
- `openapi_tags=[{name, description, externalDocs}, ...]` with metadata
- `servers=[...]` for OpenAPI
- Per-route `openapi_extra={}`
- `include_router(responses={...})`
- `Jinja2Templates` / `TemplateResponse`
- AsyncAPI story for WebSocket routes
- Legacy `@app.on_event()` decorator (codemod already targets migration)
- `contact=` / `license_info=` on constructor
- Global `HawkAPI(dependencies=[...])` kwarg

Each becomes its own spec → plan → implement cycle if prioritized.
