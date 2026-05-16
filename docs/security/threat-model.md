# HawkAPI Threat Model

Date: 2026-05-16
Scope: five subsystems landed in 0.1.3 – 0.1.5.
Method: STRIDE per subsystem (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege).
Severity scale for residual risk: LOW / MEDIUM / HIGH / CRITICAL.

---

## 1. `hawkapi.doctor`

| Threat | Vector | Mitigation | Residual |
|---|---|---|---|
| S | Forged PyPI version response misleads operator about install state | Hard-coded HTTPS URL, 2 s timeout, soft-fail | LOW |
| T | Malicious `module:attr` argument executes attacker code during health check | By design — developer tool | LOW |
| R | Findings only printed to stdout; no audit trail | N/A | LOW |
| I | `DOC013` prints `app.state.<attr>` values verbatim | Only six placeholder strings flagged | LOW |
| D | DOC050 PyPI fetch hangs CI | 2 s timeout, `--offline` opt-out | LOW |
| E | Rules read `app.routes` / `app.state` via attribute access only | N/A | LOW |

No MEDIUM+ residuals.

## 2. `hawkapi.grpc`

| Threat | Vector | Mitigation | Residual |
|---|---|---|---|
| S | Peer impersonation when `ssl_credentials=None` | TLS passthrough supported | LOW |
| T | gRPC body tampering | Handled by `grpcio` framing | LOW |
| R | Per-RPC structured log | Built-in interceptor | LOW |
| I | Reflection in prod leaks service schema | Opt-in: `reflection=False` default | LOW |
| D | `grpc.aio.server(maximum_concurrent_rpcs=None)` — unbounded RPCs; HTTP middleware does not apply to gRPC port | None | **MEDIUM** |
| E | Servicers receive full app reference | By design | LOW |

## 3. `hawkapi.graphql`

| Threat | Vector | Mitigation | Residual |
|---|---|---|---|
| T | **GET request can run a mutation.** `_is_mutation(query)` checks only the first non-comment token. A document `query A {…} mutation B {…}` with `operationName=B` passes the GET guard, executor runs `mutation B` | First-token check only | **HIGH** (CWE-352) |
| I | `graphiql=True` default; UI lets any browser visitor introspect schema in any environment | SRI + pinned CDN (0.1.5) | **MEDIUM** (CWE-200) |
| D | No depth / complexity / cost / timeout limit | None | **HIGH** (CWE-770 / CWE-1284) |
| D | JSON body up to 10 MB | Body-size cap inherited | LOW |
| E | Auth via operator `context_factory` — no automatic enforcement | Documented | LOW |

## 4. `hawkapi.flags`

| Threat | Vector | Mitigation | Residual |
|---|---|---|---|
| S | **`get_flags` builds `EvalContext(user_id=request.headers.get("x-user-id"), ...)` from unauthenticated headers** — any client can claim any identity for flag targeting | None | **HIGH** (CWE-290) |
| T | `FileFlagProvider` reloads via mtime; trusted writer assumed | Cache-then-mtime ordering (0.1.5) | LOW |
| R | `on_flag_evaluated` plugin hook | Operator-supplied sink | LOW |
| I | `Flags._dispatch_hook` swallows hook exceptions | Documented | LOW |
| D | YAML provider uses `yaml.safe_load` | Safe loader | LOW |
| E | `@requires_flag` fails closed | Fail-closed | LOW |

## 5. `hawkapi.middleware.bulkhead` + `RedisBulkheadBackend`

| Threat | Vector | Mitigation | Residual |
|---|---|---|---|
| T | `_try_acquire_once` pipelines `HSET`/`HLEN`/`PEXPIRE`/conditional `HDEL` but combination is not atomic; under contention multiple acquirers can each observe `occupancy ≤ limit` and stay registered | Documented as "sloppy semaphore" | **MEDIUM** (CWE-662) |
| R | Lease IDs not logged by default | Optional Prometheus | LOW |
| I | `reap_expired_leases` does `HGETALL` — O(n) | Operator triggers reap | LOW |
| D | Crashed worker leaves lease until reap | Bounded by `lease_ttl` | LOW |
| E | Bulkheads gate concurrency, not authorisation | N/A | LOW |

## Executive Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 3 |
| MEDIUM | 4 |
| LOW | many (acceptable) |

Top-3 priority fixes:

1. **`hawkapi.flags._di.get_flags`** — remove implicit `X-User-Id` / `X-Tenant-Id` ingestion; require operator-supplied `context_factory`.
2. **`hawkapi.graphql._handler._is_mutation`** — parse the document and reject GET when any selected operation is a mutation or subscription; flip `graphiql=True` to `False`.
3. **`hawkapi.graphql._handler.make_graphql_handler`** — add `max_depth` / `timeout_s` parameters; wrap executor in `asyncio.wait_for`.
