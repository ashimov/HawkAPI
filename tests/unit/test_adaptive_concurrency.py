"""Tests for AdaptiveConcurrencyMiddleware."""

from __future__ import annotations

import asyncio
import json

import pytest

from hawkapi.middleware.adaptive_concurrency import AdaptiveConcurrencyMiddleware


def _make_scope(path: str = "/test") -> dict[str, object]:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "root_path": "",
    }


async def _receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_app(latency: float = 0.0, status: int = 200):
    """Create an ASGI app that sleeps for ``latency`` seconds then responds."""

    async def app(scope, receive, send):
        if latency > 0.0:
            await asyncio.sleep(latency)
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


async def _call(middleware, path: str = "/test") -> tuple[int | None, dict[bytes, bytes], bytes]:
    """Invoke the middleware and return (status, headers_dict, body)."""
    scope = _make_scope(path)
    sent: list[dict[str, object]] = []

    async def send(msg):
        sent.append(msg)

    await middleware(scope, _receive, send)

    if not sent:
        return None, {}, b""
    start = sent[0]
    body = b"".join(m.get("body", b"") for m in sent[1:] if m["type"] == "http.response.body")
    headers_dict: dict[bytes, bytes] = dict(start.get("headers", []))  # type: ignore[arg-type]
    return start["status"], headers_dict, body  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Basic admission control
# ---------------------------------------------------------------------------


async def test_basic_allow_under_limit():
    """A single request comfortably under the limit is admitted."""
    inner = _make_app()
    mw = AdaptiveConcurrencyMiddleware(inner, initial_limit=10, min_limit=1)
    status, _, body = await _call(mw)
    assert status == 200
    assert body == b"ok"


async def test_rejects_over_limit():
    """Concurrent requests beyond the limit are rejected with 503."""
    # Slow inner app — keeps the first request in-flight while we fire the second
    inner = _make_app(latency=0.1)
    mw = AdaptiveConcurrencyMiddleware(
        inner, initial_limit=1, min_limit=1, max_limit=1
    )

    results: list[int | None] = []

    async def fire(idx: int):
        # Stagger slightly so request 0 gets the slot first
        await asyncio.sleep(0.001 * idx)
        status, _, _ = await _call(mw)
        results.append(status)

    await asyncio.gather(fire(0), fire(1))
    assert 200 in results
    assert 503 in results


# ---------------------------------------------------------------------------
# 503 response shape
# ---------------------------------------------------------------------------


async def test_503_has_retry_after_header():
    """503 responses include a Retry-After header and problem+json body."""
    inner = _make_app(latency=0.05)
    mw = AdaptiveConcurrencyMiddleware(
        inner, initial_limit=1, min_limit=1, max_limit=1
    )

    statuses: list[int | None] = []
    headers_seen: list[dict[bytes, bytes]] = []
    bodies: list[bytes] = []

    async def fire(idx: int):
        await asyncio.sleep(0.001 * idx)
        s, h, b = await _call(mw)
        statuses.append(s)
        headers_seen.append(h)
        bodies.append(b)

    await asyncio.gather(fire(0), fire(1))

    # Find the rejected request
    rejected_idx = next(i for i, s in enumerate(statuses) if s == 503)
    headers = headers_seen[rejected_idx]
    body = bodies[rejected_idx]

    assert b"retry-after" in headers
    retry_after_value = headers[b"retry-after"]
    assert int(retry_after_value) >= 1
    assert headers[b"content-type"] == b"application/problem+json"

    parsed = json.loads(body)
    assert parsed["status"] == 503
    assert parsed["title"] == "Service Unavailable"
    assert "detail" in parsed


# ---------------------------------------------------------------------------
# Adaptive behavior — limit decreases / increases
# ---------------------------------------------------------------------------


async def test_limit_decreases_when_latency_rises():
    """When recent RTTs are far above the floor, the limit should contract."""
    inner = _make_app()
    mw = AdaptiveConcurrencyMiddleware(
        inner,
        initial_limit=200,
        min_limit=10,
        max_limit=1000,
        smoothing=0.5,  # less inertia so the test converges quickly
        queue_size_buffer=1.0,
        min_rtt_reset_interval=999.0,
    )
    # Seed state
    await _call(mw)
    state = mw._states["/test"]
    initial_limit = state.limit

    # Establish a tiny floor
    state.min_rtt = 0.001
    state.samples.clear()

    # Feed many high-RTT samples — gradient becomes 0.5, limit must shrink
    for _ in range(50):
        mw._record_sample(state, rtt=1.0)

    assert state.limit < initial_limit, (
        f"limit should shrink under load: was {initial_limit}, now {state.limit}"
    )


async def test_limit_increases_when_latency_drops():
    """When RTTs hug the floor, the gradient saturates at 1.0 and limit grows."""
    inner = _make_app()
    mw = AdaptiveConcurrencyMiddleware(
        inner,
        initial_limit=20,
        min_limit=10,
        max_limit=1000,
        smoothing=0.5,
        queue_size_buffer=5.0,
        min_rtt_reset_interval=999.0,
    )
    await _call(mw)
    state = mw._states["/test"]

    # Establish a floor and feed RTTs equal to the floor (gradient -> 1.0)
    state.min_rtt = 0.01
    state.samples.clear()
    state.limit = 20.0
    starting = state.limit

    for _ in range(100):
        mw._record_sample(state, rtt=0.01)

    assert state.limit > starting, (
        f"limit should grow when RTTs match the floor: was {starting}, now {state.limit}"
    )


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


async def test_min_limit_clamping():
    """The dynamic limit never falls below min_limit even under sustained load."""
    inner = _make_app()
    mw = AdaptiveConcurrencyMiddleware(
        inner,
        initial_limit=50,
        min_limit=15,
        max_limit=1000,
        smoothing=0.0,  # no inertia — converge in a single step
        queue_size_buffer=0.0,
        min_rtt_reset_interval=999.0,
    )
    await _call(mw)
    state = mw._states["/test"]
    state.min_rtt = 0.001
    state.samples.clear()

    # Hammer with high-RTT samples; limit should be clamped at min_limit
    for _ in range(200):
        mw._record_sample(state, rtt=10.0)

    assert state.limit == 15.0


async def test_max_limit_clamping():
    """The dynamic limit never exceeds max_limit even when latency stays low."""
    inner = _make_app()
    mw = AdaptiveConcurrencyMiddleware(
        inner,
        initial_limit=50,
        min_limit=10,
        max_limit=60,
        smoothing=0.0,
        queue_size_buffer=100.0,  # large buffer to push past max
        min_rtt_reset_interval=999.0,
    )
    await _call(mw)
    state = mw._states["/test"]
    state.min_rtt = 0.01
    state.samples.clear()

    for _ in range(50):
        mw._record_sample(state, rtt=0.01)

    assert state.limit == 60.0


# ---------------------------------------------------------------------------
# ASGI scope handling
# ---------------------------------------------------------------------------


async def test_non_http_scope_passthrough():
    """Non-HTTP scopes (e.g. websocket, lifespan) bypass the limiter entirely."""
    inner = _make_app()
    mw = AdaptiveConcurrencyMiddleware(inner, initial_limit=1, min_limit=1, max_limit=1)

    sent: list[dict[str, object]] = []

    async def send(msg):
        sent.append(msg)

    await mw({"type": "websocket", "path": "/ws"}, _receive, send)

    # The inner app sent its normal start message — point being that the
    # middleware did not interpose any 503 / per-path state mutation.
    assert sent[0]["status"] == 200
    assert "/ws" not in mw._states


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"initial_limit": 0}, "initial_limit"),
        ({"min_limit": 0}, "min_limit"),
        ({"min_limit": 100, "max_limit": 50}, "max_limit"),
        ({"smoothing": 1.0}, "smoothing"),
        ({"smoothing": -0.1}, "smoothing"),
        ({"target_p99_ms": 0.0}, "target_p99_ms"),
    ],
)
async def test_constructor_validates_args(kwargs, match):
    inner = _make_app()
    with pytest.raises(ValueError, match=match):
        AdaptiveConcurrencyMiddleware(inner, **kwargs)


# ---------------------------------------------------------------------------
# In-flight bookkeeping
# ---------------------------------------------------------------------------


async def test_in_flight_decremented_after_completion():
    """After a successful request, in_flight returns to 0."""
    inner = _make_app()
    mw = AdaptiveConcurrencyMiddleware(inner, initial_limit=10, min_limit=1)
    await _call(mw)
    state = mw._states["/test"]
    assert state.in_flight == 0


async def test_in_flight_decremented_on_exception():
    """If the inner app raises, in_flight must still be released."""

    async def failing(scope, receive, send):
        raise RuntimeError("boom")

    mw = AdaptiveConcurrencyMiddleware(failing, initial_limit=10, min_limit=1)
    with pytest.raises(RuntimeError):
        await _call(mw)
    state = mw._states["/test"]
    assert state.in_flight == 0
