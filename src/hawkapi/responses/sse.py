"""Server-Sent Events (SSE) response."""

from __future__ import annotations

from collections.abc import AsyncIterator

from hawkapi._types import Receive, Scope, Send


class ServerSentEvent:
    """Represents a single SSE event."""

    __slots__ = ("data", "event", "id", "retry")

    def __init__(
        self,
        data: str,
        *,
        event: str | None = None,
        id: str | None = None,
        retry: int | None = None,
    ) -> None:
        """Create an SSE event with data and optional event type, id, retry."""
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry

    def encode(self) -> bytes:
        """Encode the event into SSE wire format."""
        lines: list[str] = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.event is not None:
            lines.append(f"event: {self.event}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        for line in self.data.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            lines.append(f"data: {line}")
        lines.append("")
        lines.append("")
        return "\n".join(lines).encode("utf-8")


class EventSourceResponse:
    """Response that streams Server-Sent Events.

    Usage:
        async def event_stream():
            for i in range(10):
                yield ServerSentEvent(data=f"Message {i}", event="update")

        return EventSourceResponse(event_stream())
    """

    __slots__ = ("body_iterator", "status_code", "_headers")

    def __init__(
        self,
        content: AsyncIterator[ServerSentEvent | str],
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Create an SSE response from an async iterator of events."""
        self.body_iterator = content
        self.status_code = status_code
        self._headers = headers or {}

    @property
    def headers(self) -> dict[str, str]:
        """Response headers as a string-to-string dictionary."""
        return self._headers

    def _build_raw_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = [
            (b"content-type", b"text/event-stream"),
            (b"cache-control", b"no-cache"),
            (b"connection", b"keep-alive"),
        ]
        for key, value in self._headers.items():
            raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))
        return raw

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_raw_headers(),
            }
        )
        try:
            async for event in self.body_iterator:
                if isinstance(event, str):
                    chunk = ServerSentEvent(data=event).encode()
                else:
                    chunk = event.encode()
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )
        finally:
            _aclose = getattr(self.body_iterator, "aclose", None)
            if _aclose is not None:
                await _aclose()
            await send({"type": "http.response.body", "body": b"", "more_body": False})
