"""HTML response."""

from __future__ import annotations

from hawkapi.responses.response import Response


class HTMLResponse(Response):
    """Response that returns HTML content."""

    def __init__(
        self,
        content: str | bytes = "",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Create an HTML response with text/html content type."""
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            content_type="text/html; charset=utf-8",
        )
