"""Tests for WebSocket support."""

import msgspec
import pytest

from hawkapi import HawkAPI
from hawkapi.websocket.connection import WebSocket, WebSocketDisconnect, WebSocketState


class TestWebSocketConnection:
    @pytest.mark.asyncio
    async def test_accept(self):
        sent = []

        async def receive():
            return {"type": "websocket.connect"}

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        ws = WebSocket(scope, receive, send)
        assert ws.state == WebSocketState.CONNECTING

        await ws.accept()
        assert ws.state == WebSocketState.CONNECTED
        assert sent[0]["type"] == "websocket.accept"

    @pytest.mark.asyncio
    async def test_send_receive_text(self):
        messages = [
            {"type": "websocket.receive", "text": "hello"},
        ]
        msg_iter = iter(messages)
        sent = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        ws = WebSocket(scope, receive, send)
        await ws.accept()

        text = await ws.receive_text()
        assert text == "hello"

        await ws.send_text("world")
        assert sent[-1] == {"type": "websocket.send", "text": "world"}

    @pytest.mark.asyncio
    async def test_send_receive_bytes(self):
        messages = [
            {"type": "websocket.receive", "bytes": b"\x00\x01"},
        ]
        msg_iter = iter(messages)
        sent = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        ws = WebSocket(scope, receive, send)
        await ws.accept()

        data = await ws.receive_bytes()
        assert data == b"\x00\x01"

        await ws.send_bytes(b"\x02\x03")
        assert sent[-1] == {"type": "websocket.send", "bytes": b"\x02\x03"}

    @pytest.mark.asyncio
    async def test_send_receive_json(self):
        messages = [
            {"type": "websocket.receive", "text": '{"key":"value"}'},
        ]
        msg_iter = iter(messages)
        sent = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        ws = WebSocket(scope, receive, send)
        await ws.accept()

        data = await ws.receive_json()
        assert data == {"key": "value"}

        await ws.send_json({"result": 42})
        last = sent[-1]
        assert last["type"] == "websocket.send"
        assert msgspec.json.decode(last["text"].encode()) == {"result": 42}

    @pytest.mark.asyncio
    async def test_disconnect_raises(self):
        messages = [
            {"type": "websocket.disconnect", "code": 1000},
        ]
        msg_iter = iter(messages)
        sent = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        ws = WebSocket(scope, receive, send)
        await ws.accept()

        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_text()
        assert exc_info.value.code == 1000
        assert ws.state == WebSocketState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_close(self):
        sent = []

        async def receive():
            return {"type": "websocket.connect"}

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        ws = WebSocket(scope, receive, send)
        await ws.accept()

        await ws.close(code=1001, reason="going away")
        assert ws.state == WebSocketState.DISCONNECTED
        assert sent[-1]["type"] == "websocket.close"
        assert sent[-1]["code"] == 1001

    @pytest.mark.asyncio
    async def test_async_iter(self):
        messages = [
            {"type": "websocket.receive", "text": "a"},
            {"type": "websocket.receive", "text": "b"},
            {"type": "websocket.disconnect", "code": 1000},
        ]
        msg_iter = iter(messages)
        sent = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        ws = WebSocket(scope, receive, send)
        await ws.accept()

        received = []
        async for msg in ws:
            received.append(msg)
        assert received == ["a", "b"]

    @pytest.mark.asyncio
    async def test_properties(self):
        scope = {
            "type": "websocket",
            "path": "/ws/chat",
            "headers": [(b"origin", b"http://localhost")],
            "query_string": b"room=general",
        }
        ws = WebSocket(scope, None, None)
        assert ws.path == "/ws/chat"
        assert ws.query_string == b"room=general"
        assert ws.headers.get("origin") == "http://localhost"


class TestWebSocketRouting:
    @pytest.mark.asyncio
    async def test_websocket_route(self):
        app = HawkAPI(openapi_url=None)
        log = []

        @app.websocket("/ws")
        async def ws_handler(ws: WebSocket):
            await ws.accept()
            text = await ws.receive_text()
            log.append(text)
            await ws.send_text(f"Echo: {text}")
            await ws.close()

        messages = [
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": "hello"},
        ]
        msg_iter = iter(messages)
        sent = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
        await app(scope, receive, send)

        assert log == ["hello"]
        assert any(m.get("text") == "Echo: hello" for m in sent)

    @pytest.mark.asyncio
    async def test_websocket_no_handler_closes(self):
        app = HawkAPI(openapi_url=None)
        sent = []

        async def receive():
            return {"type": "websocket.connect"}

        async def send(msg):
            sent.append(msg)

        scope = {"type": "websocket", "path": "/ws/nope", "headers": [], "query_string": b""}
        await app(scope, receive, send)

        assert sent[0]["type"] == "websocket.close"
        assert sent[0]["code"] == 4004
