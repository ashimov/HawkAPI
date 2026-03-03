"""Streaming response — sends chunks as they arrive."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from hawkapi._types import Receive, Scope, Send


class StreamingResponse:
    """Response that streams content from an async iterator.

    Usage:
        async def generate():
            for i in range(10):
                yield f"chunk {i}\n".encode()

        return StreamingResponse(generate())
    """

    __slots__ = ("body_iterator", "status_code", "_headers", "content_type")

    def __init__(
        self,
        content: AsyncIterator[bytes],
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Create a streaming response from an async iterator of bytes."""
        self.body_iterator = content
        self.status_code = status_code
        self._headers = headers or {}
        self.content_type = content_type

    @property
    def headers(self) -> dict[str, str]:
        """Response headers as a string-to-string dictionary."""
        return self._headers

    def _build_raw_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = []
        has_content_type = False
        for key, value in self._headers.items():
            lower = key.lower()
            if lower == "content-type":
                has_content_type = True
            raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))

        if not has_content_type:
            raw.append((b"content-type", self.content_type.encode("latin-1")))
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
            async for chunk in self.body_iterator:
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )
        finally:
            _aclose: Any = getattr(self.body_iterator, "aclose", None)
            if _aclose is not None:
                await _aclose()
            await send({"type": "http.response.body", "body": b"", "more_body": False})
