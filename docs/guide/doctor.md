# Doctor

`hawkapi doctor` is a one-shot health-check CLI that lints a running HawkAPI application for common misconfigurations across security, observability, performance, correctness, and dependency hygiene.

## Usage

```bash
hawkapi doctor <APP_SPEC> [--format={human,json}] [--severity={info,warn,error}] [--fix]
```

| Argument | Default | Description |
|---|---|---|
| `APP_SPEC` | required | `module:attr` reference, e.g. `main:app` |
| `--format` | `human` | Output format: `human` (coloured TTY) or `json` |
| `--severity` | `info` | Minimum severity to report: `info`, `warn`, or `error` |
| `--fix` | off | Apply safe auto-fixes (v1: prints a notice; no fixes implemented yet) |

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | No findings at or above the chosen severity |
| `1` | At least one warning |
| `2` | At least one error |

### Example

```bash
$ hawkapi doctor main:app
hawkapi doctor — main:app

✗  DOC010  DOC010
   CORSMiddleware allows all origins ('*'). This exposes all endpoints to any origin.
   Fix: Whitelist specific origins in CORSMiddleware(allow_origins=[...]).
   https://hawkapi.ashimov.com/doctor/DOC010

⚠  DOC011  DOC011
   State-changing routes (POST/PUT/PATCH/DELETE) exist but CSRFMiddleware is not installed.
   Fix: Add app.add_middleware(CSRFMiddleware, secret=...) to protect browser-facing endpoints.
   https://hawkapi.ashimov.com/doctor/DOC011

Summary: 1 errors, 1 warnings, 0 info · exit 2
```

### JSON output

```bash
hawkapi doctor main:app --format=json
```

```json
{
  "app": "main:app",
  "summary": {"errors": 1, "warnings": 1, "info": 0, "total": 2},
  "findings": [
    {
      "rule_id": "DOC010",
      "severity": "error",
      "message": "CORSMiddleware allows all origins ('*').",
      "fix": "Whitelist specific origins in CORSMiddleware(allow_origins=[...]).",
      "location": null,
      "docs_url": "https://hawkapi.ashimov.com/doctor/DOC010"
    }
  ]
}
```

## Rule reference

### Security

| ID | Severity | Title | Fix |
|---|---|---|---|
| `DOC010` | error | CORS allows `*` in production | Whitelist specific origins in `CORSMiddleware(allow_origins=[...])` |
| `DOC011` | warn | CSRFMiddleware not installed but state-changing routes exist | Add `CSRFMiddleware` |
| `DOC012` | warn | TrustedProxyMiddleware missing behind a known proxy | Add `TrustedProxyMiddleware` |
| `DOC013` | error | Hardcoded placeholder secrets on `app.state` | Load secrets from env vars or a secrets manager |
| `DOC014` | info/warn | HTTPSRedirectMiddleware absent | Add `HTTPSRedirectMiddleware` (warn if `ENV=production`) |

### Observability

| ID | Severity | Title | Fix |
|---|---|---|---|
| `DOC020` | warn | No request-ID / observability middleware | Add `RequestIDMiddleware` or `StructuredLoggingMiddleware` |
| `DOC021` | info | No `/metrics` endpoint (prometheus_client installed) | Add `PrometheusMiddleware` |
| `DOC022` | info | opentelemetry installed but no OTel wiring | Install hawkapi-otel and register the plugin |
| `DOC023` | info | sentry_sdk installed but no Sentry wiring | Install hawkapi-sentry and register the plugin |

### Performance

| ID | Severity | Title | Fix |
|---|---|---|---|
| `DOC030` | info/error | `debug=True` in production | Set `debug=False` (error if `ENV=production`) |
| `DOC031` | warn | GZipMiddleware absent and routes return large payloads | Add `GZipMiddleware(minimum_size=1000)` |
| `DOC032` | warn | Handler returns bare `dict`/`list` without `response_model` | Add a msgspec.Struct return annotation |
| `DOC033` | info | Heavy I/O routes without a bulkhead | Wrap with `@bulkhead(...)` |

### Correctness

| ID | Severity | Title | Fix |
|---|---|---|---|
| `DOC040` | info | Route handler missing return annotation | Add a return type annotation |
| `DOC041` | info | Route without docstring or `summary=` | Add a docstring or `summary=` parameter |
| `DOC042` | warn | Suspicious middleware order: CORS after auth | Add `CORSMiddleware` before authentication middleware |

### Dependencies

| ID | Severity | Title | Fix |
|---|---|---|---|
| `DOC050` | info | HawkAPI version older than latest on PyPI | `pip install --upgrade hawkapi` |
| `DOC051` | warn | msgspec < 0.19 | `pip install --upgrade 'msgspec>=0.19'` |

## `--fix` mode

`--fix` is reserved for safe, deterministic auto-fixes. In v1, no rules implement `auto_fix`, so the flag prints a notice and exits normally. Future rules may opt in on a case-by-case basis.

## CI integration

Add a step to your GitHub Actions workflow to gate deployments on doctor output:

```yaml
- name: hawkapi doctor
  run: |
    uv run hawkapi doctor main:app --severity=warn --format=json
```

This step exits non-zero if any warning or error is found, blocking the workflow. Use `--severity=error` to only gate on errors:

```yaml
- name: hawkapi doctor (errors only)
  run: uv run hawkapi doctor main:app --severity=error
```
