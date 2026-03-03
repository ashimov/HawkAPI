"""Tests for rate limiting middleware."""

import json

from hawkapi.middleware.rate_limit import RateLimitMiddleware


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


async def test_within_rate_limit():
    inner = await _make_app()
    mw = RateLimitMiddleware(inner, requests_per_second=100.0, burst=10)
    msgs = await _collect(mw, _make_scope())
    assert msgs[0]["status"] == 200


async def test_exceeds_rate_limit():
    inner = await _make_app()
    mw = RateLimitMiddleware(inner, requests_per_second=1.0, burst=2)

    # First 2 requests should succeed (burst=2)
    for _ in range(2):
        msgs = await _collect(mw, _make_scope())
        assert msgs[0]["status"] == 200

    # Third request should be rate limited
    msgs = await _collect(mw, _make_scope())
    assert msgs[0]["status"] == 429


async def test_retry_after_header():
    inner = await _make_app()
    mw = RateLimitMiddleware(inner, requests_per_second=1.0, burst=1)

    await _collect(mw, _make_scope())  # use the burst token
    msgs = await _collect(mw, _make_scope())
    assert msgs[0]["status"] == 429
    headers = dict(msgs[0]["headers"])
    assert b"retry-after" in headers


async def test_429_response_body():
    inner = await _make_app()
    mw = RateLimitMiddleware(inner, requests_per_second=1.0, burst=1)

    await _collect(mw, _make_scope())
    msgs = await _collect(mw, _make_scope())
    body = json.loads(msgs[1]["body"])
    assert body["detail"] == "Too Many Requests"


async def test_different_clients_independent():
    inner = await _make_app()
    mw = RateLimitMiddleware(inner, requests_per_second=1.0, burst=1)

    # Client A uses their token
    msgs = await _collect(mw, _make_scope("10.0.0.1"))
    assert msgs[0]["status"] == 200

    # Client B should still have their token
    msgs = await _collect(mw, _make_scope("10.0.0.2"))
    assert msgs[0]["status"] == 200


async def test_custom_key_func():
    inner = await _make_app()

    def key_func(scope):
        return "global"

    mw = RateLimitMiddleware(inner, requests_per_second=1.0, burst=1, key_func=key_func)
    await _collect(mw, _make_scope("10.0.0.1"))
    # Different IP but same key — should be rate limited
    msgs = await _collect(mw, _make_scope("10.0.0.2"))
    assert msgs[0]["status"] == 429


async def test_non_http_passthrough():
    inner = await _make_app()
    mw = RateLimitMiddleware(inner, requests_per_second=1.0, burst=1)
    scope = {"type": "websocket", "path": "/ws"}
    msgs = await _collect(mw, scope)
    assert msgs[0]["status"] == 200


async def test_cleanup_stale_entries():
    inner = await _make_app()
    mw = RateLimitMiddleware(inner, requests_per_second=100.0, burst=10, cleanup_interval=0)
    await _collect(mw, _make_scope("10.0.0.1"))
    assert "10.0.0.1" in mw._buckets
    # Force cleanup by setting last_cleanup far in the past
    import time

    mw._last_cleanup = time.monotonic() - 100
    mw._buckets["10.0.0.1"][1] = time.monotonic() - 100
    await _collect(mw, _make_scope("10.0.0.2"))
    assert "10.0.0.1" not in mw._buckets
