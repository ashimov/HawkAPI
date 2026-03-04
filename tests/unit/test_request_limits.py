"""Tests for RequestLimitsMiddleware — query/header size enforcement."""

import json

from hawkapi.middleware.request_limits import RequestLimitsMiddleware


async def _noop_app(scope, receive, send):
    """Inner app that returns 200 OK."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _call_app(app, method, path, headers=None, body=b"", query_string=b""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


async def test_reject_long_query_string():
    """Query strings exceeding max_query_length get 414 URI Too Long."""
    app = RequestLimitsMiddleware(_noop_app, max_query_length=50)
    long_qs = b"x" * 51
    result = await _call_app(app, "GET", "/", query_string=long_qs)

    assert result["status"] == 414
    assert result["headers"][b"content-type"] == b"application/problem+json"

    body = json.loads(result["body"])
    assert body["status"] == 414
    assert body["title"] == "URI Too Long"


async def test_allow_short_query_string():
    """Query strings within max_query_length pass through."""
    app = RequestLimitsMiddleware(_noop_app, max_query_length=50)
    short_qs = b"x" * 50
    result = await _call_app(app, "GET", "/", query_string=short_qs)

    assert result["status"] == 200


async def test_reject_too_many_headers():
    """Requests with too many headers get 431 Request Header Fields Too Large."""
    app = RequestLimitsMiddleware(_noop_app, max_headers_count=5)
    headers = [(f"x-header-{i}".encode(), b"value") for i in range(6)]
    result = await _call_app(app, "GET", "/", headers=headers)

    assert result["status"] == 431
    assert result["headers"][b"content-type"] == b"application/problem+json"

    body = json.loads(result["body"])
    assert body["status"] == 431
    assert body["title"] == "Request Header Fields Too Large"


async def test_allow_within_header_count():
    """Requests within max_headers_count pass through."""
    app = RequestLimitsMiddleware(_noop_app, max_headers_count=5)
    headers = [(f"x-header-{i}".encode(), b"value") for i in range(5)]
    result = await _call_app(app, "GET", "/", headers=headers)

    assert result["status"] == 200


async def test_reject_oversized_header_value():
    """Individual header values exceeding max_header_size get 431."""
    app = RequestLimitsMiddleware(_noop_app, max_header_size=100)
    headers = [(b"x-big", b"v" * 101)]
    result = await _call_app(app, "GET", "/", headers=headers)

    assert result["status"] == 431
    assert result["headers"][b"content-type"] == b"application/problem+json"

    body = json.loads(result["body"])
    assert body["status"] == 431
    assert body["title"] == "Request Header Fields Too Large"


async def test_allow_within_header_size():
    """Header values within max_header_size pass through."""
    app = RequestLimitsMiddleware(_noop_app, max_header_size=100)
    headers = [(b"x-big", b"v" * 100)]
    result = await _call_app(app, "GET", "/", headers=headers)

    assert result["status"] == 200


async def test_non_http_passthrough():
    """Non-HTTP scopes (e.g. websocket) pass through unchanged."""
    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True
        await send({"type": "websocket.accept"})

    app = RequestLimitsMiddleware(inner)
    scope = {"type": "websocket", "path": "/ws"}
    sent = []

    async def receive():
        return {}

    async def send(msg):
        sent.append(msg)

    await app(scope, receive, send)
    assert called
    assert sent[0]["type"] == "websocket.accept"


async def test_default_limits_pass_normal_request():
    """Default limits allow normal requests through."""
    app = RequestLimitsMiddleware(_noop_app)
    result = await _call_app(
        app,
        "GET",
        "/api/items",
        headers=[(b"host", b"localhost"), (b"accept", b"application/json")],
        query_string=b"page=1&limit=20",
    )
    assert result["status"] == 200
