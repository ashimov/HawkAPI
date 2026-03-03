# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/ashimov/HawkAPI/releases/tag/v0.1.0
