# Middleware

HawkAPI supports composable ASGI middleware.

## Adding Middleware

```python
from hawkapi import HawkAPI, Middleware

class TimingMiddleware(Middleware):
    async def handle(self, scope, receive, send, call_next):
        import time
        start = time.monotonic()
        response = await call_next(scope, receive, send)
        elapsed = time.monotonic() - start
        print(f"Request took {elapsed:.3f}s")
        return response

app = HawkAPI()
app.add_middleware(TimingMiddleware)
```

## Built-in Middleware

| Middleware | Description |
|-----------|-------------|
| `CORSMiddleware` | Cross-Origin Resource Sharing |
| `GZipMiddleware` | Response compression |
| `RateLimitMiddleware` | Rate limiting |
| `TrustedHostMiddleware` | Host header validation |
| `SecurityHeadersMiddleware` | Security response headers |
| `ObservabilityMiddleware` | Tracing, logs, metrics |

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

## Middleware Order

Middleware is applied in order: first added = outermost (runs first).
