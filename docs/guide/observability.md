# Observability

HawkAPI provides built-in observability with one flag: tracing, structured logs, and metrics.

## Quick Start

```python
from hawkapi import HawkAPI

app = HawkAPI(observability=True)
```

This enables:

- **Request ID** — generated or forwarded via `x-request-id` header
- **Structured JSON logging** — method, path, status, duration per request
- **In-memory metrics** — request count, error count, average duration
- **OpenTelemetry tracing** — if `opentelemetry` is installed

## Custom Config

```python
from hawkapi import HawkAPI, ObservabilityConfig

config = ObservabilityConfig(
    enable_tracing=True,
    enable_logging=True,
    enable_metrics=True,
    log_level="INFO",
    trace_sample_rate=0.5,
    service_name="my-api",
    request_id_header="x-request-id",
)

app = HawkAPI(observability=config)
```

## OpenTelemetry

Install the optional dependency:

```bash
pip install "hawkapi[otel]"
```

When `opentelemetry` is available, each request is wrapped in a trace span with `http.method` and `http.target` attributes.

If OpenTelemetry is not installed, tracing is silently skipped — no errors.

## W3C Trace Context

The observability middleware supports [W3C Trace Context](https://www.w3.org/TR/trace-context/) propagation. When an incoming request contains a `traceparent` header, the middleware extracts the trace ID and generates a new span ID. If no `traceparent` is present, new IDs are generated automatically.

The extracted values are stored in the ASGI scope and injected into the response:

```text
Request:  traceparent: 00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01
                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^
                            trace_id                          parent_id

Response: traceparent: 00-4bf92f3577b16e0714f34b92bd2fa926-a1b2c3d4e5f60718-01
                            (same trace_id)                   (new span_id)
```

Access the trace and span IDs inside a route handler via the ASGI scope:

```python
@app.get("/orders")
async def list_orders(scope: dict):
    trace_id = scope.get("trace_id", "")
    span_id = scope.get("span_id", "")
    # Pass trace_id to downstream services for distributed tracing
    return {"trace_id": trace_id}
```

The `tracestate` header (vendor-specific key-value pairs) is also propagated when present. If OpenTelemetry is installed, the middleware uses its propagation API; otherwise it falls back to built-in W3C parsing.

## Error Resilience

The observability middleware is wrapped in error handling. If tracing, metrics, or logging fail, the request is still processed normally — observability never crashes your application.
