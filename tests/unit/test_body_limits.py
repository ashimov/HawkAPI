"""Tests for request body size limits."""

import pytest

from hawkapi.requests.request import (
    DEFAULT_MAX_BODY_SIZE,
    RequestEntityTooLarge,
    read_body,
)


async def test_read_body_within_limit():
    body = b"hello world"

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    result = await read_body(receive, max_size=1024)
    assert result == body


async def test_read_body_exceeds_limit():
    body = b"x" * 1000

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    with pytest.raises(RequestEntityTooLarge) as exc_info:
        await read_body(receive, max_size=500)
    assert exc_info.value.max_size == 500


async def test_read_body_chunked_within_limit():
    chunks = [b"chunk1", b"chunk2", b"chunk3"]
    idx = 0

    async def receive():
        nonlocal idx
        chunk = chunks[idx]
        idx += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": idx < len(chunks),
        }

    result = await read_body(receive, max_size=1024)
    assert result == b"chunk1chunk2chunk3"


async def test_read_body_chunked_exceeds_limit():
    chunks = [b"x" * 300, b"x" * 300]
    idx = 0

    async def receive():
        nonlocal idx
        chunk = chunks[idx]
        idx += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": idx < len(chunks),
        }

    with pytest.raises(RequestEntityTooLarge):
        await read_body(receive, max_size=500)


async def test_default_max_body_size():
    assert DEFAULT_MAX_BODY_SIZE == 10 * 1024 * 1024  # 10 MB


async def test_empty_body():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    result = await read_body(receive, max_size=100)
    assert result == b""
