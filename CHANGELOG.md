# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.6] - 2026-05-16

### Security

- **[HIGH · CWE-290] `hawkapi.flags.get_flags` no longer trusts client-supplied identity headers.** The DI helper previously built `EvalContext(user_id=request.headers.get("x-user-id"), tenant_id=request.headers.get("x-tenant-id"))`, letting any attacker claim any user/tenant by setting the header — bypassing flag targeting for admin previews and sensitive feature toggles. `user_id` and `tenant_id` are now always `None` on the default context; operators MUST derive identity from an authenticated dependency and build their own `EvalContext`. The headers are still exposed on `ctx.headers` for non-identity targeting (region, A/B variant).
- **[HIGH · CWE-352] GraphQL `GET` request can no longer execute mutations or subscriptions via multi-operation documents.** The previous `_is_mutation` check inspected only the first non-comment token, so a document `query A {…} mutation B {…}` with `?operationName=B` snuck a mutation through the GET guard — a CSRF vector for image tags, prefetch, and cache poisoning. The handler now parses every top-level operation and rejects GET whenever the selected operation (or any of them, if `operationName` is omitted) is not a `query`.
- **[HIGH · CWE-770] GraphQL endpoint gained depth and timeout limits.** `make_graphql_handler` now accepts `max_depth: int | None = 15` (selection-set nesting cap, evaluated before executor dispatch) and `timeout_s: float | None = 30.0` (wraps the executor in `asyncio.wait_for`). A single deeply-nested or alias-explosion query can no longer pin a worker indefinitely.
- **[MEDIUM · CWE-200] GraphiQL UI is now opt-in.** `app.mount_graphql(...)` ships with `graphiql=False` by default; the in-browser explorer (and the schema introspection it implies) must be explicitly enabled for dev environments. Production deployments that previously relied on the default are unaffected because schema browsing is no longer exposed unless requested.
- **[MEDIUM] gRPC server now has a default concurrent-RPC cap.** `app.mount_grpc(...)` accepts `maximum_concurrent_rpcs: int | None = 1000` and passes it to `grpc.aio.server(...)`. Pass `None` to restore the previous unbounded behaviour.

### Added

- `docs/security/threat-model.md` — STRIDE per subsystem for the five 0.1.3–0.1.5 additions (doctor / gRPC / GraphQL / flags / bulkhead).
- `docs/security/code-review-2026-05-16.md` — focused security code review covering `security/**`, security-relevant middleware, and request/response boundaries.
- `docs/security/owasp-api-top10-2023.md` — OWASP API Security Top 10 (2023) compliance map.
- `SECURITY.md` — responsible-disclosure policy + supported-versions table.
- `.github/workflows/security.yml` — Bandit + Semgrep (p/python + p/security-audit + p/owasp-top-ten) + pip-audit + Gitleaks + CodeQL on every push, PR, and weekly cron.
- `.github/dependabot.yml` — weekly pip and github-actions update PRs.

### Changed

- `hawkapi.doctor.rules.deps.DOC050` PyPI fetch now explicit-scheme-checks the hard-coded URL and ships with `# nosemgrep` / `# nosec` markers — satisfies Bandit B310 and Semgrep `dynamic-urllib-use-detected` cleanly while preserving the `--offline` opt-out.

## [0.1.5] - 2026-04-19

### Fixed

- **[HIGH] Double-execution of handler on `StreamingResponse`.** Routes whose handler returns a `StreamingResponse` / `FileResponse` were classified as trivial by the Wave 3 fast path, and a late fallback to `_execute_route` re-ran the handler — doubling any side effects (DB writes, emails, billing). `_compute_trivial` now inspects the handler's return annotation and excludes streaming returns at registration time; the fast path dispatches streaming responses in-place as a defensive guard.
- **[MEDIUM] Path-param coercion missing on the trivial fast path.** `{id:int}`-style typed path params were passed as raw `str` to the handler, breaking the declared type contract. The fast path now calls `_coerce_fast` on path values (same behaviour as the general path).
- **[MEDIUM] GraphiQL CDN assets now use pinned versions + Subresource Integrity (SRI) hashes.** Default `app.mount_graphql(...)` ships with `graphiql=True`; the embedded HTML loaded React/GraphiQL from `cdn.jsdelivr.net` with the `@3` / `@18` floating tags and without `integrity=` attributes — a supply-chain vector. All four assets are now pinned to exact versions (`graphiql@3.0.9`, `react@18.3.1`, `react-dom@18.3.1`) with `sha384` SRI hashes.
- **[LOW] `FileFlagProvider` cache/mtime update order.** Under free-threaded CPython or thread-pool workers, writing `_mtime` before `_cache` could let a concurrent reader observe the new mtime, skip the reload, and return the stale cache. Cache is now written first, mtime last.
- **[LOW] Lazy imports inside `_execute_trivial_route` hoisted out of the hot path.** `ParamSource` and `_coerce_fast` are now imported at module scope in `app.py` — a small but per-request saving on every trivial dispatch.

### Added

- `hawkapi doctor --offline` — skip rules that require network access (e.g. DOC050's PyPI version check). Rules opt in via `requires_network: bool = True`.
- README `Security` section note: always use `secrets.compare_digest` to compare credentials returned by `HTTPBasic` / `HTTPBearer` to avoid timing attacks.

### Changed

- `build_mypyc.py` documents the MSVC reserved-identifier trap (`__is_trivial`, `__is_class`, `__is_base_of`, `__has_trivial_destructor`, …) so future additions to `HOT_MODULES` avoid `_is_*` / `_has_*` private attribute names that collide with C++11 type-trait keywords on Windows.
- `[tool.ruff] extend-exclude` and `[tool.ruff.lint.per-file-ignores]` extended so local venvs, build artefacts, and non-library code (`benchmarks/**`, `examples/**`, `hatch_build.py`) no longer block lint.

## [0.1.4] - 2026-04-19

### Added

- `hawkapi doctor <APP_SPEC>` — one-shot health-check CLI that lints a running HawkAPI app against 18 rules across 5 categories (security, observability, performance, correctness, deps). Human and JSON output, `--severity` filter, `--fix` scaffold, exit codes 0/1/2.
- `docs/assets/hawk-icon.svg` + "Using HawkAPI?" README section with a dynamic PyPI-version badge for downstream projects (Markdown + reStructuredText snippets).

### Changed

- **Trivial-route fast path** (`_execute_trivial_route`): routes with no DI, no dependencies, no permissions, no background tasks, no response model, no deprecation headers, and no per-route middleware now bypass all bookkeeping in `_execute_route` and call the handler directly. The eligibility flag (`route._trivial`) is computed once at registration time so the per-request branch is a single boolean check. Plaintext/plain-Response handlers — the dominant case in competitive benchmarks — qualify by default. Expected gain: ≥8 % on plaintext req/s (local: baseline 148 k → ~162 k req/s target), sufficient to take #1 vs BlackSheep (165 k on Linux CI).
- **uvloop by default** in `hawkapi dev`: the CLI now calls `asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())` when uvloop is installed, before handing off to uvicorn. Pass `--no-uvloop` to opt out. No change when uvloop is absent.
- **mypyc expansion** (Wave 3): `src/hawkapi/routing/router.py` and `src/hawkapi/di/resolver.py` added to `HOT_MODULES` in `build_mypyc.py`. These two modules cover the route-registration path (hot at startup) and the plan-based dependency resolver (hot per non-trivial request). `app.py` remains excluded (user subclassing), `requests/request.py` remains excluded (custom request overrides).

## [0.1.3] - 2026-04-19

### Added

- `app.mount_grpc(servicer, add_to_server=..., port=50051)` — thin gRPC integration over `grpc.aio`: ASGI lifespan-tied server lifecycle, built-in `HawkAPIObservabilityInterceptor` (structured logging + Prometheus metrics), context injection (`context.hawkapi_app`, `context.hawkapi_request_id`), reflection toggle with `reflection_service_names`, TLS passthrough via `ssl_credentials`, port-merge for multi-servicer setups; zero runtime deps on default path (`grpcio` imported lazily) (Tier 2 gRPC thin mount)
- `app.mount_graphql(path, executor=...)` — thin GraphQL-over-HTTP adapter: POST + GET wire protocol, GraphiQL UI served to browsers, context injection via `context_factory`, and two optional adapters (`from_graphql_core`, `from_strawberry`) behind lazy imports; zero new runtime deps (Tier 2 GraphQL thin mount)
- Feature flags subsystem: `FlagProvider` Protocol, built-in Static/Env/File providers (File with mtime hot-reload, JSON/TOML/YAML), `Flags` facade, `Depends(get_flags)` DI helper with per-request `EvalContext`, `@requires_flag` decorator (404 on off), plugin hook `on_flag_evaluated`; zero external deps (Tier 2 feature flags)
- `hawkapi gen-client` CLI: generates zero-dep TypeScript (`client.ts`) + Python (`client.py`) client SDKs from OpenAPI 3.1 spec; msgspec-backed for Python, native fetch for TS (Tier 3 OpenAPI codegen)
- Typed routes: `response_model` is now **auto-inferred from the handler's return annotation** when not passed explicitly (msgspec Structs, Pydantic models, parameterized generics, Optionals). Explicit `response_model=` still wins; primitives / `Response` subclasses / missing annotations skip inference (Tier 3 typed routes)
- `hawkapi migrate` codemod — automated FastAPI → HawkAPI migration via AST rewriting
- Performance regression gate in CI: committed baseline (`tests/perf/.benchmark_baseline.json`), 5 % mean regression threshold via `pytest-benchmark --benchmark-compare-fail`
- Memory budget tests using pytest-memray (`tests/perf/`, `memory` mark)
- Distributed primitives: Redis-backed circuit breaker and adaptive concurrency limiter
- HTTP/2 deployment guide
- Free-threaded Python 3.13 wheels (`cp313t-cp313t`) built via cibuildwheel (experimental)
- `hawkapi._threading` module: `FREE_THREADED` flag, `maybe_thread_lock()`, and `maybe_async_lock()` helpers for PEP 703-aware locking
- `build_mypyc.is_enabled()` automatically skips mypyc compilation on free-threaded interpreters
- Experimental `test-free-threaded` CI job (non-blocking, `continue-on-error: true`)
- PEP 779 `Programming Language :: Python :: Free Threading :: 1 - Unstable` trove classifier in `pyproject.toml`
- User guide: `docs/guide/free-threaded.md`
- Bulkhead primitive (`hawkapi.middleware.Bulkhead`) — Hystrix-style named async concurrency isolator with context-manager and `@bulkhead(...)` decorator forms
- `LocalBulkheadBackend` (default, `asyncio.Semaphore` per name) and `RedisBulkheadBackend` (distributed, hash + lease-TTL) implementations
- Opt-in Prometheus metrics for bulkheads (`hawkapi_bulkhead_in_flight`, `_capacity`, `_rejections_total`, `_acquire_latency_seconds`)
- User guide: `docs/guide/bulkhead.md`
- `hawkapi.status` module — HTTP and WebSocket status-code constants (FastAPI parity)
- Route-level `response_model_exclude_none`, `response_model_exclude_unset`, `response_model_exclude_defaults` flags — recursive filtering over msgspec Structs and Pydantic models, zero-overhead when all flags are False (FastAPI parity, DX Gap #3)
- Route-level and router-level `dependencies=[Depends(...)]` kwarg — side-effect dependencies (auth guards, audit writers) that run before the handler and whose return values are discarded; sub-dependencies resolved via normal DI; `HTTPException` short-circuits the request (FastAPI parity, DX Gap #2)
- OAuth2 scopes enforcement scaffolding: `Security(dependency, *, scopes=[...])` marker, `SecurityScopes` injected context, per-route scope aggregation, and OpenAPI `operation.security` scope reflection (FastAPI parity, DX Gap #4)
- Competitive benchmark CI: weekly cron + release-trigger runs the full `benchmarks/competitive/` suite on `ubuntu-latest` with wrk, auto-PRs refreshed `RESULTS.md`, uploads release artefacts; ships `docs/guide/benchmarks.md` + README Performance section

## [0.1.2] - 2026-04-05

### Added

- CSRF Middleware (double-submit cookie pattern)
- Session Middleware (signed cookie sessions)
- Redis Rate Limiter (`RedisRateLimitMiddleware`)
- Per-route middleware support (`@app.get("/path", middleware=[...])`)
- Streaming request body (`request.stream()`)
- MessagePack content negotiation
- W3C Trace Context propagation (traceparent/tracestate)
- Plugin API new hooks: `on_startup`, `on_shutdown`, `on_exception`, `on_middleware_added`
- `hawkapi init` CLI command
- TestClient cookie jar with automatic Set-Cookie tracking
- TestClient `CaseInsensitiveDict` headers
- TestClient assertion helpers: `is_success`, `is_redirect`, `raise_for_status()`
- `MiddlewareEntry` dataclass for typed middleware configuration
- Improved scaffold templates with DI, middleware, and test examples
- New benchmarks: streaming, WebSocket, concurrent load, memory profiling

### Fixed

- Multipart `rstrip` corrupting binary uploads
- StreamingResponse not sending terminal ASGI chunk on error
- CRLF injection in RedirectResponse
- Radix tree silent param name/type conflicts
- Circuit breaker holding asyncio.Lock during I/O
- X-Forwarded-For IP spoofing (now uses rightmost non-trusted)
- HEAD responses preserving correct Content-Length
- Generator dependency cleanup distinguishes success/error
- Duplicate Content-Length in middleware after_response hook
- GZip double-compression of already-encoded responses
- FileResponse more_body flag on exact chunk boundaries
- asyncio.Lock created lazily in DI Provider
- Settings._coerce crash on Optional[T] types
- WebSocket send methods now check connection state
- Cookie parser strips RFC 6265 quoted values
- And 40+ additional bug fixes across all modules

### Changed

- `app.py` refactored: extracted `_docs.py`, `_health.py`, `_execute_route()`
- Controller instances created per-request (was shared singleton)
- Middleware stack uses `MiddlewareEntry` dataclass
- Development Status changed from "Production/Stable" to "Beta"

## [0.1.1] - 2026-03-04

### Added

- `PrometheusMiddleware` — Prometheus `/metrics` endpoint (extra: `hawkapi[metrics]`)
- `StructuredLoggingMiddleware` — JSON-structured request/response logs with request ID tracking (extra: `hawkapi[logging]`)
- `CircuitBreakerMiddleware` — three-state circuit breaker pattern (closed → open → half-open)
- `TrustedProxyMiddleware` — X-Forwarded-For/Proto/Host handling with IP validation
- `RequestLimitsMiddleware` — query string and header size limits
- `DebugMiddleware` — `/_debug/routes` and `/_debug/stats` endpoints for development
- `/readyz` and `/livez` Kubernetes health probe endpoints
- Deprecation headers: `Deprecation`, `Sunset`, and `Link` for deprecated routes
- Pagination helpers: `Page[T]`, `CursorPage[T]`, `PaginationParams`, `CursorParams`
- OpenAPI `example` support on parameter markers (`Query`, `Path`, `Header`, `Body`, `Cookie`)
- `hawkapi new` CLI command for project scaffolding
- `hawkapi check` CLI command with built-in OpenAPI linter
- `hawkapi changelog` CLI command for changelog generation
- `hawkapi diff` CLI command for API breaking changes detection
- Contract smoke test generator
- DI container introspection and Mermaid diagram generation
- Plugin API with route registration and schema generation hooks
- Client SDK generation templates for TypeScript and Python
- Docker template and deployment guide
- FastAPI migration guide
- E2E benchmark suite and GitHub Action
- PyPI publish workflow (trusted publishing)

### Fixed

- Singleton provider race condition: eager lock initialization + `_UNSET` sentinel for `None` caching
- `StreamingResponse` now only sends terminal frame on successful completion
- `CircuitBreakerMiddleware` state transitions protected with `asyncio.Lock`
- `ObservabilityMiddleware` always records metrics/logs via `try/finally`
- WebSocket 404: consume `websocket.connect` before sending close frame (ASGI protocol)
- Security schemes (`HTTPBearer`, `HTTPBasic`, `OAuth2PasswordBearer`) return `WWW-Authenticate` header on 401
- `MissingCredentialError` propagates `headers` dict to error response
- Empty bearer/OAuth2 token detection (whitespace-only tokens rejected)
- `BackgroundTasks` handles `functools.partial` via `getattr(func, "__name__", repr(func))`
- `Page` division by zero when `size <= 0`
- `detect_breaking_changes` parameter keying uses `(name, in)` tuple per OpenAPI spec
- `detect_breaking_changes` resolves `$ref` in response schemas
- `TrustedProxyMiddleware` validates IP addresses with `ipaddress.ip_address()`
- `JSONResponse` deduplicates Content-Type header when caller provides one
- `StructuredLoggingMiddleware` configures structlog only once across instances
- Radix tree `find_allowed_methods` path normalization matches `lookup()` behavior
- OpenAPI schema shallow-copies operation dict for multi-method routes
- Scaffold Dockerfile uses `uvicorn` instead of non-existent `hawkapi run`

### Changed

- Project status upgraded to Production/Stable (PyPI classifier)

### Docs

- Fixed middleware guide: replaced non-existent `handle(call_next)` with `before_request`/`after_response` hooks
- Fixed middleware table: expanded from 6 to 15 middleware
- Fixed `StreamingResponse` parameter: `media_type` → `content_type`
- Removed non-existent `shutdown_drain_timeout` from configuration guide
- Removed non-existent `Settings.Config` inner class from configuration guide
- Added `metrics` and `logging` extras to installation guide
- Added Deployment and Migration from FastAPI pages to MkDocs navigation
- Fixed README: `credentials.token` → `credentials.credentials`, pagination constructor, cursor parameter name

## [0.1.0] - 2026-03-03

### Added

- ASGI 3.0 application core with custom middleware pipeline
- Radix tree router with path parameters (`int`, `str`, `float`, `uuid`)
- Request/response layer: JSON, HTML, PlainText, Redirect, Streaming, File, SSE
- Dependency injection container with singleton, scoped, and transient lifecycles
- Generator dependencies with `yield` (async and sync) for resource cleanup
- Sub-dependencies: nested `Depends()` resolution with automatic cleanup ordering
- `response_model` parameter for response filtering and validation
- OpenAPI 3.1 schema auto-generation from type annotations
- Swagger UI, ReDoc, and Scalar documentation endpoints
- Middleware: CORS, GZip, Timing, Trusted Host, Security Headers, Request ID, HTTPS Redirect, Rate Limiting, Error Handler
- Security schemes: API Key (header/query/cookie), HTTP Bearer, HTTP Basic, OAuth2 Password Bearer
- WebSocket support with async iteration and dependency injection
- Class-based controllers with HTTP method decorators
- Router with prefix and tag support, sub-app mounting
- `Settings` base class with environment variable binding and profile support
- `TestClient` for synchronous testing with `pytest` integration
- Scoped DI overrides for test isolation
- `BackgroundTasks` for post-response execution
- `StaticFiles` with directory serving, HTML mode, path traversal protection, ETag, Last-Modified, Cache-Control, 304 Not Modified
- `HTTPException` with RFC 9457 Problem Details responses
- Custom exception handlers
- Request body size limits (default 10 MB)
- CLI tool (`hawkapi dev`) with auto-reload via uvicorn
- Sync handler support (auto threadpool execution)
- API Versioning: `VersionRouter` for URL-based versioning with per-version OpenAPI specs
- Breaking Changes Detector: `detect_breaking_changes()` compares OpenAPI specs
- Declarative RBAC: `PermissionPolicy` with `permissions` on routes and WebSocket endpoints
- Observability: `ObservabilityMiddleware` with structured logging, tracing (OpenTelemetry), and in-memory metrics
- Cold Start Optimization: lazy imports in `__init__.py`, `serverless=True` mode
- `Request.url` property for full URL reconstruction
- OpenAPI `x-permissions` extension for routes with permissions
- Health check endpoint (`health_url="/healthz"`, configurable or disableable)
- Request timeout (`request_timeout` parameter with `asyncio.wait_for`, returns 504)
- Graceful shutdown: in-flight request tracking with configurable drain timeout
- `content_security_policy` parameter for `SecurityHeadersMiddleware`
- `py.typed` marker for PEP 561 typed packages
- Pyright strict mode compliance (0 errors)
- MkDocs documentation site

[0.1.2]: https://github.com/ashimov/HawkAPI/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/ashimov/HawkAPI/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ashimov/HawkAPI/releases/tag/v0.1.0
