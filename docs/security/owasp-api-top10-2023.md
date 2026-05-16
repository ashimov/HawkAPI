# OWASP API Security Top 10 — 2023 Compliance Map

Date: 2026-05-16  ·  HawkAPI version: 0.1.6
Mapping each OWASP API Top 10 (2023) category to the framework's posture and the operator's responsibility.

| API# | Category | HawkAPI provides | Operator must |
|---|---|---|---|
| **API1** | Broken Object-Level Authorization (BOLA) | `@app.get(..., permissions=["..."])` declarative permission scope + `PermissionPolicy` resolver | Implement a resolver that maps the authenticated principal to per-object roles and call it from `permissions=`. The framework does not infer object ownership |
| **API2** | Broken Authentication | `HTTPBasic`, `HTTPBearer`, `APIKeyHeader/Query/Cookie`, `OAuth2PasswordBearer` extractors; `Security(dep, scopes=[…])`; `SecurityScopes` injection; `secrets.compare_digest` documented as the only safe way to compare extracted credentials | Choose a hashing scheme (`argon2id` recommended), implement rate-limit on `/login`, rotate signing keys |
| **API3** | Broken Object-Property-Level Authorization | `response_model=` filters at the framework level + `response_model_exclude_{none,unset,defaults}` for finer redaction; msgspec Struct field omission on serialisation | Define explicit response Structs for every route — never return raw ORM objects |
| **API4** | Unrestricted Resource Consumption | `RequestLimitsMiddleware` (query / header size), body-size cap via `HawkAPI(max_body_size=…)`, `RateLimitMiddleware` (token bucket), `RedisRateLimitMiddleware` (distributed), `Bulkhead` primitive, `request_timeout`, GraphQL `max_depth` + `timeout_s` (since 0.1.6), gRPC `maximum_concurrent_rpcs=1000` default (since 0.1.6) | Tune limits to traffic profile; place `TrustedProxyMiddleware` **before** rate-limit so per-IP buckets see the real client; use bulkheads around external dependencies |
| **API5** | Broken Function-Level Authorization | Same primitives as API1 — `permissions=` per route, `Security(dep, scopes=[…])`, OpenAPI `operation.security` reflection so reviewers can audit the matrix | Document the role / function matrix; add CI test that every route either declares `permissions=` or is explicitly marked public |
| **API6** | Unrestricted Access to Sensitive Business Flows | `Bulkhead` for per-flow concurrency caps, `RateLimitMiddleware` with custom `key_func` for per-tenant / per-flow budgets, `CSRFMiddleware` (double-submit) | Identify high-value flows (signup, refund, withdrawal); apply per-flow rate limits and human-verification (CAPTCHA / webauthn) outside the framework |
| **API7** | Server-Side Request Forgery (SSRF) | Framework itself makes no outbound HTTP calls except `doctor` DOC050 (hard-coded `https://pypi.org` + scheme validation, `--offline` opt-out) | When your handler fetches a URL, validate scheme + resolved IP against allow-list; never pass user input directly to `httpx`/`requests` |
| **API8** | Security Misconfiguration | `hawkapi doctor` ships 18 rules across 5 categories (security, observability, performance, correctness, deps). CSRF/Session use HMAC by default, GraphiQL ships disabled (since 0.1.6), gRPC reflection is opt-in, headers sanitised for CRLF, debug mode flagged by doctor | Run `hawkapi doctor app:app --severity=warn` as a deploy gate; pin actions to SHAs; enable Dependabot |
| **API9** | Improper Inventory Management | OpenAPI 3.1 auto-gen, `/docs` `/redoc` `/scalar` opt-in (set `docs_url=None` for prod), version routing (`@app.get("/users", version="v1")` + `VersionRouter`), deprecation headers (RFC 8594 `Deprecation` / `Sunset` / `Link`), `detect_breaking_changes` for API governance, contract smoke tests | Track every released version in changelog; mark deprecated routes; remove docs URLs in prod or gate behind auth |
| **API10** | Unsafe Consumption of APIs | `hawkapi gen-client` produces typed TS/Python clients with response-shape validation via msgspec; OpenAPI linter enforces `operation-id-required` / response descriptions | Validate downstream API responses; rate-limit + circuit-break upstream calls (use `CircuitBreakerMiddleware` / `RedisCircuitBreakerMiddleware` on the client side) |

## Framework-level controls summary

* **Input validation**: type-driven via msgspec / Pydantic; query / path / header / body / cookie all validated.
* **Output filtering**: `response_model`, `response_model_exclude_*`, explicit Struct return types.
* **Auth primitives**: HTTPBasic / HTTPBearer / APIKey* / OAuth2 + `Security(dep, scopes=[…])`.
* **Headers**: response value CRLF-stripped; SecurityHeadersMiddleware available; trusted-proxy + IP-allowlist.
* **DoS posture**: body-size, query/header limits, rate-limit (local + Redis), bulkhead, adaptive concurrency, GraphQL depth+timeout, gRPC max concurrent RPCs.
* **Secrets**: CSRF / Session use HMAC-SHA256, `secrets.compare_digest` documented for handler-side comparison.
* **CSRF**: double-submit cookie token, signed with HMAC-SHA256.
* **Logging**: `StructuredLoggingMiddleware`, W3C Trace Context, `request.id` middleware, gRPC observability interceptor.
* **Supply chain**: weekly Bandit + Semgrep (OWASP + python + security-audit rulesets) + pip-audit + Gitleaks + CodeQL via `.github/workflows/security.yml`; Dependabot weekly.

## CI gates

Required jobs that fail the build on findings:

| Job | Tool | Severity threshold |
|---|---|---|
| Bandit | bandit | Medium and above |
| Semgrep | semgrep (p/python + p/security-audit + p/owasp-top-ten) | ERROR + WARNING |
| pip-audit | pip-audit | Any CVE (`--strict`) |
| Gitleaks | gitleaks-action | Any leak |
| CodeQL | github/codeql-action | security-extended + security-and-quality queries |

Run locally:

```bash
bandit -r src/ -ll
semgrep --config=p/python --config=p/security-audit --config=p/owasp-top-ten src/
pip-audit --strict
gitleaks detect --source .
```

## What HawkAPI deliberately does NOT do

* Authentication / authorization business logic — operator provides via DI.
* Identity from `X-User-Id` / `X-Tenant-Id` headers — never trusted by framework.
* Auto-redaction of secrets in logs — operator opts in via `StructuredLoggingMiddleware` filter.
* WAF / rule-based payload scanning — out of scope (use Cloudflare / ModSecurity in front).
