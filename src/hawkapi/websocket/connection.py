"""WebSocket connection wrapper."""

from __future__ import annotations

from enum import Enum
from typing import Any

import msgspec

from hawkapi._types import Receive, Send
from hawkapi.requests.headers import Headers


class WebSocketState(Enum):
    """Possible states of a WebSocket connection."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class WebSocketDisconnect(Exception):
    """Raised when the WebSocket is disconnected."""

    def __init__(self, code: int = 1000) -> None:
        self.code = code


class WebSocket:
    """WebSocket connection — wraps the ASGI WebSocket protocol.

    Usage:
        @app.websocket("/ws")
        async def ws_handler(ws: WebSocket):
            await ws.accept()
            while True:
                data = await ws.receive_text()
                await ws.send_text(f"Echo: {data}")
    """

    __slots__ = ("scope", "_receive", "_send", "_state", "_headers")

    def __init__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        self.scope = scope
        self._receive = receive
        self._send = send
        self._state = WebSocketState.CONNECTING
        self._headers: Headers | None = None

    @property
    def path(self) -> str:
        return self.scope["path"]

    @property
    def query_string(self) -> bytes:
        return self.scope.get("query_string", b"")

    @property
    def headers(self) -> Headers:
        if self._headers is None:
            self._headers = Headers(self.scope.get("headers", []))
        return self._headers

    @property
    def state(self) -> WebSocketState:
        return self._state

    async def accept(
        self,
        subprotocol: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Accept the WebSocket connection."""
        if self._state != WebSocketState.CONNECTING:
            raise RuntimeError(f"Cannot accept: state is {self._state.value}")

        msg: dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol:
            msg["subprotocol"] = subprotocol
        if headers:
            msg["headers"] = [
                (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()
            ]
        await self._send(msg)
        self._state = WebSocketState.CONNECTED

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the WebSocket connection (idempotent)."""
        if self._state == WebSocketState.DISCONNECTED:
            return
        try:
            await self._send({"type": "websocket.close", "code": code, "reason": reason})
        except Exception:  # noqa: S110
            pass
        finally:
            self._state = WebSocketState.DISCONNECTED

    async def receive(self) -> dict[str, Any]:
        """Receive the next WebSocket message."""
        if self._state == WebSocketState.DISCONNECTED:
            raise WebSocketDisconnect()

        message = await self._receive()
        if message["type"] == "websocket.disconnect":
            self._state = WebSocketState.DISCONNECTED
            raise WebSocketDisconnect(code=message.get("code", 1000))
        return message

    async def receive_text(self) -> str:
        """Receive a text message."""
        msg = await self.receive()
        text = msg.get("text")
        if text is None:
            raise RuntimeError("Expected text frame, got binary")
        return text

    async def receive_bytes(self) -> bytes:
        """Receive a binary message."""
        msg = await self.receive()
        data = msg.get("bytes")
        if data is None:
            raise RuntimeError("Expected binary frame, got text")
        return data

    async def receive_json(self) -> Any:
        """Receive and decode a JSON message."""
        text = await self.receive_text()
        return msgspec.json.decode(text.encode("utf-8"))

    async def send_text(self, data: str) -> None:
        """Send a text message."""
        if self._state != WebSocketState.CONNECTED:
            raise RuntimeError(f"Cannot send: WebSocket state is {self._state.value}")
        await self._send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        """Send a binary message."""
        if self._state != WebSocketState.CONNECTED:
            raise RuntimeError(f"Cannot send: WebSocket state is {self._state.value}")
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any) -> None:
        """Send a JSON message."""
        text = msgspec.json.encode(data).decode("utf-8")
        await self.send_text(text)

    async def __aiter__(self) -> Any:
        """Iterate over incoming text messages until disconnect."""
        try:
            while True:
                yield await self.receive_text()
        except WebSocketDisconnect:
            return
