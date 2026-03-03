"""Plain text response."""

from __future__ import annotations

from hawkapi.responses.response import Response


class PlainTextResponse(Response):
    """Response that returns plain text content.

    Usage:
        return PlainTextResponse("Hello, World!")
    """

    def __init__(
        self,
        content: str = "",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Create a plain text response."""
        super().__init__(
            content=content.encode("utf-8"),
            status_code=status_code,
            headers=headers,
            content_type="text/plain; charset=utf-8",
        )
