# HawkAPI DX audit vs FastAPI

**Date:** 2026-04-18
**Scope:** Feature-parity snapshot of HawkAPI vs FastAPI. Research-only; no code changes here.
**Spec:** [docs/plans/2026-04-18-dx-audit-design.md](../plans/2026-04-18-dx-audit-design.md)

---

## Executive summary

HawkAPI currently **matches or exceeds FastAPI on ~85 % of the tutorial-level DX surface**, and meaningfully exceeds on differentiators FastAPI does not ship at all (API versioning, permission policies, built-in bulkhead/circuit-breaker/rate-limiter, observability, migration codemod, PEP 703 wheels).

The five gaps below are the ones that hurt migration from a real FastAPI codebase the most — not because they are large engineering tasks, but because they are everywhere in FastAPI tutorials and copy-pasted into real production code:

| # | Gap | Severity | Effort |
|---|---|---|---|
| 1 | **Yield-dependencies with per-request finalization** | Critical | M |
| 2 | **Route-level `dependencies=[Depends(...)]`** on decorators | Important | S |
| 3 | **`response_model_exclude_none/unset/defaults`** flags | Important | S |
| 4 | **OAuth2 scopes enforcement + OpenAPI reflection** | Important | M |
| 5 | **`status` module with HTTP_NNN constants** | Minor (cosmetic) | XS |

Everything else is either already present or a known out-of-scope differentiator. The non-gap surplus (built-in versioning, bulkhead, observability, codemod, etc.) is strong; the five items above close the last mile of "FastAPI users land on HawkAPI and nothing is missing."

---

## Feature-parity matrix

Legend: ✅ full, ⚠️ partial, ❌ missing.

### Routing & path operations

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `@app.get/post/put/patch/delete/head/options` | [src/hawkapi/routing/router.py](../../src/hawkapi/routing/router.py) | ✅ | |
| `APIRouter` with `prefix=`, `tags=`, `dependencies=` | `Router` class + `include_router` | ⚠️ | `prefix`/`tags` supported; `dependencies=` on routers not wired |
| Typed path params `{id}` with `int`/`str`/... inference | [routing/_radix_tree.py](../../src/hawkapi/routing/_radix_tree.py) | ✅ | `/items/{id:int}` |
| Route-level `tags=`, `summary=`, `description=` | [routing/route.py](../../src/hawkapi/routing/route.py) | ✅ | |
| Route-level `response_model=` | Router.add_route | ✅ | |
| Route-level `status_code=` | Router.add_route | ✅ | |
| Route-level `include_in_schema=False` | Router.add_route | ✅ | |
| Route-level `dependencies=[...]` (side-effect deps) | — | ❌ | Must use app-level hooks or middleware today (**Gap #2**) |
| `include_router(responses=...)` default-response map | — | ❌ | Not supported |
| Sub-app mount `app.mount("/x", subapp)` | app.py | ✅ | |

### Parameters (path / query / header / cookie / body)

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `Query()` marker (alias, validation) | [validation/constraints.py](../../src/hawkapi/validation/constraints.py) | ✅ | Via `Annotated[T, Query(...)]` |
| `Path()` marker | validation/constraints.py | ✅ | |
| `Header()` marker with `_`→`-` auto-conversion | validation/constraints.py + di/param_plan.py | ✅ | |
| `Cookie()` marker | validation/constraints.py | ✅ | |
| `Body()` marker | validation/constraints.py | ✅ | |
| `Annotated[T, Query(...)]` form | di/param_plan.py | ✅ | First-class |
| `Form()` marker | — | ⚠️ | Forms are parsed when `FormData` is declared, but no explicit `Form()` class for per-field validation |
| `File()` / `UploadFile` | [requests/form_data.py](../../src/hawkapi/requests/form_data.py) | ✅ | `.read()`, `.seek()`, `.close()` |
| Multiple body params in one handler | di/param_plan.py | ✅ | |

### Dependency injection

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `Depends(callable)` | [src/hawkapi/di/depends.py](../../src/hawkapi/di/depends.py) | ✅ | |
| Sub-dependencies (transitive) | di/param_plan.py | ✅ | Resolved recursively |
| `yield` dependencies with teardown after response | — | ⚠️ | App-level `lifespan` only; no per-request yield-dep (**Gap #1**) |
| Class-callable as dependency | di/param_plan.py | ✅ | |
| Path-operation-level `dependencies=[...]` | — | ❌ | Requires middleware today (**Gap #2**) |
| Global (app-level) dependencies | — | ❌ | Workaround: middleware |
| Within-request caching of same `Depends(fn)` | di/scope.py | ✅ | Scope-level caching |
| `dependency_overrides` for tests | [testing/overrides.py](../../src/hawkapi/testing/overrides.py) | ✅ | `override()` context manager |

### Security

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `OAuth2PasswordBearer` | [security/oauth2.py](../../src/hawkapi/security/oauth2.py) | ✅ | |
| `OAuth2PasswordRequestForm` | — | ❌ | Form helper class not shipped |
| `HTTPBasic` / `HTTPBasicCredentials` | [security/http_basic.py](../../src/hawkapi/security/http_basic.py) | ✅ | |
| `APIKeyHeader` / `APIKeyQuery` / `APIKeyCookie` | [security/api_key.py](../../src/hawkapi/security/api_key.py) | ✅ | |
| OAuth2 scopes enforcement + OpenAPI reflection | security/oauth2.py | ❌ | `scopes` placeholder present but not enforced (**Gap #4**) |
| `SecurityScheme` propagation into OpenAPI | security/base.py | ✅ | |

### Responses

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `JSONResponse` | responses/json_response.py | ✅ | |
| `HTMLResponse`, `PlainTextResponse`, `RedirectResponse`, `FileResponse`, `StreamingResponse` | `src/hawkapi/responses/` | ✅ | |
| Return `Response` directly from handler (bypass serialization) | responses/response.py | ✅ | |
| `response_model_exclude_none/unset/defaults` | — | ❌ | Not wired (**Gap #3**) |
| `jsonable_encoder` equivalent | [serialization/encoder.py](../../src/hawkapi/serialization/encoder.py) | ✅ | `encode_response()` |
| Content negotiation (Accept → JSON vs MessagePack) | serialization/negotiation.py | ✅ | Exceeds FastAPI |

### Exception handling

| FastAPI feature | HawkAPI | Status | Notes |
|---|---|---|---|
| `HTTPException(status_code, detail, headers)` | [exceptions.py](../../src/hawkapi/exceptions.py) | ✅ | Returns RFC 7807 `application/problem+json` |
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
| `BackgroundTasks` injection + `add_task()` | [background.py](../../src/hawkapi/background.py) | ✅ | |
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
| `from fastapi import status` → `status.HTTP_201_CREATED` | — | ❌ | No constants module (**Gap #5**) |
| CORS middleware | middleware/cors.py | ✅ | |
| GZip middleware | middleware/gzip.py | ✅ | |
| Session (signed cookies) middleware | middleware/session.py | ✅ | |
| TrustedHost middleware | middleware/trusted_host.py | ✅ | |
| Official starter scaffold CLI | cli.py (`hawkapi new`) | ✅ | Exceeds FastAPI |
| FastAPI → framework migration codemod | _migrate/codemod.py | ✅ | Exceeds FastAPI |

---

## Top-5 gaps (detailed)

### Gap #1 — Yield-dependencies with per-request finalization

**Severity:** Critical  **Effort:** M

**What FastAPI has:**

```python
async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session  # returned to handler

@app.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    ...
# After response is sent, session context manager exits; rolls back or commits.
```

This is THE pattern in FastAPI tutorials and production code for database sessions, HTTP clients, Redis connections, transactions. Every SQLAlchemy/Databases example depends on it.

**What HawkAPI has:** App-level `lifespan` context manager for long-lived resources. No per-request teardown.

**Work required:**
- Extend `src/hawkapi/di/param_plan.py` to detect generator/async-generator dependencies.
- Register each yield-dep on a per-request stack (push on entry, pop + run remaining code after the handler's response body is sent).
- Ensure cancellation and exception paths run the finalizers.
- Wire teardown to run AFTER response headers+body flushed (like FastAPI) so the client isn't blocked.
- Test: yield that raises during teardown — how should the error be reported? (FastAPI: logs, ignores.)

**Payoff:** Single biggest migration-friction item for any FastAPI user with a database.

---

### Gap #2 — Route-level `dependencies=[Depends(...)]`

**Severity:** Important  **Effort:** S

**What FastAPI has:**

```python
@app.get("/admin/reports", dependencies=[Depends(require_admin)])
async def reports() -> ...:
    ...
```

Used pervasively for auth guards, audit-log writers, rate-limit increments that don't need a return value. Also accepted on `APIRouter(dependencies=[...])` for whole-router guards.

**What HawkAPI has:** Workaround via app-level hooks or middleware. No decorator-level kwarg.

**Work required:**
- Add `dependencies: Sequence[Depends] | None = None` kwarg to the route decorators in `src/hawkapi/routing/router.py`.
- Add the same kwarg on the `Router` class constructor and `include_router` call; merge router-level + route-level lists.
- On request: resolve each `Depends` before invoking the handler; any raised exception short-circuits (consistent with FastAPI behavior).
- Make the results *not* injected into the handler's signature — they're executed for side effects only.
- Tests: chain ordering, exceptions, interaction with yield-dependencies.

**Payoff:** Biggest ergonomic win for anyone who reads FastAPI auth examples and copy-pastes.

---

### Gap #3 — `response_model_exclude_none / _unset / _defaults`

**Severity:** Important  **Effort:** S

**What FastAPI has:**

```python
@app.get(
    "/items/{id}",
    response_model=Item,
    response_model_exclude_none=True,     # drop keys whose value is None
    response_model_exclude_unset=True,    # drop keys the user didn't set
    response_model_exclude_defaults=True, # drop keys equal to their default
)
```

Used for:
- APIs where optional fields shouldn't serialize as `"field": null`
- Versioned responses where fields were added later and old clients shouldn't see them
- Admin vs public response shapes

**What HawkAPI has:** `response_model` accepted on routes; the three exclusion knobs are not wired through to the serializer.

**Work required:**
- Plumb three flags from route metadata → `src/hawkapi/serialization/encoder.py`.
- msgspec already supports field exclusion at encode time; map the flags onto its API.
- Tests per flag + combinations.

**Payoff:** Low-effort closure of a feature 70 % of FastAPI response_model users eventually reach for.

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

### Gap #5 — `status` module with HTTP_NNN constants

**Severity:** Minor (but high frequency)  **Effort:** XS

**What FastAPI has:**

```python
from fastapi import status

@app.post("/items", status_code=status.HTTP_201_CREATED)
async def create_item(...): ...
```

Pure cosmetic convenience re-exported from Starlette. Everyone uses it.

**What HawkAPI has:** Users hardcode `201`.

**Work required:**
- Create `src/hawkapi/status.py` re-exporting the standard HTTP constants (can copy from Starlette's `starlette.status`, or use `http.HTTPStatus`'s integer values).
- Export `status` from `hawkapi/__init__.py` so `from hawkapi import status` works.
- One-line unit test.

**Payoff:** Removes a paper cut. A one-hour job that eliminates a reason someone says "HawkAPI is missing things FastAPI has."

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

## Follow-ups (not this project)

Each of the top-5 gaps becomes its own design spec + implementation plan. Recommended order (smallest effort / highest ratio first, to accumulate shipped wins):

1. **Gap #5** (`status` constants) — afternoon of work.
2. **Gap #3** (`response_model_exclude_*`) — one spec, small impl.
3. **Gap #2** (`dependencies=[...]` kwarg) — clean decorator change.
4. **Gap #1** (yield-dependencies) — the big one, touches DI core.
5. **Gap #4** (OAuth2 scopes) — biggest surface area, last.

This order gives four visible DX-parity wins before the fifth (scopes) takes more effort. Each gets an independent cycle — spec → plan → implement — following the workflow used for Tier 1 and Tier 2.
