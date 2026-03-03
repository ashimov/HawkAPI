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

## Error Resilience

The observability middleware is wrapped in error handling. If tracing, metrics, or logging fail, the request is still processed normally — observability never crashes your application.
