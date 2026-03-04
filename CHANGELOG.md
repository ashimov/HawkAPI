# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.1]: https://github.com/ashimov/HawkAPI/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ashimov/HawkAPI/releases/tag/v0.1.0
