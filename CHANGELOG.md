# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
