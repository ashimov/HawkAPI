"""Tests for advanced response types."""

import tempfile
from pathlib import Path

import pytest

from hawkapi.responses.file_response import FileResponse
from hawkapi.responses.html_response import HTMLResponse
from hawkapi.responses.redirect import RedirectResponse
from hawkapi.responses.sse import EventSourceResponse, ServerSentEvent
from hawkapi.responses.streaming import StreamingResponse


async def _send_response(response):
    """Helper: invoke ASGI response and collect messages."""
    scope = {"type": "http", "method": "GET", "path": "/"}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await response(scope, receive, send)
    return sent


class TestHTMLResponse:
    @pytest.mark.asyncio
    async def test_html_content(self):
        resp = HTMLResponse("<h1>Hello</h1>")
        sent = await _send_response(resp)
        assert sent[0]["status"] == 200
        headers = dict(sent[0]["headers"])
        assert b"text/html" in headers[b"content-type"]
        assert sent[1]["body"] == b"<h1>Hello</h1>"

    @pytest.mark.asyncio
    async def test_html_bytes(self):
        resp = HTMLResponse(b"<p>bytes</p>")
        sent = await _send_response(resp)
        assert sent[1]["body"] == b"<p>bytes</p>"


class TestRedirectResponse:
    @pytest.mark.asyncio
    async def test_redirect_307(self):
        resp = RedirectResponse("/new-location")
        sent = await _send_response(resp)
        assert sent[0]["status"] == 307
        headers = dict(sent[0]["headers"])
        assert headers[b"location"] == b"/new-location"

    @pytest.mark.asyncio
    async def test_redirect_301(self):
        resp = RedirectResponse("/permanent", status_code=301)
        sent = await _send_response(resp)
        assert sent[0]["status"] == 301

    @pytest.mark.asyncio
    async def test_redirect_body_empty(self):
        resp = RedirectResponse("/somewhere")
        sent = await _send_response(resp)
        assert sent[1]["body"] == b""


class TestStreamingResponse:
    @pytest.mark.asyncio
    async def test_streams_chunks(self):
        async def generate():
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        resp = StreamingResponse(generate())
        sent = await _send_response(resp)
        assert sent[0]["status"] == 200

        body_msgs = [m for m in sent if m["type"] == "http.response.body"]
        # 3 chunks + 1 final empty
        assert len(body_msgs) == 4
        assert body_msgs[0]["body"] == b"chunk1"
        assert body_msgs[1]["body"] == b"chunk2"
        assert body_msgs[2]["body"] == b"chunk3"
        assert body_msgs[3]["body"] == b""
        assert body_msgs[3]["more_body"] is False

    @pytest.mark.asyncio
    async def test_custom_content_type(self):
        async def gen():
            yield b"data"

        resp = StreamingResponse(gen(), content_type="text/csv")
        sent = await _send_response(resp)
        headers = dict(sent[0]["headers"])
        assert headers[b"content-type"] == b"text/csv"


class TestFileResponse:
    @pytest.mark.asyncio
    async def test_serves_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Hello, file!")
            f.flush()
            path = f.name

        try:
            resp = FileResponse(path)
            sent = await _send_response(resp)
            assert sent[0]["status"] == 200
            headers = dict(sent[0]["headers"])
            assert b"text/plain" in headers[b"content-type"]
            assert headers[b"content-length"] == b"12"

            body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
            assert body == b"Hello, file!"
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_download_filename(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"a,b,c")
            f.flush()
            path = f.name

        try:
            resp = FileResponse(path, filename="report.csv")
            sent = await _send_response(resp)
            headers = dict(sent[0]["headers"])
            assert b"attachment" in headers[b"content-disposition"]
            assert b"report.csv" in headers[b"content-disposition"]
        finally:
            Path(path).unlink()


class TestSSE:
    def test_server_sent_event_encode(self):
        event = ServerSentEvent(data="hello", event="msg", id="1")
        encoded = event.encode()
        assert b"id: 1" in encoded
        assert b"event: msg" in encoded
        assert b"data: hello" in encoded

    def test_multiline_data(self):
        event = ServerSentEvent(data="line1\nline2")
        encoded = event.encode()
        assert b"data: line1" in encoded
        assert b"data: line2" in encoded

    @pytest.mark.asyncio
    async def test_event_source_response(self):
        async def stream():
            yield ServerSentEvent(data="first", event="update")
            yield "plain string"

        resp = EventSourceResponse(stream())
        sent = await _send_response(resp)
        assert sent[0]["status"] == 200
        headers = dict(sent[0]["headers"])
        assert headers[b"content-type"] == b"text/event-stream"
        assert headers[b"cache-control"] == b"no-cache"

        body_msgs = [m for m in sent if m["type"] == "http.response.body" and m.get("body")]
        assert len(body_msgs) >= 2
