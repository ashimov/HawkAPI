"""Multipart form data parser.

Lightweight parser for multipart/form-data and application/x-www-form-urlencoded.
"""

from __future__ import annotations

from urllib.parse import parse_qs


class UploadFile:
    """Represents an uploaded file with async read/seek interface."""

    __slots__ = ("filename", "content_type", "data", "_pos")

    def __init__(self, filename: str, content_type: str, data: bytes) -> None:
        """Initialize with filename, MIME type, and raw file data."""
        self.filename = filename
        self.content_type = content_type
        self.data = data
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        """Read up to *size* bytes. Read all remaining if size is -1."""
        if size == -1:
            result = self.data[self._pos :]
            self._pos = len(self.data)
            return result
        result = self.data[self._pos : self._pos + size]
        self._pos += len(result)
        return result

    async def seek(self, offset: int) -> None:
        """Seek to the given byte offset."""
        self._pos = offset

    async def close(self) -> None:
        """No-op for in-memory files. Provided for interface compatibility."""

    @property
    def size(self) -> int:
        """Total size of the file data in bytes."""
        return len(self.data)

    def __repr__(self) -> str:
        return f"UploadFile(filename={self.filename!r}, size={len(self.data)})"


class FormData:
    """Parsed form data — supports both urlencoded and multipart forms."""

    __slots__ = ("_fields", "_files")

    def __init__(
        self,
        fields: dict[str, str] | None = None,
        files: dict[str, UploadFile] | None = None,
    ) -> None:
        """Initialize with optional field and file dictionaries."""
        self._fields = fields or {}
        self._files = files or {}

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a form field value by key, or default if missing."""
        return self._fields.get(key, default)

    def getlist(self, key: str) -> list[str]:
        """Get a form field value as a list."""
        val = self._fields.get(key)
        return [val] if val is not None else []

    @property
    def fields(self) -> dict[str, str]:
        """All form fields as a string-to-string dictionary."""
        return self._fields

    @property
    def files(self) -> dict[str, UploadFile]:
        """All uploaded files as a string-to-UploadFile dictionary."""
        return self._files

    def __contains__(self, key: str) -> bool:
        return key in self._fields or key in self._files

    def __repr__(self) -> str:
        return f"FormData(fields={list(self._fields.keys())}, files={list(self._files.keys())})"


def parse_urlencoded(body: bytes) -> FormData:
    """Parse application/x-www-form-urlencoded body."""
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    fields = {k: v[0] for k, v in parsed.items()}
    return FormData(fields=fields)


def parse_multipart(body: bytes, boundary: str) -> FormData:
    """Parse multipart/form-data body."""
    fields: dict[str, str] = {}
    files: dict[str, UploadFile] = {}

    boundary_bytes = boundary.encode("utf-8")
    delimiter = b"--" + boundary_bytes
    parts = body.split(delimiter)

    for part in parts[1:]:  # Skip preamble
        if part.startswith(b"--"):
            break  # End marker

        # Split headers and body
        if b"\r\n\r\n" in part:
            header_section, _, part_body = part.partition(b"\r\n\r\n")
        elif b"\n\n" in part:
            header_section, _, part_body = part.partition(b"\n\n")
        else:
            continue

        # Remove the trailing \r\n boundary separator (not arbitrary bytes)
        if part_body.endswith(b"\r\n"):
            part_body = part_body[:-2]
        elif part_body.endswith(b"\n"):
            part_body = part_body[:-1]

        # Parse headers
        headers: dict[str, str] = {}
        for line in header_section.split(b"\r\n"):
            line = line.strip()
            if not line:
                continue
            if b":" in line:
                key, _, value = line.partition(b":")
                headers[key.decode("utf-8").lower().strip()] = value.decode("utf-8").strip()

        content_disposition = headers.get("content-disposition", "")
        name = _extract_param(content_disposition, "name")
        filename = _extract_param(content_disposition, "filename")

        if not name:
            continue

        if filename:
            content_type = headers.get("content-type", "application/octet-stream")
            files[name] = UploadFile(filename=filename, content_type=content_type, data=part_body)
        else:
            fields[name] = part_body.decode("utf-8")

    return FormData(fields=fields, files=files)


def _extract_param(header: str, param: str) -> str | None:
    """Extract a parameter value from a header like Content-Disposition."""
    search = f'{param}="'
    idx = header.find(search)
    if idx == -1:
        # Try without quotes
        search = f"{param}="
        idx = header.find(search)
        if idx == -1:
            return None
        start = idx + len(search)
        end = header.find(";", start)
        return header[start:end].strip() if end != -1 else header[start:].strip()

    start = idx + len(search)
    end = header.find('"', start)
    return header[start:end] if end != -1 else None
