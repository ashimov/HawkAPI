# Wave 2 — `hawkapi doctor` — design spec

**Status:** Approved — ready for implementation
**Date:** 2026-04-19
**Scope:** Ship `hawkapi doctor app:app` — a one-shot health check that lints a running HawkAPI application for common misconfigurations across security, observability, performance, correctness, and dependency hygiene. Produces human-readable or JSON output, exits non-zero on warn/error findings.

---

## Goal

```bash
$ hawkapi doctor app:app
🩺 hawkapi doctor — app:app
   Scanned 42 routes, 8 middleware, 3 plugins

✗  DOC010  CORS allows '*' in production
   Fix: whitelist specific origins in CORSMiddleware.
   https://hawkapi.ashimov.com/doctor/DOC010

⚠  DOC003  /api/v1/users:POST
   No response_model declared; handler returns dict.
   Fix: add a msgspec.Struct return annotation.
   https://hawkapi.ashimov.com/doctor/DOC003

Summary: 1 errors, 1 warnings, 0 info · exit 1
```

## CLI surface

```
hawkapi doctor <APP_SPEC> [--format={human,json}] [--severity={info,warn,error}] [--fix]
```

- `APP_SPEC` — `module:attr` form (same as `hawkapi dev`, `hawkapi check`).
- `--format` — `human` (default, coloured if TTY) or `json` (machine-readable).
- `--severity` — minimum severity to report. Default `info` (everything).
- `--fix` — apply safe, deterministic fixes where a rule supports `auto_fix`. v1: very few rules support this; print `"no auto-fixes available"` when none apply.
- Exit codes: `0` = no findings at the chosen severity or above. `1` = at least one warn. `2` = at least one error.

## Rule architecture

```python
from enum import IntEnum
from dataclasses import dataclass
from typing import Protocol

class Severity(IntEnum):
    INFO = 1
    WARN = 2
    ERROR = 3

@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    severity: Severity
    message: str
    fix: str | None = None
    location: str | None = None  # e.g. "POST /api/v1/users"
    docs_url: str | None = None

class Rule(Protocol):
    id: str
    category: str         # security | observability | performance | correctness | deps
    severity: Severity    # default severity (actual finding can override)
    title: str
    docs_url: str
    def check(self, app: "HawkAPI") -> list[Finding]: ...
```

Rules are discovered from a static list in `src/hawkapi/doctor/rules/__init__.py` (no dynamic plugin discovery in v1 — keep it simple, auditable).

## Rules v1

### Security (5)
- `DOC010` **CORS allows `*` in production.** Detect `CORSMiddleware(allow_origins=["*"])` or equivalent.
- `DOC011` **CSRFMiddleware not installed but state-changing routes exist.** Warns if any POST/PUT/PATCH/DELETE route is registered and CSRFMiddleware is absent.
- `DOC012` **TrustedProxyMiddleware missing behind a known proxy.** Warns if `X-Forwarded-*` headers may be parsed without trust configured.
- `DOC013` **Bearer/OAuth2 auth with hardcoded secrets.** Scan `OAuth2PasswordBearer(tokenUrl=...)` for URL + check Settings/env for obvious placeholders (`changeme`, `secret`, `dev`).
- `DOC014` **HTTPSRedirectMiddleware absent.** Info-level in dev, warn if `ENV=production` env var is set.

### Observability (4)
- `DOC020` **No Request-ID / structured-logging / observability middleware installed.** Warn — one-line fix.
- `DOC021` **No `/metrics` endpoint.** If `PrometheusMiddleware` absent and an observability stack is likely (OTel plugin, Prometheus plugin deps installed), info.
- `DOC022` **No OTel wiring.** If `opentelemetry` is importable but no `hawkapi-otel` plugin registered, info.
- `DOC023` **No Sentry wiring.** If `sentry_sdk` is importable but `hawkapi-sentry` plugin absent, info.

### Performance (4)
- `DOC030` **`debug=True` on HawkAPI constructor in what looks like a production app.** Error if `ENV=production` else info.
- `DOC031` **GZipMiddleware absent and routes return >1 KiB JSON on average.** Warn — static analysis of `response_model` payloads.
- `DOC032` **Handler returning `dict`/`list` primitives without `response_model`.** Warn — auto-inference only catches msgspec/Pydantic types. Bare dict response bypasses filtering.
- `DOC033` **No bulkhead on routes that look like heavy I/O** (handler signature contains `db` / `session` / `http_client` / `redis`). Info.

### Correctness (3)
- `DOC040` **Route handler missing return annotation.** Info — blocks auto-`response_model` inference.
- `DOC041` **Route without docstring or `summary=`.** Info — produces empty OpenAPI summary.
- `DOC042` **Middleware order suspicious.** Warn if `CORSMiddleware` appears after authentication-style middleware (heuristic: any middleware named `*Auth*` / class of `HTTPBearer`-using middleware). Order matters: CORS should run first.

### Dependencies (2)
- `DOC050` **HawkAPI version older than latest published.** Info — read `hawkapi.__version__`, fetch latest from PyPI (best-effort; skip if offline).
- `DOC051` **`msgspec` version < 0.19.** Warn — known perf gap.

### Total: 18 rules. Easy to extend by adding a file under `rules/`.

## Output formats

### Human (default)
- Group by severity (errors first, then warnings, then info).
- Emoji prefix per severity (`✗` error / `⚠` warn / `ℹ` info), coloured when stdout is a TTY (use `rich` if already in deps, else plain ANSI codes).
- Footer summary line with counts and exit code.

### JSON
```json
{
  "app": "app:app",
  "summary": {"errors": 1, "warnings": 1, "info": 0, "total": 2},
  "findings": [
    {"rule_id": "DOC010", "severity": "error", "message": "...", "fix": "...", "location": null, "docs_url": "..."}
  ]
}
```

## `--fix` mode (v1)

Applies only to rules that declare `auto_fix: Callable[[HawkAPI], bool]`. v1 ships zero `auto_fix` implementations — print `"--fix: no auto-fixable findings"` and exit per severity rule. The infrastructure is there, but each rule must opt in carefully (most need user judgement).

## Module layout

```
src/hawkapi/doctor/
    __init__.py           # re-exports Rule, Finding, Severity, run()
    _runner.py            # orchestration: load app, run rules, filter, format, exit
    _formatter.py         # human + json output
    _types.py             # Rule Protocol, Finding, Severity
    rules/
        __init__.py       # ALL_RULES = [...] static list
        security.py       # DOC010–DOC014
        observability.py  # DOC020–DOC023
        performance.py    # DOC030–DOC033
        correctness.py    # DOC040–DOC042
        deps.py           # DOC050–DOC051

src/hawkapi/cli.py
    +doctor subcommand wiring
```

Each file < 200 lines.

## Tests — `tests/unit/test_doctor.py`

~25 tests. For each rule: one happy-path (clean app → no finding), one failing-path (misconfigured app → finding). Plus:
- `_runner.run(app)` returns findings list.
- `--format=json` output shape.
- `--severity=warn` filters info.
- Exit code mapping.
- CLI smoke test (`hawkapi doctor app:app` via `subprocess`).

## Docs — `docs/guide/doctor.md`

- Overview + usage.
- Full rule reference table (ID, category, severity, description, fix).
- `--fix` caveat.
- CI integration example (one-liner GitHub Actions step).

## Mkdocs nav + CHANGELOG

- `mkdocs.yml`: `- Doctor: guide/doctor.md` after "OpenAPI linter".
- `CHANGELOG.md`: `[Unreleased] ### Added` bullet → target v0.1.4.
- README.md: add a short "Doctor" subsection under "CLI" or "Production Features".

## Out of scope (v2+)

- Dynamic rule discovery (entry points / plugins).
- `--fix` with actual auto-fixes (needs per-rule careful design).
- Runtime traffic analysis (would require proxy/sniffer).
- Config-file output (`.hawkapi-doctor.toml` for rule overrides).
- IDE integration (SARIF/LSP) — could be a follow-up.

## Success criteria

1. `hawkapi doctor app:app` runs all 18 rules on a real HawkAPI app.
2. Exit codes map: clean → 0, warn → 1, error → 2.
3. `--format=json` produces stable schema.
4. CHANGELOG + docs + mkdocs nav entry present and mkdocs strict-clean.
5. Full suite + ruff + pyright-strict clean.

## Files touched

- `src/hawkapi/doctor/**` — new (10 files)
- `src/hawkapi/cli.py` — add `doctor` subcommand
- `tests/unit/test_doctor.py` — new
- `docs/guide/doctor.md` — new
- `mkdocs.yml` — nav entry
- `CHANGELOG.md` — bullet
- `README.md` — add Doctor subsection

## Rollback

New module + new CLI subcommand + new docs. No existing paths change. Revert = delete `doctor/` package, remove one argparse subparser, revert three doc diffs.
