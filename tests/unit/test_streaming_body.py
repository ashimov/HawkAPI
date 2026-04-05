"""Tests for streaming request body."""

import pytest

from hawkapi.requests.request import Request, RequestEntityTooLarge


def _make_scope(**overrides):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "query_string": b"",
        "headers": [],
    }
    scope.update(overrides)
    return scope


def _make_chunked_receive(chunks):
    """Create a receive callable that yields chunks one at a time."""
    idx = 0

    async def receive():
        nonlocal idx
        if idx < len(chunks):
            chunk = chunks[idx]
            idx += 1
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": idx < len(chunks),
            }
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


async def test_stream_multi_chunk_body():
    """Test streaming a body that arrives in multiple chunks."""
    chunks = [b"chunk1", b"chunk2", b"chunk3"]
    receive = _make_chunked_receive(chunks)
    req = Request(_make_scope(), receive)

    collected = []
    async for chunk in req.stream():
        collected.append(chunk)

    assert collected == [b"chunk1", b"chunk2", b"chunk3"]
    assert b"".join(collected) == b"chunk1chunk2chunk3"


async def test_stream_respects_max_body_size():
    """Test that streaming raises RequestEntityTooLarge when limit is exceeded."""
    chunks = [b"x" * 300, b"x" * 300]
    receive = _make_chunked_receive(chunks)
    req = Request(_make_scope(), receive, max_body_size=500)

    with pytest.raises(RequestEntityTooLarge) as exc_info:
        async for _ in req.stream():
            pass

    assert exc_info.value.max_size == 500


async def test_stream_then_body_raises():
    """Test that body() raises RuntimeError after stream() has consumed the body."""
    chunks = [b"hello"]
    receive = _make_chunked_receive(chunks)
    req = Request(_make_scope(), receive)

    # Consume via stream
    async for _ in req.stream():
        pass

    # Now body() should raise
    with pytest.raises(RuntimeError, match="Body already consumed by stream"):
        await req.body()


async def test_body_then_stream_yields_cached():
    """Test that stream() yields the cached body if body() was called first."""
    body_data = b"cached body content"

    async def receive():
        return {"type": "http.request", "body": body_data, "more_body": False}

    req = Request(_make_scope(), receive)

    # Read body first
    result = await req.body()
    assert result == body_data

    # Now stream should yield the cached body as a single chunk
    collected = []
    async for chunk in req.stream():
        collected.append(chunk)

    assert collected == [body_data]


async def test_stream_empty_body():
    """Test streaming an empty body."""

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    req = Request(_make_scope(), receive)

    collected = []
    async for chunk in req.stream():
        collected.append(chunk)

    assert collected == []


async def test_stream_single_chunk():
    """Test streaming a body that arrives as a single chunk."""
    chunks = [b"single chunk data"]
    receive = _make_chunked_receive(chunks)
    req = Request(_make_scope(), receive)

    collected = []
    async for chunk in req.stream():
        collected.append(chunk)

    assert collected == [b"single chunk data"]


async def test_stream_max_body_size_exact_boundary():
    """Test streaming body that is exactly at the max_body_size limit."""
    chunks = [b"x" * 250, b"x" * 250]
    receive = _make_chunked_receive(chunks)
    req = Request(_make_scope(), receive, max_body_size=500)

    collected = []
    async for chunk in req.stream():
        collected.append(chunk)

    assert len(b"".join(collected)) == 500
