"""Tests for Redis-backed rate limiting middleware."""

import json
from unittest.mock import AsyncMock

import pytest

redis = pytest.importorskip("redis")

from hawkapi.middleware.rate_limit_redis import RedisRateLimitMiddleware  # noqa: E402


async def _make_app():
    """Create a simple ASGI app that returns 200."""

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


def _make_scope(client_ip="127.0.0.1"):
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": (client_ip, 12345),
    }


async def _collect(app, scope):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await app(scope, receive, send)
    return sent


def _inject_mock_redis(mw, *, allowed=True, retry_after=0.0, evalsha_side_effect=None):
    """Inject a mock Redis client directly onto the middleware instance."""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.script_load = AsyncMock(return_value="fake_sha")
    if evalsha_side_effect is not None:
        mock_client.evalsha = AsyncMock(side_effect=evalsha_side_effect)
    else:
        mock_client.evalsha = AsyncMock(return_value=[1 if allowed else 0, str(retry_after)])
    mw._redis_client = mock_client
    mw._lua_sha = "fake_sha"
    mw._redis_available = True
    return mock_client


async def test_basic_allow():
    """Test that requests are allowed when under the limit."""
    inner = await _make_app()
    mw = RedisRateLimitMiddleware(inner, requests_per_second=10.0, burst=10)
    _inject_mock_redis(mw, allowed=True)

    msgs = await _collect(mw, _make_scope())
    assert msgs[0]["status"] == 200


async def test_basic_deny():
    """Test that requests are denied when over the limit."""
    inner = await _make_app()
    mw = RedisRateLimitMiddleware(inner, requests_per_second=1.0, burst=1)
    _inject_mock_redis(mw, allowed=False, retry_after=0.5)

    msgs = await _collect(mw, _make_scope())
    assert msgs[0]["status"] == 429
    body = json.loads(msgs[1]["body"])
    assert body["detail"] == "Too Many Requests"


async def test_429_has_retry_after_header():
    """Test that 429 responses include retry-after header."""
    inner = await _make_app()
    mw = RedisRateLimitMiddleware(inner, requests_per_second=1.0, burst=1)
    _inject_mock_redis(mw, allowed=False, retry_after=2.3)

    msgs = await _collect(mw, _make_scope())
    assert msgs[0]["status"] == 429
    headers = dict(msgs[0]["headers"])
    assert b"retry-after" in headers


async def test_429_has_content_length_header():
    """Test that 429 responses include content-length header."""
    inner = await _make_app()
    mw = RedisRateLimitMiddleware(inner, requests_per_second=1.0, burst=1)
    _inject_mock_redis(mw, allowed=False, retry_after=0.5)

    msgs = await _collect(mw, _make_scope())
    assert msgs[0]["status"] == 429
    headers = dict(msgs[0]["headers"])
    assert b"content-length" in headers
    expected_body = b'{"detail":"Too Many Requests"}'
    assert headers[b"content-length"] == str(len(expected_body)).encode("latin-1")


async def test_token_refill():
    """Test that the Lua script is called with correct parameters for refill."""
    inner = await _make_app()
    mw = RedisRateLimitMiddleware(inner, requests_per_second=5.0, burst=10, key_prefix="test:")
    mock_client = _inject_mock_redis(mw, allowed=True)

    await _collect(mw, _make_scope())

    # Verify evalsha was called with the correct arguments
    mock_client.evalsha.assert_called_once()
    call_args = mock_client.evalsha.call_args
    assert call_args[0][0] == "fake_sha"  # SHA
    assert call_args[0][1] == 1  # number of keys
    assert call_args[0][2] == "test:127.0.0.1"  # redis key
    assert call_args[0][3] == "10"  # burst
    assert call_args[0][4] == "5.0"  # rate


async def test_multiple_clients_independent():
    """Test that different clients have independent rate limits."""
    inner = await _make_app()

    call_count = 0

    async def evalsha_side_effect(*args):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return [1, "0"]
        return [0, "1.0"]

    mw = RedisRateLimitMiddleware(inner, requests_per_second=1.0, burst=1)
    mock_client = _inject_mock_redis(mw, evalsha_side_effect=evalsha_side_effect)

    # Client A
    msgs_a = await _collect(mw, _make_scope("10.0.0.1"))
    assert msgs_a[0]["status"] == 200

    # Client B
    msgs_b = await _collect(mw, _make_scope("10.0.0.2"))
    assert msgs_b[0]["status"] == 200

    # Verify different keys were used
    calls = mock_client.evalsha.call_args_list
    assert calls[0][0][2].endswith("10.0.0.1")
    assert calls[1][0][2].endswith("10.0.0.2")


async def test_fallback_to_in_memory_on_redis_error():
    """Test fallback to in-memory when Redis raises during operation."""
    inner = await _make_app()
    mw = RedisRateLimitMiddleware(inner, requests_per_second=100.0, burst=10)
    mock_client = _inject_mock_redis(mw, allowed=True)
    mock_client.evalsha = AsyncMock(side_effect=ConnectionError("Redis gone"))

    msgs = await _collect(mw, _make_scope())

    # Should still work via fallback
    assert msgs[0]["status"] == 200
    # Redis should now be marked unavailable
    assert mw._redis_available is False


async def test_non_http_passthrough():
    """Test that non-HTTP scopes are passed through."""
    inner = await _make_app()
    mw = RedisRateLimitMiddleware(inner, requests_per_second=1.0, burst=1)
    scope = {"type": "websocket", "path": "/ws"}
    msgs = await _collect(mw, scope)
    assert msgs[0]["status"] == 200


async def test_fallback_rate_limiting_works():
    """Test that fallback in-memory rate limiting actually enforces limits."""
    inner = await _make_app()
    mw = RedisRateLimitMiddleware(inner, requests_per_second=1.0, burst=2)
    # Force fallback mode directly
    mw._redis_available = False

    # First 2 requests should succeed (burst=2)
    for _ in range(2):
        msgs = await _collect(mw, _make_scope())
        assert msgs[0]["status"] == 200

    # Third request should be rate limited
    msgs = await _collect(mw, _make_scope())
    assert msgs[0]["status"] == 429
