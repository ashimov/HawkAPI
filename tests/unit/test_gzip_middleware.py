"""Tests for GZip middleware with streaming support."""

import gzip

from hawkapi.middleware.gzip import GZipMiddleware


def _make_scope(accept_gzip=True):
    headers = []
    if accept_gzip:
        headers.append((b"accept-encoding", b"gzip, deflate"))
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "server": ("localhost", 8000),
    }


async def _collect(app, scope=None):
    msgs = []
    scope = scope or _make_scope()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        msgs.append(msg)

    await app(scope, receive, send)
    return msgs


async def test_compresses_large_response():
    body = b"x" * 1000

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    app = GZipMiddleware(inner, minimum_size=500)
    msgs = await _collect(app)

    assert msgs[0]["status"] == 200
    headers = dict(msgs[0]["headers"])
    assert headers[b"content-encoding"] == b"gzip"
    assert b"vary" in headers

    compressed = msgs[1]["body"]
    assert gzip.decompress(compressed) == body


async def test_skips_small_response():
    body = b"small"

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    app = GZipMiddleware(inner, minimum_size=500)
    msgs = await _collect(app)

    headers = dict(msgs[0]["headers"])
    assert b"content-encoding" not in headers
    assert msgs[1]["body"] == body


async def test_skips_when_no_accept_encoding():
    body = b"x" * 1000

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    app = GZipMiddleware(inner, minimum_size=500)
    msgs = await _collect(app, _make_scope(accept_gzip=False))

    assert msgs[1]["body"] == body


async def test_multi_chunk_response():
    chunk1 = b"a" * 300
    chunk2 = b"b" * 300

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": chunk1, "more_body": True})
        await send({"type": "http.response.body", "body": chunk2, "more_body": False})

    app = GZipMiddleware(inner, minimum_size=500)
    msgs = await _collect(app)

    headers = dict(msgs[0]["headers"])
    assert headers[b"content-encoding"] == b"gzip"

    # Collect all body chunks
    compressed = b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body")
    assert gzip.decompress(compressed) == chunk1 + chunk2


async def test_multi_chunk_small_total():
    chunk1 = b"a" * 100
    chunk2 = b"b" * 100

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": chunk1, "more_body": True})
        await send({"type": "http.response.body", "body": chunk2, "more_body": False})

    app = GZipMiddleware(inner, minimum_size=500)
    msgs = await _collect(app)

    # Should not be compressed
    body = b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body")
    assert body == chunk1 + chunk2


async def test_non_http_passthrough():
    async def inner(scope, receive, send):
        await send({"type": "websocket.accept"})

    app = GZipMiddleware(inner)
    scope = {"type": "websocket", "path": "/ws"}
    msgs = await _collect(app, scope)
    assert msgs[0]["type"] == "websocket.accept"


async def test_streaming_large_chunks():
    """Test streaming compression with large chunks exceeding minimum_size."""
    chunks = [b"x" * 600, b"y" * 400, b"z" * 300]

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for i, chunk in enumerate(chunks):
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": i < len(chunks) - 1,
                }
            )

    app = GZipMiddleware(inner, minimum_size=500)
    msgs = await _collect(app)

    headers = dict(msgs[0]["headers"])
    assert headers[b"content-encoding"] == b"gzip"

    compressed = b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body")
    assert gzip.decompress(compressed) == b"".join(chunks)
