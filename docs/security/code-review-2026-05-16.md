# HawkAPI 0.1.5 Focused Security Code Review

Date: 2026-05-16
Scope: `security/**`, selected middleware, request/response boundaries, `staticfiles.py`.
Confidence threshold: HIGH only. Already-fixed items from 0.1.5 not repeated.

## HIGH

### H-1. GraphQL GET can execute mutations via multi-operation document (CWE-352)

- File: `src/hawkapi/graphql/_handler.py:43-50, 76-91`
- Issue: `_is_mutation` inspects only the first non-comment token. A request `GET /graphql?query=query+A+{…}+mutation+B+{…}&operationName=B` passes the GET-mutation guard and runs `mutation B`.
- Impact: CSRF on mutations — image tags, prefetch, cache poisoning can all trigger writes.
- Fix: parse the document with the executor's parser before dispatch; reject GET whenever any `OperationDefinition` whose `name` matches `operationName` (or the only operation, if `operationName` is omitted) has `operation != "query"`.

### H-2. Unauthenticated identity headers feed flag targeting (CWE-290)

- File: `src/hawkapi/flags/_di.py:21-26`
- Issue: `EvalContext(user_id=request.headers.get("x-user-id"), tenant_id=request.headers.get("x-tenant-id"))` trusts client-supplied headers as identity for flag evaluation.
- Impact: any flag gated on `user_id == "alice"` (admin previews, sensitive feature toggles) can be reached by anyone with `X-User-Id: alice`.
- Fix: remove implicit header read; require operator to pass explicit `context_factory`. Default `EvalContext()` must be empty.

### H-3. GraphQL endpoint has no depth, complexity or timeout limit (CWE-770)

- File: `src/hawkapi/graphql/_handler.py:119-128`
- Issue: `await executor(...)` runs to completion with no in-band budget; nested-selection / alias-explosion queries pin a worker indefinitely.
- Impact: single unauthenticated request → worker DoS.
- Fix: wrap executor call in `asyncio.wait_for(...)`; add `max_depth` that pre-walks the parsed document and short-circuits with 400.

## MEDIUM

### M-1. gRPC server runs with unbounded concurrent RPCs

- File: `src/hawkapi/grpc/_mount.py:70-74`
- Issue: `grpc.aio.server(...)` started without `maximum_concurrent_rpcs`; HTTP rate-limit / bulkhead middleware does not cover the gRPC port.
- Fix: expose `maximum_concurrent_rpcs: int | None = 1000` on `mount_grpc`.

### M-2. GraphiQL UI enabled by default

- File: `src/hawkapi/graphql/_handler.py:57-74`
- Issue: `graphiql: bool = True` default. UI ships in every deployment; combined with no introspection control the schema is publicly browsable in prod.
- Fix: change default to `False`.

### M-3. `RedisBulkheadBackend._try_acquire_once` is racy (CWE-662)

- File: `src/hawkapi/middleware/bulkhead_redis.py:50-67`
- Issue: `HSET` → `HLEN` → conditional `HDEL` pipelined but not transactional. Multiple acquirers may each `HSET` first then read `occupancy ≤ limit` and all stay registered.
- Fix: replace pipeline with Lua script doing `HLEN` first, returning 0 when full, only then `HSET`.

### M-4. CSRF middleware never validates the HMAC it generates

- File: `src/hawkapi/middleware/csrf.py:67-78, 197-224`
- Issue: `_generate_token` produces `{raw}.{hmac(raw)}`, but `_verify_token` is dead code — the unsafe-method path only does `hmac.compare_digest(submitted_token, cookie_token)`. `secret=` param is functionally unused.
- Impact: not exploitable today (double-submit equality is enough), but API misleads operators and future changes can regress silently.
- Fix: call `_verify_token` on both before equality check, or drop the dead `_verify_token`/`_secret` API.

## LOW

- **L-1.** Session middleware claims "optionally encrypted" but is sign-only (`middleware/session.py:25-27`). Docstring fix or add AES-GCM.
- **L-2.** CSRF cookie `HttpOnly=False` by design (`middleware/csrf.py:38`); document the trade-off.
- **L-3.** Multipart parser has no `max_parts` cap (`requests/form_data.py:96-146`). Default 1000 recommended.
- **L-4.** Multipart `Content-Type` boundary split breaks on quoted `;` (`requests/request.py:226-234`).
- **L-5.** Response header **names** not CRLF-scrubbed (`responses/response.py:62-69`); raise on `\r`/`\n`/`:` in key.
- **L-6.** `FileResponse` does not constrain `path` to a base dir (`responses/file_response.py:33-37`); add optional `root=`.
- **L-7.** CORS `expose_headers` / `allow_methods` not CRLF-scrubbed before joining (`middleware/cors.py:67-90`).
- **L-8.** `RateLimitMiddleware._default_key_func` uses raw `scope["client"]`; docstring should advise placing `TrustedProxyMiddleware` first.

## Executive Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH     | 3 |
| MEDIUM   | 4 |
| LOW      | 8 |

Already-fixed items NOT re-reported (per 0.1.5 CHANGELOG): StreamingResponse double-execution, path-param coercion, GraphiQL SRI, FileFlagProvider mtime ordering, `_execute_trivial_route` lazy-import hoisting.
