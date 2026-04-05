# Middleware

HawkAPI supports composable ASGI middleware.

## Adding Middleware

### Hook-Based (convenient)

```python
from hawkapi import HawkAPI, Middleware, Request, Response
import time

class TimingMiddleware(Middleware):
    async def before_request(self, request: Request):
        request.state.start_time = time.monotonic()
        return None  # continue processing

    async def after_response(self, request: Request, response: Response):
        elapsed = time.monotonic() - request.state.start_time
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        return response

app = HawkAPI()
app.add_middleware(TimingMiddleware)
```

### Raw ASGI (maximum performance)

```python
from hawkapi import Middleware

class TimingMiddleware(Middleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import time
        start = time.monotonic()
        await self.app(scope, receive, send)
        elapsed = time.monotonic() - start
        print(f"Request took {elapsed:.3f}s")

app.add_middleware(TimingMiddleware)
```

## Built-in Middleware

| Middleware | Description | Extra |
|-----------|-------------|-------|
| `CSRFMiddleware` | CSRF protection (double-submit cookie) | — |
| `SessionMiddleware` | Signed cookie-based sessions | — |
| `RedisRateLimitMiddleware` | Redis-backed rate limiting | `redis` |
| `CORSMiddleware` | Cross-Origin Resource Sharing | — |
| `GZipMiddleware` | Response compression | — |
| `RateLimitMiddleware` | In-memory rate limiting | — |
| `TrustedHostMiddleware` | Host header validation | — |
| `SecurityHeadersMiddleware` | Security response headers | — |
| `RequestIDMiddleware` | Request ID generation/forwarding | — |
| `TimingMiddleware` | Server-Timing header | — |
| `HTTPSRedirectMiddleware` | HTTP → HTTPS redirect | — |
| `ErrorHandlerMiddleware` | Global exception handler | — |
| `DebugMiddleware` | Debug info in error responses | — |
| `CircuitBreakerMiddleware` | Circuit breaker pattern | — |
| `TrustedProxyMiddleware` | X-Forwarded-* handling | — |
| `RequestLimitsMiddleware` | Query/header size limits | — |
| `StructuredLoggingMiddleware` | JSON-structured request logs | `logging` |
| `PrometheusMiddleware` | Prometheus metrics endpoint | `metrics` |

## CORS Example

```python
from hawkapi.middleware import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization"],
)
```

## Circuit Breaker

```python
from hawkapi.middleware import CircuitBreakerMiddleware

app.add_middleware(
    CircuitBreakerMiddleware,
    failure_threshold=5,
    recovery_timeout=30.0,
)
```

## Structured Logging

Requires: `pip install "hawkapi[logging]"`

```python
from hawkapi.middleware.structured_logging import StructuredLoggingMiddleware

app.add_middleware(StructuredLoggingMiddleware)
```

Emits JSON logs with request ID, method, path, status, and duration.

## Prometheus Metrics

Requires: `pip install "hawkapi[metrics]"`

```python
from hawkapi.middleware.prometheus import PrometheusMiddleware

app.add_middleware(PrometheusMiddleware)
# GET /metrics -> Prometheus-format metrics
```

## CSRF Middleware

HawkAPI includes CSRF protection using the **double-submit cookie** pattern. A CSRF token is set in a cookie on safe requests (GET, HEAD, OPTIONS) and must be echoed back via a header or form field on unsafe requests (POST, PUT, DELETE, PATCH).

```python
from hawkapi.middleware.csrf import CSRFMiddleware

app.add_middleware(
    CSRFMiddleware,
    secret="your-secret-key",
)
```

On safe requests, the middleware sets a `csrftoken` cookie automatically. On unsafe requests, the client must send the token back via the `X-CSRF-Token` header or a `csrf_token` form field. If the token is missing or does not match, a 403 response is returned.

| Option | Default | Description |
|--------|---------|-------------|
| `secret` | *required* | Secret key for HMAC-SHA256 token signing |
| `cookie_name` | `"csrftoken"` | Name of the CSRF cookie |
| `header_name` | `"x-csrf-token"` | Header to read the token from |
| `safe_methods` | `GET, HEAD, OPTIONS, TRACE` | Methods that skip validation |
| `cookie_path` | `"/"` | Cookie path |
| `cookie_httponly` | `False` | Whether the cookie is HttpOnly |
| `cookie_secure` | `True` | Whether the cookie requires HTTPS |
| `cookie_samesite` | `"lax"` | SameSite attribute |

## Session Middleware

Signed cookie-based sessions using HMAC-SHA256. Session data is serialized with `msgspec.json`, base64url-encoded, and stored in a signed cookie. No server-side storage is required.

```python
from hawkapi.middleware.session import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key",
)
```

Reading and writing session data in a route handler:

```python
@app.post("/login")
async def login(scope: dict):
    scope["session"]["user_id"] = 42
    return {"status": "logged in"}

@app.get("/me")
async def me(scope: dict):
    user_id = scope["session"].get("user_id")
    return {"user_id": user_id}
```

The middleware detects changes automatically and only sets the cookie when the session data has been modified.

| Option | Default | Description |
|--------|---------|-------------|
| `secret_key` | *required* | Secret key for HMAC-SHA256 signing |
| `session_cookie` | `"session"` | Cookie name |
| `max_age` | `1209600` (14 days) | Cookie max age in seconds |
| `path` | `"/"` | Cookie path |
| `httponly` | `True` | Whether the cookie is HttpOnly |
| `secure` | `True` | Whether the cookie requires HTTPS |
| `samesite` | `"lax"` | SameSite attribute |

## Redis Rate Limiter

A Redis-backed rate limiter using the **token bucket** algorithm. Uses a Lua script for atomic operations, so it is safe across multiple processes. Falls back to in-memory rate limiting if Redis is unavailable.

Requires: `pip install redis` (or `pip install "hawkapi[redis]"`)

```python
from hawkapi.middleware.rate_limit_redis import RedisRateLimitMiddleware

app.add_middleware(
    RedisRateLimitMiddleware,
    redis_url="redis://localhost:6379",
    requests_per_second=10.0,
    burst=20,
)
```

Custom key functions let you rate-limit by API key, user ID, or any other attribute:

```python
def key_by_api_key(scope):
    for key, value in scope.get("headers", []):
        if key == b"x-api-key":
            return value.decode("latin-1")
    return "anonymous"

app.add_middleware(
    RedisRateLimitMiddleware,
    key_func=key_by_api_key,
)
```

| Option | Default | Description |
|--------|---------|-------------|
| `redis_url` | `"redis://localhost:6379"` | Redis connection URL |
| `requests_per_second` | `10.0` | Sustained request rate |
| `burst` | `0` (uses `requests_per_second`) | Maximum burst size |
| `key_func` | client IP | `(scope) -> str` callable for bucket keys |
| `key_prefix` | `"hawkapi:rl:"` | Redis key prefix |

## Per-Route Middleware

Middleware can be applied to individual routes instead of the entire application. Pass a `middleware` list to the route decorator:

```python
from hawkapi.middleware.csrf import CSRFMiddleware

@app.post("/checkout", middleware=[(CSRFMiddleware, {"secret": "s3cret"})])
async def checkout():
    return {"status": "ok"}
```

Each entry in the list can be either a middleware class (applied with no extra arguments) or a tuple of `(MiddlewareClass, kwargs_dict)`. Per-route middleware runs *inside* the global middleware stack, only for that specific route.

## MiddlewareEntry Dataclass

As a typed alternative to `(class, kwargs)` tuples, you can use the `MiddlewareEntry` dataclass when building middleware pipelines programmatically:

```python
from hawkapi.middleware import MiddlewareEntry
from hawkapi.middleware.csrf import CSRFMiddleware

entry = MiddlewareEntry(cls=CSRFMiddleware, kwargs={"secret": "s3cret"})
```

## Middleware Order

Middleware is applied in order: first added = outermost (runs first).
