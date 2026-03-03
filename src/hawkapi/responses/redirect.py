"""Redirect responses."""

from __future__ import annotations

from hawkapi.responses.response import Response


class RedirectResponse(Response):
    """HTTP redirect response."""

    def __init__(
        self,
        url: str,
        *,
        status_code: int = 307,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Create a redirect response to the given URL."""
        merged = {"location": url, **(headers or {})}
        super().__init__(
            content=b"",
            status_code=status_code,
            headers=merged,
        )
