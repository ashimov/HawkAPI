"""GZip compression middleware with streaming support."""

from __future__ import annotations

import gzip as gzip_lib
import io
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class GZipMiddleware(Middleware):
    """Compress responses with GZip when the client supports it.

    Supports both buffered (small) and streaming (large/chunked) responses.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        minimum_size: int = 500,
        compresslevel: int = 6,
    ) -> None:
        super().__init__(app)
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check if client accepts gzip
        accept_encoding = ""
        for key, value in scope.get("headers", []):
            if key == b"accept-encoding":
                accept_encoding = value.decode("latin-1")
                break

        if "gzip" not in accept_encoding:
            await self.app(scope, receive, send)
            return

        responder = _GZipResponder(send, self.minimum_size, self.compresslevel)
        try:
            await self.app(scope, receive, responder.send)
        finally:
            await responder.finalize()


class _GZipResponder:
    """Handles GZip compression with streaming support."""

    __slots__ = (
        "_send",
        "_minimum_size",
        "_compresslevel",
        "_initial_message",
        "_buf",
        "_gzip_file",
        "_gzip_buf",
        "_started",
        "_pass_through",
    )

    def __init__(self, send: Send, minimum_size: int, compresslevel: int) -> None:
        self._send = send
        self._minimum_size = minimum_size
        self._compresslevel = compresslevel
        self._initial_message: dict[str, Any] | None = None
        self._buf = io.BytesIO()
        self._gzip_file: gzip_lib.GzipFile | None = None
        self._gzip_buf: io.BytesIO | None = None
        self._started = False
        self._pass_through = False

    async def send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self._initial_message = message
            return

        if message["type"] != "http.response.body":
            await self._send(message)
            return

        body = message.get("body", b"")
        more_body = message.get("more_body", False)

        if self._pass_through:
            await self._send(message)
            return

        if self._started and self._gzip_file is not None:
            # Streaming mode — compress and forward
            await self._stream_chunk(body, more_body)
            return

        # Still buffering
        self._buf.write(body)

        if not more_body:
            # Final chunk — decide based on total size
            all_body = self._buf.getvalue()
            if len(all_body) < self._minimum_size:
                await self._send_passthrough(all_body)
            else:
                compressed = self._compress_all(all_body)
                await self._send_compressed_headers(len(compressed))
                await self._send(
                    {
                        "type": "http.response.body",
                        "body": compressed,
                        "more_body": False,
                    }
                )
            self._started = True
        elif self._buf.tell() >= self._minimum_size:
            # Enough buffered — start streaming compressed
            await self._start_streaming()

    async def _send_passthrough(self, body: bytes) -> None:
        """Send response without compression."""
        self._pass_through = True
        if self._initial_message:
            await self._send(self._initial_message)
        await self._send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )

    async def _start_streaming(self) -> None:
        """Begin streaming compressed data."""
        self._gzip_buf = io.BytesIO()
        self._gzip_file = gzip_lib.GzipFile(
            fileobj=self._gzip_buf,
            mode="wb",
            compresslevel=self._compresslevel,
        )

        await self._send_compressed_headers()

        # Compress buffered data
        self._gzip_file.write(self._buf.getvalue())
        self._gzip_file.flush()
        data = self._gzip_buf.getvalue()
        self._gzip_buf.seek(0)
        self._gzip_buf.truncate()

        if data:
            await self._send(
                {
                    "type": "http.response.body",
                    "body": data,
                    "more_body": True,
                }
            )
        self._started = True

    async def _stream_chunk(self, body: bytes, more_body: bool) -> None:
        """Compress and send a streaming chunk."""
        if self._gzip_file is None or self._gzip_buf is None:
            return

        if body:
            self._gzip_file.write(body)
            self._gzip_file.flush()

        if not more_body:
            self._gzip_file.close()

        data = self._gzip_buf.getvalue()
        self._gzip_buf.seek(0)
        self._gzip_buf.truncate()

        await self._send(
            {
                "type": "http.response.body",
                "body": data,
                "more_body": more_body,
            }
        )

    async def finalize(self) -> None:
        """Finalize if response never completed."""
        if not self._started and self._initial_message:
            # Response never sent body — send headers and empty body
            body = self._buf.getvalue()
            if body and len(body) >= self._minimum_size:
                compressed = self._compress_all(body)
                await self._send_compressed_headers(len(compressed))
                await self._send(
                    {
                        "type": "http.response.body",
                        "body": compressed,
                        "more_body": False,
                    }
                )
            else:
                await self._send_passthrough(body)

    def _compress_all(self, body: bytes) -> bytes:
        buf = io.BytesIO()
        with gzip_lib.GzipFile(
            fileobj=buf,
            mode="wb",
            compresslevel=self._compresslevel,
        ) as f:
            f.write(body)
        return buf.getvalue()

    async def _send_compressed_headers(
        self,
        content_length: int | None = None,
    ) -> None:
        if self._initial_message is None:
            return
        headers = [
            (k, v)
            for k, v in self._initial_message.get("headers", [])
            if k not in (b"content-length", b"content-encoding")
        ]
        headers.append((b"content-encoding", b"gzip"))
        if content_length is not None:
            headers.append((b"content-length", str(content_length).encode("latin-1")))
        headers.append((b"vary", b"Accept-Encoding"))

        await self._send(
            {
                "type": "http.response.start",
                "status": self._initial_message["status"],
                "headers": headers,
            }
        )
