"""Base Response class for ASGI."""

from __future__ import annotations

from hawkapi._types import Receive, Scope, Send


class Response:
    """Base HTTP response that sends via the ASGI protocol."""

    __slots__ = ("status_code", "body", "_headers", "content_type")

    def __init__(
        self,
        content: bytes | str = b"",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        """Create a response with content, status code, and optional headers."""
        self.status_code = status_code
        self.content_type = content_type
        self._headers = headers or {}

        if isinstance(content, str):
            self.body = content.encode("utf-8")
        else:
            self.body = content

    @property
    def headers(self) -> dict[str, str]:
        """Response headers as a string-to-string dictionary."""
        return self._headers

    @staticmethod
    def _sanitize_header_value(value: str) -> str:
        """Strip CR/LF from header values to prevent header injection."""
        return value.replace("\r", "").replace("\n", "")

    def _build_raw_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = []
        has_content_type = False
        for key, value in self._headers.items():
            lower = key.lower()
            if lower == "content-type":
                has_content_type = True
            safe_value = self._sanitize_header_value(value)
            raw.append((lower.encode("latin-1"), safe_value.encode("latin-1")))

        if not has_content_type:
            raw.append((b"content-type", self.content_type.encode("latin-1")))

        # Only auto-compute content-length if not explicitly set in headers
        if "content-length" not in self._headers:
            raw.append((b"content-length", str(len(self.body)).encode("latin-1")))
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
