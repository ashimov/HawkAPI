# Tier 2 — Bulkhead (design spec)

**Status:** Draft — awaiting user review
**Date:** 2026-04-18
**Scope:** Named, size-limited concurrency isolation primitive with two usage forms (async context manager and route decorator) and two backends (local, Redis).

This is the first sub-project of Tier 2. Subsequent sub-projects (feature flags, GraphQL, gRPC) get their own spec/plan cycles.

---

## Goal

Give HawkAPI users a classical Hystrix-style bulkhead: isolate dependency/downstream capacity so saturation of one resource pool does not starve others. Complement — not replace — the existing `AdaptiveConcurrencyMiddleware` (global auto-tuned cap) and `RateLimit*` middleware (time-windowed request budget).

## Architecture

Single core primitive — `hawkapi.middleware.bulkhead.Bulkhead` — with:

- **Two public forms** sharing one implementation:
  - Context manager: `async with Bulkhead("stripe", limit=10, max_wait=0.5): ...`
  - Decorator: `@bulkhead("payments", limit=10)` on a route handler.
- **Pluggable backend** through a `BulkheadBackend` Protocol:
  - `LocalBulkheadBackend` (default) — `asyncio.Semaphore` per name, lazily created.
  - `RedisBulkheadBackend` (opt-in) — Redis counter + lease TTL for crash safety.

Rationale for one core / two forms: per-dependency and per-route are complementary real use cases. Per-dependency protects a downstream (Hystrix discipline); per-route caps an endpoint's concurrency. A single primitive + thin adapters keep code DRY and metrics uniform.

Rationale for pluggable backend: the local path must stay zero-overhead (sub-microsecond `acquire`/`release` over a vanilla `asyncio.Semaphore`). The Redis backend pays a network round-trip; users opt in per-bulkhead when cross-process capacity control matters. The Protocol boundary keeps both on the same user-facing API.

## Behavior

### Acquire semantics

- `max_wait = 0.0` (default) — fail-fast. `acquire()` tries the semaphore non-blocking; on no slot, raises `BulkheadFullError(name, limit, waited=0.0)`.
- `max_wait > 0` — wait up to `max_wait` seconds. On timeout, raises `BulkheadFullError(name, limit, waited=max_wait)`.
- Release is guaranteed via `try/finally` in the context manager, including on `asyncio.CancelledError`.

### Decorator → HTTP mapping

```python
@bulkhead("payments", limit=10, status_code=503, retry_after=1.0)
async def pay(...): ...
```

When the wrapped handler (or any code inside it) raises `BulkheadFullError`, the decorator converts it to an HTTP response:

- Status: `status_code` (default `503 Service Unavailable`, matching `AdaptiveConcurrencyMiddleware`). Configurable to `429` for users whose clients already handle rate-limit backoff.
- Header: `Retry-After: <retry_after>` (default `1.0`). Float-to-integer rounding up per RFC 9110 (seconds, non-negative integer).
- Body: short JSON `{"error": "bulkhead_full", "name": "...", "limit": N}`.

In context-manager form there is no HTTP mapping — the caller catches `BulkheadFullError` themselves.

### Redis lease-TTL model

Each `acquire` on the Redis backend:

1. Atomic `INCR hawkapi:bulkhead:{name}` + `SET hawkapi:bulkhead:{name}:lease:{uuid}` with TTL (default 30 s, configurable).
2. If post-INCR value > `limit`: `DECR` + `DEL` the lease + `BulkheadFullError` (or retry loop if `max_wait > 0`, backing off by `min(max_wait, 10 ms)`).
3. On `release`: `DECR hawkapi:bulkhead:{name}` + `DEL` the lease key.

If a worker crashes mid-hold, the lease key expires by TTL. A reaper (`Bulkhead.reap_expired_leases(name)` method, plus a future `hawkapi bulkhead reap` CLI subcommand) reconciles the counter with still-living lease keys.

This is the standard "sloppy distributed semaphore" pattern. Correct enough for capacity control; bounded over-capacity window is `≤ TTL` during a crash. Redlock-level correctness is explicitly not a goal.

### Error class

```python
class BulkheadFullError(Exception):
    """Raised when a Bulkhead has no capacity within the wait budget."""
    def __init__(self, name: str, limit: int, waited: float) -> None:
        super().__init__(f"bulkhead '{name}' full (limit={limit}, waited={waited:.3f}s)")
        self.name = name
        self.limit = limit
        self.waited = waited
```

### Metrics (opt-in)

When a `Bulkhead` is constructed with `metrics=True`:

- `hawkapi_bulkhead_in_flight{name}` — gauge
- `hawkapi_bulkhead_capacity{name}` — gauge, = `limit` (static; re-emitted on register)
- `hawkapi_bulkhead_rejections_total{name,reason}` — counter; `reason ∈ {"fail_fast", "timeout"}`
- `hawkapi_bulkhead_acquire_latency_seconds{name}` — histogram

Naming follows the convention already established in `src/hawkapi/middleware/prometheus.py`. Off by default so the hot path stays allocation-free.

## Public API

Re-exported from `hawkapi.middleware`:

```python
from hawkapi.middleware import Bulkhead, BulkheadFullError, bulkhead
```

The Redis backend is imported explicitly to keep the import graph of the base package free of the `redis` dependency:

```python
from hawkapi.middleware.bulkhead_redis import RedisBulkheadBackend
```

### Module layout

```
src/hawkapi/middleware/
  bulkhead.py              # Core primitive + LocalBulkheadBackend + decorator
  bulkhead_redis.py        # RedisBulkheadBackend (lazy redis import)
tests/unit/
  test_bulkhead.py         # Core + local backend + decorator + metrics
  test_bulkhead_redis.py   # fakeredis-based; real-redis marker for integration
tests/perf/
  test_bulkhead_perf.py    # benchmark local acquire/release overhead
docs/guide/
  bulkhead.md              # when to use vs AdaptiveConcurrency vs RateLimit
```

`mkdocs.yml` gets a new nav entry under Guide, after `Performance` and before `Free-threaded Python (PEP 703)`.

## Out of scope (explicit)

- **Thread-pool bulkhead** for sync code offloaded via `asyncio.to_thread` — rare use case. Can be added later as a separate `ThreadPoolBulkhead` without affecting the async one.
- **Circuit-breaker composition** — users compose manually (`CircuitBreaker` is a separate, existing middleware). We do not auto-wrap Bulkhead with a breaker.
- **Load shedding** (dropping old waiting requests under pressure) — a different pattern with different tradeoffs.
- **Auto-tuning `limit`** — that is what `AdaptiveConcurrencyMiddleware` does, by design.
- **Per-user / per-tenant partitions** — can be done by composing (`Bulkhead(f"tenant:{t}", ...)`) or subclassing later.
- **Redlock-style strict correctness** in the Redis backend — lease-TTL is deliberate.
- **Priority queuing / fairness guarantees** when multiple waiters race for the same slot — FIFO / fairness is not guaranteed.

## Success criteria

1. `async with Bulkhead("x", 10): ...` works; context-manager entry/exit in sub-millisecond on the local backend.
2. `@bulkhead("x", 10)` decorator returns 503 with `Retry-After` on full; configurable to 429.
3. Concurrency test: spawning N coroutines against a local `Bulkhead(limit=K)` never has more than K in flight at once.
4. `max_wait > 0` queues waiters and releases them in acquire order when slots free; `max_wait = 0` fails immediately.
5. Perf benchmark: local backend `acquire/release` overhead `< 5 µs` per pair on CI runner. Baseline committed in `tests/perf/.benchmark_baseline.json`; perf regression gate applies.
6. Redis backend: cross-process capacity control verified via fakeredis-based test; lease TTL reaps stale slots after simulated crash.
7. Release is guaranteed on `CancelledError` — explicit test.
8. Prometheus metrics emit only when `metrics=True`; no `prometheus_client` import on the default path.
9. `mkdocs build --strict` clean after new guide + nav entry.

## Testing approach

### Unit tests (`tests/unit/test_bulkhead.py`)

- Context manager happy path.
- Decorator happy path.
- Fail-fast: second acquire when full raises `BulkheadFullError` with `waited ≈ 0`.
- Queue-with-timeout: second acquire waits, is released when first completes; third times out.
- Release-on-exception: handler raises user error → bulkhead slot is freed.
- Release-on-cancel: task cancelled mid-hold → slot is freed.
- Decorator HTTP: 503 + `Retry-After`; configurable to 429.
- Metrics: when `metrics=True`, counters/gauges update; when `False`, the `prometheus_client` module is not imported.
- Registry lookup: same name, different construction → shared backend slot (second `Bulkhead("x", 10)` reuses the same semaphore).
- Name collision with different limits → documented error (raise `ValueError`, do not silently use the first).

### Redis tests (`tests/unit/test_bulkhead_redis.py`)

- fakeredis-backed: basic acquire/release, counter arithmetic, lease-key creation.
- Lease TTL expiry: simulate a crashed worker by skipping release + advancing fakeredis time; reaper reconciles.
- Concurrency: two fakeredis clients race, only `limit` succeed.
- Opt-in real-redis: `@pytest.mark.redis` for integration runs; CI does not require a live redis.

### Perf tests (`tests/perf/test_bulkhead_perf.py`)

- Benchmark local `acquire/release` pair with `pytest-benchmark`.
- Baseline in `tests/perf/.benchmark_baseline.json`.
- Regression gate (5 %) inherited from existing `perf-regression` CI job.

### Coverage target

- `src/hawkapi/middleware/bulkhead.py` ≥ 95 % line coverage (the local path is small and fully exercisable).
- `src/hawkapi/middleware/bulkhead_redis.py` ≥ 85 % (TTL / reaper edge paths covered via fakeredis).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Deadlock with nested bulkheads | Document "do not nest same-name bulkheads"; no runtime detection. |
| Race registering a new name in `LocalBulkheadBackend` | `asyncio.Lock` on first-time registration; fast path after is lock-free dict lookup. |
| Redis connection drop mid-lease | Lease-TTL expires naturally; reaper periodically reconciles. |
| Over-capacity window in Redis after worker crash | Bounded by TTL (default 30 s); documented as known tradeoff. |
| Semaphore not released on `asyncio.CancelledError` | `try/finally` in core; explicit unit test for cancel-mid-hold. |
| Ambiguity: same `name`, different `limit` in two callsites | Raise `ValueError` at second construction; documented. Prevents silent surprise. |
| Metrics cardinality explosion from user-supplied names | Document: `name` should be bounded (per-downstream, per-endpoint). We do not sanitize. |

## Rollback

New modules + new user-facing import. No existing code paths change. Reverting:

1. Delete `src/hawkapi/middleware/bulkhead.py` and `bulkhead_redis.py`.
2. Remove re-exports from `src/hawkapi/middleware/__init__.py`.
3. Revert `mkdocs.yml` nav and delete `docs/guide/bulkhead.md`.
4. Delete tests under `tests/unit/test_bulkhead*.py` and `tests/perf/test_bulkhead_perf.py`.

One PR, fully reversible.

## Files touched

- New: `src/hawkapi/middleware/bulkhead.py`
- New: `src/hawkapi/middleware/bulkhead_redis.py`
- Modify: `src/hawkapi/middleware/__init__.py` — re-export `Bulkhead`, `bulkhead`, `BulkheadFullError`.
- New: `tests/unit/test_bulkhead.py`
- New: `tests/unit/test_bulkhead_redis.py`
- New: `tests/perf/test_bulkhead_perf.py`
- New: `docs/guide/bulkhead.md`
- Modify: `mkdocs.yml` — nav entry.
- Modify: `tests/perf/.benchmark_baseline.json` — add bulkhead benchmark baseline.
- Modify: `CHANGELOG.md` — `[Unreleased]` `### Added` entry.
