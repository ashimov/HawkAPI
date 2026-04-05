"""File response — serves files from disk efficiently."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from hawkapi._types import Receive, Scope, Send


class FileResponse:
    """Response that serves a file from disk.

    Usage:
        return FileResponse("path/to/file.pdf")
        return FileResponse("report.csv", filename="download.csv")
    """

    __slots__ = ("path", "status_code", "_headers", "content_type", "filename")

    CHUNK_SIZE = 64 * 1024  # 64KB

    def __init__(
        self,
        path: str | Path,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> None:
        """Create a file response. Raises FileNotFoundError if path is invalid."""
        self.path = Path(path).resolve()

        # Path traversal protection: ensure path is a regular file
        if not self.path.is_file():
            raise FileNotFoundError(f"File not found: {self.path}")

        self.status_code = status_code
        self._headers = headers or {}
        self.filename = filename

        if content_type is None:
            content_type, _ = mimetypes.guess_type(str(self.path))
            content_type = content_type or "application/octet-stream"
        self.content_type = content_type

    @property
    def headers(self) -> dict[str, str]:
        """Response headers as a string-to-string dictionary."""
        return self._headers

    def _build_raw_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = []
        for key, value in self._headers.items():
            raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))

        raw.append((b"content-type", self.content_type.encode("latin-1")))

        try:
            stat = self.path.stat()
        except OSError as exc:
            raise FileNotFoundError(f"File not found: {self.path}") from exc
        raw.append((b"content-length", str(stat.st_size).encode("latin-1")))

        if self.filename:
            # Sanitize filename to prevent header injection
            safe_name = (
                self.filename.replace('"', "")
                .replace("\r", "")
                .replace("\n", "")
                .replace(";", "")
                .replace("\\", "")
            )
            raw.append(
                (
                    b"content-disposition",
                    f'attachment; filename="{safe_name}"'.encode("latin-1"),
                )
            )

        return raw

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_raw_headers(),
            }
        )
        with open(self.path, "rb") as f:
            while True:
                chunk = f.read(self.CHUNK_SIZE)
                if not chunk:
                    # EOF — send terminal frame
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                    break
                # Peek ahead to determine if this is the last chunk
                next_chunk = f.read(1)
                if next_chunk:
                    # More data available — send with more_body=True
                    f.seek(-1, 1)  # Unread the peeked byte
                    await send({"type": "http.response.body", "body": chunk, "more_body": True})
                else:
                    # This is the last chunk — send with more_body=False
                    await send({"type": "http.response.body", "body": chunk, "more_body": False})
                    break
