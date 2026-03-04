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

## Middleware Order

Middleware is applied in order: first added = outermost (runs first).
