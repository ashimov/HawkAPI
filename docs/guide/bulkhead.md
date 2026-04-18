# Bulkhead

A **bulkhead** is a named, size-limited concurrency isolator. It partitions
capacity across resource pools so one saturated downstream cannot starve
others.

## When to use which pattern

HawkAPI ships three related concurrency-control tools:

| Pattern | What it caps | When to reach for it |
|---|---|---|
| `RateLimitMiddleware` | Requests per time window | Per-client quotas; DDoS protection |
| `AdaptiveConcurrencyMiddleware` | Total in-flight requests (auto-tuned) | Whole-service overload protection |
| `Bulkhead` | Named pool of concurrent slots | Protect a specific downstream or endpoint |

If you need all three, compose them — they do different things.

## Context-manager form

Protect a specific downstream:

```python
from hawkapi.middleware import Bulkhead, BulkheadFullError

stripe_bulkhead = Bulkhead("stripe", limit=10, max_wait=0.5)

async def charge(card: str, amount: int) -> str:
    try:
        async with stripe_bulkhead:
            return await stripe_client.charge(card, amount)
    except BulkheadFullError:
        return await queue_for_async_charge(card, amount)
```

- `limit=10` — at most 10 concurrent calls to Stripe.
- `max_wait=0.5` — wait up to 500 ms for a slot; raise on timeout.
- `max_wait=0.0` (default) — fail fast.

## Decorator form

Cap an endpoint's concurrency:

```python
from hawkapi.middleware.bulkhead import bulkhead

@bulkhead("payments", limit=10, status_code=503, retry_after=1.0)
async def pay(request: Request) -> Response:
    ...
```

On rejection the handler raises `HTTPException(503)` with a `Retry-After`
header. Override `status_code=429` if your clients already implement
rate-limit backoff.

## Distributed bulkheads

For multi-process capacity control, swap in the Redis backend:

```python
import redis.asyncio as aioredis
from hawkapi.middleware import Bulkhead
from hawkapi.middleware.bulkhead_redis import RedisBulkheadBackend

redis_client = aioredis.from_url("redis://localhost")
redis_backend = RedisBulkheadBackend(redis_client, lease_ttl=30.0)

stripe_bulkhead = Bulkhead(
    "stripe", limit=10, max_wait=0.5, backend=redis_backend
)
```

**Tradeoffs**:

- Each `acquire` and `release` is a Redis round-trip (~0.3–1 ms typical).
- If a worker crashes mid-hold, its lease expires after `lease_ttl` (default
  30 s); until then the slot counts as held — a bounded over-capacity window.
- Call `RedisBulkheadBackend.reap_expired_leases(name)` periodically (for
  example from a lifespan background task) to actively reclaim stale slots.

## Metrics

Enable Prometheus metrics per bulkhead:

```python
stripe_bulkhead = Bulkhead("stripe", limit=10, metrics=True)
```

Exposed series:

- `hawkapi_bulkhead_in_flight{name}` — gauge of currently-held slots.
- `hawkapi_bulkhead_capacity{name}` — gauge = configured `limit`.
- `hawkapi_bulkhead_rejections_total{name, reason}` — counter;
  `reason ∈ {"fail_fast", "timeout"}`.
- `hawkapi_bulkhead_acquire_latency_seconds{name}` — histogram.

Metrics are off by default — the hot path does not import `prometheus_client`
unless at least one `Bulkhead(metrics=True)` is constructed.

## Limitations

- Same name with different `limit` raises `ValueError` — pick one.
- Fairness is not guaranteed — waiters are not served strictly FIFO.
- Nested same-name acquires in the same task work, but can deadlock if
  `limit` is too small; avoid them.
- The Redis backend does not provide Redlock-strength guarantees — if that
  matters, wrap a strict-mode lock around the call yourself.
