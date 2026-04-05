"""Static file serving — mount a directory to serve files."""

from __future__ import annotations

import hashlib
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path
from typing import Any

from hawkapi._types import Receive, Scope, Send
from hawkapi.responses.file_response import FileResponse
from hawkapi.responses.response import Response
from hawkapi.serialization.encoder import encode_response


class StaticFiles:
    """ASGI app that serves static files from a directory.

    Supports ETag, Last-Modified, and Cache-Control headers for efficient
    client-side caching. Returns 304 Not Modified when appropriate.

    Usage:
        app.mount("/static", StaticFiles(directory="static"))
        app.mount("/static", StaticFiles(directory="static", max_age=3600))
    """

    def __init__(
        self,
        *,
        directory: str | Path,
        html: bool = False,
        max_age: int = 0,
    ) -> None:
        self.directory = Path(directory).resolve()
        self.html = html
        self.max_age = max_age

        if not self.directory.is_dir():
            raise RuntimeError(f"Static directory not found: {self.directory}")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return

        method = scope.get("method", "GET")
        if method not in ("GET", "HEAD"):
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/method-not-allowed",
                        "title": "Method Not Allowed",
                        "status": 405,
                    }
                ),
                status_code=405,
                content_type="application/problem+json",
            )
            await response(scope, receive, send)
            return

        path = scope.get("path", "/")
        # Remove leading slash
        rel_path = path.lstrip("/")

        # Resolve the file path
        file_path = (self.directory / rel_path).resolve()

        # Path traversal protection
        if not file_path.is_relative_to(self.directory):
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/not-found",
                        "title": "Not Found",
                        "status": 404,
                    }
                ),
                status_code=404,
                content_type="application/problem+json",
            )
            await response(scope, receive, send)
            return

        # For HEAD requests, wrap send to suppress body after first chunk
        actual_send = send
        if method == "HEAD":
            _body_sent = False

            async def head_send(message: dict[str, Any]) -> None:
                nonlocal _body_sent
                if message["type"] == "http.response.body":
                    if _body_sent:
                        return  # Suppress subsequent body chunks
                    _body_sent = True
                    message = {**message, "body": b"", "more_body": False}
                await actual_send(message)

            send = head_send

        # Try file directly
        if file_path.is_file():
            if await self._serve_with_cache(file_path, scope, receive, send):
                return
            return

        # Try index.html in html mode
        if self.html and file_path.is_dir():
            index = file_path / "index.html"
            if index.is_file():
                if await self._serve_with_cache(index, scope, receive, send):
                    return
                return

        # 404 — fall through
        response = Response(
            content=encode_response(
                {
                    "type": "https://hawkapi.ashimov.com/errors/not-found",
                    "title": "Not Found",
                    "status": 404,
                    "detail": "Not found",
                }
            ),
            status_code=404,
            content_type="application/problem+json",
        )
        await response(scope, receive, send)

    async def _serve_with_cache(
        self,
        file_path: Path,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> bool:
        """Serve a file with ETag/Last-Modified/Cache-Control. Returns True on success."""
        try:
            stat = file_path.stat()
        except OSError:
            return False

        etag = _compute_etag(stat.st_mtime, stat.st_size)
        last_modified = formatdate(stat.st_mtime, usegmt=True)

        # Check conditional headers
        headers_raw = dict(scope.get("headers", []))
        if_none_match = headers_raw.get(b"if-none-match", b"").decode("latin-1")
        if if_none_match:
            # Support wildcard and multi-value If-None-Match (RFC 7232 §3.2)
            if if_none_match.strip() == "*":
                await _send_304(send, etag, last_modified, self.max_age)
                return True
            # Strip W/ prefix for weak comparison and check each ETag
            etag_value = etag.removeprefix("W/")
            for candidate in if_none_match.split(","):
                candidate = candidate.strip().removeprefix("W/")
                if candidate == etag_value:
                    await _send_304(send, etag, last_modified, self.max_age)
                    return True

        if_modified = headers_raw.get(b"if-modified-since")
        if if_modified is not None and not if_none_match:
            try:
                client_time = parsedate_to_datetime(if_modified.decode("latin-1"))  # pyright: ignore[reportUnknownVariableType]
                file_time = parsedate_to_datetime(last_modified)  # pyright: ignore[reportUnknownVariableType]
                if file_time <= client_time:
                    await _send_304(send, etag, last_modified, self.max_age)
                    return True
            except (ValueError, TypeError):
                pass

        # Serve the file with cache headers
        file_response = FileResponse(file_path)
        file_response.headers["etag"] = etag
        file_response.headers["last-modified"] = last_modified
        if self.max_age > 0:
            file_response.headers["cache-control"] = f"public, max-age={self.max_age}"
        else:
            file_response.headers["cache-control"] = "no-cache"
        await file_response(scope, receive, send)
        return True


def _compute_etag(mtime: float, size: int) -> str:
    """Compute a weak ETag from file modification time and size."""
    token = f"{mtime}-{size}".encode()
    digest = hashlib.md5(token, usedforsecurity=False).hexdigest()[:16]
    return f'W/"{digest}"'


async def _send_304(send: Send, etag: str, last_modified: str, max_age: int) -> None:
    """Send a 304 Not Modified response."""
    headers: list[tuple[bytes, bytes]] = [
        (b"etag", etag.encode("latin-1")),
        (b"last-modified", last_modified.encode("latin-1")),
    ]
    if max_age > 0:
        headers.append((b"cache-control", f"public, max-age={max_age}".encode("latin-1")))
    await send({"type": "http.response.start", "status": 304, "headers": headers})
    await send({"type": "http.response.body", "body": b""})
