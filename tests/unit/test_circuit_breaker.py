"""Tests for CircuitBreakerMiddleware."""

import contextlib

from hawkapi.middleware.circuit_breaker import CircuitBreakerMiddleware


async def _make_app(status=200, raise_exc=False):
    """Create a simple ASGI app that returns given status or raises."""

    async def app(scope, receive, send):
        if raise_exc:
            raise RuntimeError("boom")
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


async def _call(middleware, path="/test"):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    with contextlib.suppress(RuntimeError):
        await middleware(scope, receive, send)
    return sent[0]["status"] if sent else None


async def test_passes_through_normally():
    """Successful responses pass through without interference."""
    inner = await _make_app(status=200)
    mw = CircuitBreakerMiddleware(inner, failure_threshold=3, recovery_timeout=30.0)
    status = await _call(mw)
    assert status == 200


async def test_opens_after_threshold_failures():
    """Circuit opens after failure_threshold consecutive 5xx responses."""
    inner = await _make_app(status=500)
    mw = CircuitBreakerMiddleware(inner, failure_threshold=3, recovery_timeout=30.0)

    # 3 failures to hit the threshold
    for _ in range(3):
        status = await _call(mw)
        assert status == 500

    # Next request should be rejected with 503 without calling inner app
    call_count = 0
    original_app = mw.app

    async def counting_app(scope, receive, send):
        nonlocal call_count
        call_count += 1
        await original_app(scope, receive, send)

    mw.app = counting_app
    status = await _call(mw)
    assert status == 503
    assert call_count == 0, "Inner app should NOT be called when circuit is open"


async def test_exception_counts_as_failure():
    """Exceptions are recorded as failures and re-raised."""
    inner = await _make_app(raise_exc=True)
    mw = CircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=30.0)

    # 2 exceptions to hit the threshold
    for _ in range(2):
        status = await _call(mw)
        assert status is None  # No response sent due to exception

    # Circuit should now be open
    status = await _call(mw)
    assert status == 503


async def test_non_http_passthrough():
    """Non-HTTP scopes are passed through without circuit breaker logic."""
    inner = await _make_app(status=200)
    mw = CircuitBreakerMiddleware(inner, failure_threshold=1, recovery_timeout=30.0)
    scope = {"type": "websocket", "path": "/ws"}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw(scope, receive, send)
    assert sent[0]["status"] == 200


async def test_half_open_allows_probe_after_recovery_timeout():
    """After recovery_timeout, circuit transitions to HALF_OPEN and allows a probe."""
    inner = await _make_app(status=500)
    mw = CircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=1.0)

    # Trip the circuit
    for _ in range(2):
        await _call(mw)

    # Should be open
    status = await _call(mw)
    assert status == 503

    # Simulate recovery_timeout expiring by adjusting opened_at
    state = mw._circuits["/test"]
    state.opened_at -= 2.0  # push opened_at back beyond recovery_timeout

    # Now swap inner app to one that returns 200 (service recovered)
    mw.app = await _make_app(status=200)

    # Probe request should succeed and close the circuit
    status = await _call(mw)
    assert status == 200

    # Verify circuit is closed again
    assert state.state == "CLOSED"
    assert state.failure_count == 0


async def test_half_open_probe_failure_reopens():
    """If the probe in HALF_OPEN fails, circuit re-opens."""
    inner = await _make_app(status=500)
    mw = CircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=1.0)

    # Trip the circuit
    for _ in range(2):
        await _call(mw)

    # Simulate recovery_timeout expiring
    state = mw._circuits["/test"]
    state.opened_at -= 2.0

    # Probe still gets 500 -- circuit should re-open
    status = await _call(mw)
    assert status == 500
    assert state.state == "OPEN"


async def test_success_resets_failure_count():
    """A successful response after some failures resets the count."""
    call_num = 0

    async def alternating_app(scope, receive, send):
        nonlocal call_num
        call_num += 1
        status = 500 if call_num <= 2 else 200
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = CircuitBreakerMiddleware(
        alternating_app, failure_threshold=5, recovery_timeout=30.0
    )

    # Two failures
    await _call(mw)
    await _call(mw)
    state = mw._circuits["/test"]
    assert state.failure_count == 2

    # Success resets
    await _call(mw)
    assert state.failure_count == 0
    assert state.state == "CLOSED"


async def test_per_path_tracking():
    """Different paths have independent circuit states."""
    inner = await _make_app(status=500)
    mw = CircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=30.0)

    # Trip circuit for /a
    for _ in range(2):
        await _call(mw, path="/a")

    # /a should be open (503)
    status = await _call(mw, path="/a")
    assert status == 503

    # /b should still be closed (gets 500 from inner app, not 503)
    status = await _call(mw, path="/b")
    assert status == 500


async def test_503_body_is_problem_json():
    """The 503 response body conforms to RFC 9457 problem+json."""
    import json

    inner = await _make_app(status=500)
    mw = CircuitBreakerMiddleware(inner, failure_threshold=1, recovery_timeout=30.0)

    # Trip
    await _call(mw)

    # Capture full response
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "query_string": b"",
        "headers": [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw(scope, receive, send)
    assert sent[0]["status"] == 503

    # Check content-type header
    headers = dict(sent[0]["headers"])
    assert headers[b"content-type"] == b"application/problem+json"

    body = json.loads(sent[1]["body"])
    assert body["title"] == "Service Unavailable"
    assert body["status"] == 503
    assert "detail" in body
