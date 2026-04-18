"""Tests for Redis-backed circuit breaker middleware.

Mocks the Redis client so the suite runs without a live Redis instance.
The Lua scripts themselves are exercised by the in-memory fallback paths.
"""

import contextlib
import json
from unittest.mock import AsyncMock

import pytest

redis = pytest.importorskip("redis")

from hawkapi.middleware.circuit_breaker_redis import (  # noqa: E402
    RedisCircuitBreakerMiddleware,
)


async def _make_app(status=200, raise_exc=False):
    """Create a simple ASGI app that returns *status* or raises."""

    async def app(scope, receive, send):
        if raise_exc:
            raise RuntimeError("boom")
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


def _make_scope(path="/test"):
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "root_path": "",
    }


async def _call(middleware, path="/test"):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    with contextlib.suppress(RuntimeError):
        await middleware(_make_scope(path), receive, send)
    return sent


def _inject_mock_redis(
    mw,
    *,
    check_results=None,
    record_results=None,
    check_sequence=None,
    record_sequence=None,
):
    """Inject a mock Redis client onto the middleware instance.

    Single-shot mode:
      *check_results* — a single ``[allowed, state]`` list returned for every check.
      *record_results* — a single state string returned for every record.

    Sequence mode (one entry per call):
      *check_sequence* — list of ``[allowed, state]`` lists, drained in order.
      *record_sequence* — list of state strings, drained in order.
    """
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.script_load = AsyncMock(return_value="fake_sha")

    check_iter = iter(check_sequence) if check_sequence is not None else None
    record_iter = iter(record_sequence) if record_sequence is not None else None

    async def evalsha(sha, *_args, **_kwargs):
        if sha == "check_sha":
            if check_iter is not None:
                return next(check_iter)
            return check_results if check_results is not None else [1, "CLOSED"]
        if sha == "record_sha":
            if record_iter is not None:
                return next(record_iter)
            return record_results if record_results is not None else "CLOSED"
        return [1, "CLOSED"]

    mock_client.evalsha = AsyncMock(side_effect=evalsha)
    mw._redis_client = mock_client
    mw._check_sha = "check_sha"
    mw._record_sha = "record_sha"
    mw._redis_available = True
    return mock_client


# ---------------------------------------------------------------------------
# Construction & non-HTTP passthrough
# ---------------------------------------------------------------------------


async def test_constructor_defaults():
    """Middleware accepts the documented defaults without error."""
    inner = await _make_app()
    mw = RedisCircuitBreakerMiddleware(inner)
    assert mw.failure_threshold == 5
    assert mw.recovery_timeout == 30.0
    assert mw.half_open_max_calls == 1
    assert mw.key_prefix == "hawkapi:cb:"


async def test_non_http_passthrough():
    """Non-HTTP scopes bypass the circuit breaker entirely."""
    inner = await _make_app(status=200)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=1, recovery_timeout=30.0)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw({"type": "websocket", "path": "/ws"}, receive, send)
    assert sent[0]["status"] == 200


# ---------------------------------------------------------------------------
# Redis happy path: allow / reject
# ---------------------------------------------------------------------------


async def test_redis_allows_request():
    """When the check script returns allowed=1, the inner app runs."""
    inner = await _make_app(status=200)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=3)
    _inject_mock_redis(mw, check_results=[1, "CLOSED"], record_results="CLOSED")

    sent = await _call(mw)
    assert sent[0]["status"] == 200


async def test_redis_rejects_when_open():
    """When the check script returns allowed=0, a 503 is emitted."""
    inner = await _make_app(status=200)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=3)
    _inject_mock_redis(mw, check_results=[0, "OPEN"])

    sent = await _call(mw)
    assert sent[0]["status"] == 503

    headers = dict(sent[0]["headers"])
    assert headers[b"content-type"] == b"application/problem+json"
    assert b"content-length" in headers
    assert headers[b"content-length"] == str(len(sent[1]["body"])).encode("latin-1")

    body = json.loads(sent[1]["body"])
    assert body["title"] == "Service Unavailable"
    assert body["status"] == 503
    assert "circuit-open" in body["type"]
    assert "/test" in body["detail"]


async def test_record_called_on_success():
    """A successful response triggers the record script with success=1."""
    inner = await _make_app(status=200)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=3)
    mock_client = _inject_mock_redis(mw, check_results=[1, "CLOSED"], record_results="CLOSED")

    await _call(mw)

    # Two evalsha calls expected: check then record.
    assert mock_client.evalsha.call_count == 2
    record_call = mock_client.evalsha.call_args_list[1]
    assert record_call[0][0] == "record_sha"
    # ARGV[2] is success flag; for 200 OK it must be "1".
    assert record_call[0][4] == "1"


async def test_record_called_on_5xx():
    """A 5xx response triggers the record script with success=0."""
    inner = await _make_app(status=500)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=3)
    mock_client = _inject_mock_redis(mw, check_results=[1, "CLOSED"], record_results="CLOSED")

    await _call(mw)

    record_call = mock_client.evalsha.call_args_list[1]
    assert record_call[0][0] == "record_sha"
    assert record_call[0][4] == "0"


async def test_record_called_on_exception():
    """An exception from the inner app records a failure and re-raises."""
    inner = await _make_app(raise_exc=True)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=3)
    mock_client = _inject_mock_redis(mw, check_results=[1, "CLOSED"], record_results="CLOSED")

    await _call(mw)  # _call swallows RuntimeError via contextlib.suppress

    # Both check and record should still have run.
    assert mock_client.evalsha.call_count == 2
    record_call = mock_client.evalsha.call_args_list[1]
    assert record_call[0][4] == "0"


async def test_per_path_keying():
    """Different paths produce different Redis keys."""
    inner = await _make_app(status=200)
    mw = RedisCircuitBreakerMiddleware(inner, key_prefix="cb:test:")
    mock_client = _inject_mock_redis(mw, check_results=[1, "CLOSED"], record_results="CLOSED")

    await _call(mw, path="/a")
    await _call(mw, path="/b")

    keys_used = [c[0][2] for c in mock_client.evalsha.call_args_list if c[0][0] == "check_sha"]
    assert "cb:test:/a" in keys_used
    assert "cb:test:/b" in keys_used


async def test_check_script_args():
    """The check script receives the configured timing knobs."""
    inner = await _make_app(status=200)
    mw = RedisCircuitBreakerMiddleware(
        inner,
        failure_threshold=4,
        recovery_timeout=15.5,
        half_open_max_calls=2,
        key_prefix="cb:cfg:",
    )
    mock_client = _inject_mock_redis(mw, check_results=[1, "CLOSED"], record_results="CLOSED")

    await _call(mw, path="/x")

    check_call = next(c for c in mock_client.evalsha.call_args_list if c[0][0] == "check_sha")
    # signature: (sha, num_keys, key, now, recovery_timeout, half_open_max)
    assert check_call[0][1] == 1
    assert check_call[0][2] == "cb:cfg:/x"
    assert check_call[0][4] == "15.5"
    assert check_call[0][5] == "2"


# ---------------------------------------------------------------------------
# Recovery cycle (driven by mocked check responses)
# ---------------------------------------------------------------------------


async def test_recovery_cycle_half_open_then_close():
    """OPEN -> HALF_OPEN probe allowed -> success closes the circuit."""
    inner = await _make_app(status=200)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=1.0)
    mock_client = _inject_mock_redis(
        mw,
        check_sequence=[[0, "OPEN"], [1, "HALF_OPEN"]],
        record_sequence=["CLOSED"],
    )

    # First call: circuit is OPEN -> 503
    sent = await _call(mw)
    assert sent[0]["status"] == 503

    # Second call: HALF_OPEN probe allowed; inner returns 200; record closes.
    sent = await _call(mw)
    assert sent[0]["status"] == 200

    # The single record call should have been invoked with success=1.
    record_calls = [c for c in mock_client.evalsha.call_args_list if c[0][0] == "record_sha"]
    assert len(record_calls) == 1
    assert record_calls[0][0][4] == "1"


async def test_recovery_cycle_half_open_failure_reopens():
    """HALF_OPEN probe that fails records a failure (Lua re-opens server-side)."""
    inner = await _make_app(status=500)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=1.0)
    mock_client = _inject_mock_redis(
        mw,
        check_sequence=[[1, "HALF_OPEN"]],
        record_sequence=["OPEN"],
    )

    sent = await _call(mw)
    # Probe propagated: inner returned 500 to client.
    assert sent[0]["status"] == 500

    record_calls = [c for c in mock_client.evalsha.call_args_list if c[0][0] == "record_sha"]
    assert len(record_calls) == 1
    # success=0 because status >= 500
    assert record_calls[0][0][4] == "0"


# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------


async def test_fallback_engaged_when_redis_check_errors():
    """A Redis error during _check flips the middleware into fallback mode."""
    inner = await _make_app(status=200)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=3)
    mock_client = _inject_mock_redis(mw, check_results=[1, "CLOSED"], record_results="CLOSED")
    mock_client.evalsha = AsyncMock(side_effect=ConnectionError("Redis gone"))

    sent = await _call(mw)

    # Request still succeeded via the in-memory fallback.
    assert sent[0]["status"] == 200
    assert mw._redis_available is False


async def test_fallback_circuit_opens_after_threshold():
    """In-memory fallback enforces failure_threshold and opens the circuit."""
    inner = await _make_app(status=500)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=3, recovery_timeout=30.0)
    mw._redis_available = False  # force fallback

    for _ in range(3):
        sent = await _call(mw)
        assert sent[0]["status"] == 500

    sent = await _call(mw)
    assert sent[0]["status"] == 503

    body = json.loads(sent[1]["body"])
    assert body["status"] == 503
    assert body["title"] == "Service Unavailable"


async def test_fallback_per_path_independence():
    """Fallback circuits are tracked per-path, just like the in-memory version."""
    inner = await _make_app(status=500)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=30.0)
    mw._redis_available = False

    for _ in range(2):
        await _call(mw, path="/a")

    sent = await _call(mw, path="/a")
    assert sent[0]["status"] == 503

    # Path /b should still be CLOSED and propagate the 500 from the inner app.
    sent = await _call(mw, path="/b")
    assert sent[0]["status"] == 500


async def test_fallback_recovery_then_close():
    """Fallback HALF_OPEN probe success closes the circuit again."""
    inner = await _make_app(status=500)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=1.0)
    mw._redis_available = False

    for _ in range(2):
        await _call(mw)

    # Force the recovery_timeout to have elapsed by rewinding opened_at.
    state = mw._fallback_circuits["/test"]
    state.opened_at -= 5.0

    # Swap inner to a healthy app.
    mw.app = await _make_app(status=200)

    sent = await _call(mw)
    assert sent[0]["status"] == 200
    assert state.state == "CLOSED"
    assert state.failure_count == 0


async def test_fallback_recovery_probe_failure_reopens():
    """Fallback HALF_OPEN probe failure re-opens the circuit."""
    inner = await _make_app(status=500)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=1.0)
    mw._redis_available = False

    for _ in range(2):
        await _call(mw)

    state = mw._fallback_circuits["/test"]
    state.opened_at -= 5.0

    # Probe still returns 500 -> circuit re-opens.
    sent = await _call(mw)
    assert sent[0]["status"] == 500
    assert state.state == "OPEN"


async def test_fallback_exception_counts_as_failure():
    """Fallback path treats inner exceptions as failures."""
    inner = await _make_app(raise_exc=True)
    mw = RedisCircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=30.0)
    mw._redis_available = False

    for _ in range(2):
        await _call(mw)

    sent = await _call(mw)
    assert sent[0]["status"] == 503
