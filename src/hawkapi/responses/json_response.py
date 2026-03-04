"""JSON response using msgspec for maximum serialization speed."""

from __future__ import annotations

from typing import Any

from hawkapi._types import Receive, Scope, Send
from hawkapi.serialization.encoder import encode_response as _encode


class JSONResponse:
    """High-performance JSON response using msgspec.json.encode."""

    __slots__ = ("status_code", "body", "_headers")

    def __init__(
        self,
        content: Any = None,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Create a JSON response, serializing content with msgspec."""
        self.status_code = status_code
        self._headers = headers or {}
        self.body = _encode(content) if content is not None else b"null"

    def _build_raw_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = [
            (b"content-length", str(len(self.body)).encode("latin-1")),
        ]
        has_content_type = False
        for key, value in self._headers.items():
            lower = key.lower()
            if lower == "content-type":
                has_content_type = True
            raw.append((lower.encode("latin-1"), value.encode("latin-1")))
        if not has_content_type:
            raw.insert(0, (b"content-type", b"application/json"))
        return raw

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_raw_headers(),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": self.body,
            }
        )
