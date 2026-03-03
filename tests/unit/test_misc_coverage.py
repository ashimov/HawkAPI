"""Tests for miscellaneous coverage gaps."""

from __future__ import annotations

from typing import Any

import pytest

from hawkapi.requests.state import State
from hawkapi.validation.decoder import decode_body
from hawkapi.validation.errors import RequestValidationError


class TestState:
    def test_state_delattr(self):
        """Covers state.py lines 29-30: __delattr__."""
        state = State()
        state.foo = "bar"
        assert state.foo == "bar"
        del state.foo
        with pytest.raises(AttributeError):
            _ = state.foo

    def test_state_repr(self):
        """Covers state.py line 36: __repr__."""
        state = State()
        state.x = 1
        r = repr(state)
        assert "State" in r


class TestDecodeBodyEmpty:
    @pytest.mark.asyncio
    async def test_empty_body_error(self):
        """Covers decoder.py lines 32-37: empty body raises RequestValidationError."""

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        import msgspec

        class Dummy(msgspec.Struct):
            x: int

        with pytest.raises(RequestValidationError):
            await decode_body(receive, Dummy)


class TestValidationErrors:
    def test_validation_error_detail_format(self):
        """Covers errors.py lines 68-71: format_msgspec_error with nested paths."""
        import msgspec

        from hawkapi.validation.errors import format_msgspec_error

        # Create a real validation error via decode
        decoder = msgspec.json.Decoder(type=int)
        try:
            decoder.decode(b'"not_int"')
        except msgspec.ValidationError as exc:
            errors = format_msgspec_error(exc)
            assert len(errors) >= 1
            assert errors[0].field == "$"


class TestConfigSettings:
    def test_coerce_list_from_string(self):
        """Covers settings.py lines 126-127: list coercion from comma-separated string."""
        from hawkapi.config.settings import _coerce

        result = _coerce("a, b, c", list)
        assert result == ["a", "b", "c"]

    def test_coerce_already_correct_type(self):
        """Covers settings.py line 116: value already is target type."""
        from hawkapi.config.settings import _coerce

        result = _coerce(42, int)
        assert result == 42

    def test_coerce_unknown_type_passthrough(self):
        """Covers settings.py line 127: unknown type passthrough."""
        from hawkapi.config.settings import _coerce

        result = _coerce("test", dict)
        assert result == "test"


class TestWebSocketEdgeCases:
    @pytest.mark.asyncio
    async def test_websocket_accept_with_subprotocol(self):
        """Covers websocket/connection.py lines 73, 77, 79: accept with subprotocol + headers."""
        from hawkapi.websocket.connection import WebSocket

        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "websocket.connect"}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        ws = WebSocket(
            scope={"type": "websocket", "path": "/ws", "headers": [], "query_string": b""},
            receive=receive,
            send=send,
        )
        await ws.accept(subprotocol="graphql-ws", headers={"x-custom": "val"})
        assert sent[0]["subprotocol"] == "graphql-ws"
        assert sent[0]["headers"] is not None

    @pytest.mark.asyncio
    async def test_websocket_close_idempotent(self):
        """Covers websocket/connection.py lines 89, 92-93: close when disconnected."""
        from hawkapi.websocket.connection import WebSocket, WebSocketState

        async def receive() -> dict[str, Any]:
            return {"type": "websocket.disconnect"}

        async def send(msg: dict[str, Any]) -> None:
            pass

        ws = WebSocket(
            scope={"type": "websocket", "path": "/ws", "headers": [], "query_string": b""},
            receive=receive,
            send=send,
        )
        # Force state to disconnected
        ws._state = WebSocketState.DISCONNECTED
        # This should be a no-op
        await ws.close()

    @pytest.mark.asyncio
    async def test_websocket_receive_when_disconnected(self):
        """Covers websocket/connection.py line 100: receive when disconnected."""
        from hawkapi.websocket.connection import WebSocket, WebSocketDisconnect, WebSocketState

        async def receive() -> dict[str, Any]:
            return {"type": "websocket.disconnect"}

        async def send(msg: dict[str, Any]) -> None:
            pass

        ws = WebSocket(
            scope={"type": "websocket", "path": "/ws", "headers": [], "query_string": b""},
            receive=receive,
            send=send,
        )
        ws._state = WebSocketState.DISCONNECTED
        with pytest.raises(WebSocketDisconnect):
            await ws.receive()

    @pytest.mark.asyncio
    async def test_websocket_headers(self):
        """Covers websocket/connection.py headers lazy init."""
        from hawkapi.websocket.connection import WebSocket

        async def receive() -> dict[str, Any]:
            return {"type": "websocket.connect"}

        async def send(msg: dict[str, Any]) -> None:
            pass

        scope = {
            "type": "websocket",
            "path": "/ws",
            "headers": [(b"x-test", b"val")],
            "query_string": b"",
        }
        ws = WebSocket(scope=scope, receive=receive, send=send)
        assert ws.headers.get("x-test") == "val"


class TestRadixTreeBacktrack:
    def test_find_allowed_methods_with_param(self):
        """Covers _radix_tree.py lines 185-192: _collect_methods with param child."""
        from hawkapi.routing._radix_tree import RadixTree
        from hawkapi.routing.route import Route

        tree = RadixTree()

        async def handler():
            pass

        r1 = Route(path="/users/{user_id:int}", handler=handler, methods=frozenset({"GET"}))
        r2 = Route(path="/users/{user_id:int}", handler=handler, methods=frozenset({"DELETE"}))
        tree.insert(r1)
        tree.insert(r2)

        methods = tree.find_allowed_methods("/users/42")
        assert "GET" in methods
        assert "DELETE" in methods

    def test_backtrack_on_param_mismatch(self):
        """Covers _radix_tree.py lines 152-155: backtrack on param mismatch."""
        from hawkapi.routing._radix_tree import RadixTree
        from hawkapi.routing.route import Route

        tree = RadixTree()

        async def handler():
            pass

        r = Route(
            path="/items/{item_id:int}/details",
            handler=handler,
            methods=frozenset({"GET"}),
        )
        tree.insert(r)

        # "abc" should not match :int
        result = tree.lookup("/items/abc/details", "GET")
        assert result is None


class TestFormDataEdgeCases:
    def test_parse_urlencoded_empty(self):
        """Covers form_data.py edge case."""
        from hawkapi.requests.form_data import parse_urlencoded

        result = parse_urlencoded(b"")
        assert len(result.fields) == 0


class TestFileResponse:
    def test_file_response_not_found(self):
        """Covers file_response.py line 36: file not found raises."""
        from hawkapi.responses.file_response import FileResponse

        with pytest.raises(FileNotFoundError, match="File not found"):
            FileResponse("/nonexistent/path/file.txt")

    @pytest.mark.asyncio
    async def test_file_response_sends_file(self):
        """Covers file_response.py lines 49, 54: sends file content."""
        import tempfile

        from hawkapi.responses.file_response import FileResponse

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("hello world")
            path = f.name

        try:
            resp = FileResponse(path)
            sent: list[dict[str, Any]] = []

            async def receive() -> dict[str, Any]:
                return {"type": "http.request", "body": b""}

            async def send(msg: dict[str, Any]) -> None:
                sent.append(msg)

            await resp({"type": "http"}, receive, send)
            assert sent[0]["status"] == 200
        finally:
            import os

            os.unlink(path)


class TestSSEResponse:
    @pytest.mark.asyncio
    async def test_sse_response(self):
        """Covers sse.py lines 35, 69, 78: SSE response with events."""
        from hawkapi.responses.sse import EventSourceResponse, ServerSentEvent

        events = [
            ServerSentEvent(data="hello", event="message"),
            ServerSentEvent(data="world"),
        ]

        async def gen():
            for e in events:
                yield e

        resp = EventSourceResponse(gen())
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b""}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await resp({"type": "http"}, receive, send)
        assert sent[0]["status"] == 200
        # Check content type
        headers_dict = {k: v for k, v in sent[0].get("headers", [])}
        assert b"text/event-stream" in headers_dict.get(b"content-type", b"")
