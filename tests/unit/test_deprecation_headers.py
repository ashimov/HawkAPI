"""Tests for RFC 8594 deprecation response headers."""

from __future__ import annotations

from typing import Any

import pytest

from hawkapi import HawkAPI


async def _call_app(
    app: HawkAPI,
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestDeprecationHeaders:
    """Test RFC 8594 deprecation headers for deprecated routes."""

    @pytest.mark.asyncio
    async def test_deprecated_route_emits_deprecation_header(self) -> None:
        """A route with deprecated=True should include 'Deprecation: true'."""
        app = HawkAPI(openapi_url=None)

        @app.get("/old", deprecated=True)
        async def old_endpoint() -> dict[str, str]:
            return {"msg": "old"}

        result = await _call_app(app, "GET", "/old")

        assert result["status"] == 200
        assert result["headers"][b"deprecation"] == b"true"

    @pytest.mark.asyncio
    async def test_sunset_header_emitted_when_provided(self) -> None:
        """A deprecated route with sunset kwarg should emit Sunset header."""
        app = HawkAPI(openapi_url=None)
        sunset_date = "Sat, 01 Jun 2026 00:00:00 GMT"

        @app.get("/old", deprecated=True, sunset=sunset_date)
        async def old_endpoint() -> dict[str, str]:
            return {"msg": "old"}

        result = await _call_app(app, "GET", "/old")

        assert result["status"] == 200
        assert result["headers"][b"deprecation"] == b"true"
        assert result["headers"][b"sunset"] == sunset_date.encode("latin-1")

    @pytest.mark.asyncio
    async def test_link_header_emitted_when_deprecation_link_provided(self) -> None:
        """A deprecated route with deprecation_link should emit Link header."""
        app = HawkAPI(openapi_url=None)
        link_url = "https://docs.example.com/migration"

        @app.get("/old", deprecated=True, deprecation_link=link_url)
        async def old_endpoint() -> dict[str, str]:
            return {"msg": "old"}

        result = await _call_app(app, "GET", "/old")

        assert result["status"] == 200
        assert result["headers"][b"deprecation"] == b"true"
        expected_link = f'<{link_url}>; rel="deprecation"'
        assert result["headers"][b"link"] == expected_link.encode("latin-1")

    @pytest.mark.asyncio
    async def test_all_deprecation_headers_together(self) -> None:
        """A deprecated route with both sunset and link should emit all headers."""
        app = HawkAPI(openapi_url=None)
        sunset_date = "Sat, 01 Jun 2026 00:00:00 GMT"
        link_url = "https://docs.example.com/migration"

        @app.get(
            "/old",
            deprecated=True,
            sunset=sunset_date,
            deprecation_link=link_url,
        )
        async def old_endpoint() -> dict[str, str]:
            return {"msg": "old"}

        result = await _call_app(app, "GET", "/old")

        assert result["status"] == 200
        assert result["headers"][b"deprecation"] == b"true"
        assert result["headers"][b"sunset"] == sunset_date.encode("latin-1")
        expected_link = f'<{link_url}>; rel="deprecation"'
        assert result["headers"][b"link"] == expected_link.encode("latin-1")

    @pytest.mark.asyncio
    async def test_non_deprecated_route_has_no_deprecation_headers(self) -> None:
        """A non-deprecated route should not have any deprecation headers."""
        app = HawkAPI(openapi_url=None)

        @app.get("/current")
        async def current_endpoint() -> dict[str, str]:
            return {"msg": "current"}

        result = await _call_app(app, "GET", "/current")

        assert result["status"] == 200
        assert b"deprecation" not in result["headers"]
        assert b"sunset" not in result["headers"]
        assert b"link" not in result["headers"]

    @pytest.mark.asyncio
    async def test_deprecated_via_post_decorator(self) -> None:
        """Deprecation headers should work with POST routes too."""
        app = HawkAPI(openapi_url=None)

        @app.post("/old-create", deprecated=True, sunset="Mon, 01 Dec 2025 00:00:00 GMT")
        async def old_create() -> dict[str, str]:
            return {"msg": "created"}

        result = await _call_app(app, "POST", "/old-create")

        assert result["status"] == 201
        assert result["headers"][b"deprecation"] == b"true"
        assert result["headers"][b"sunset"] == b"Mon, 01 Dec 2025 00:00:00 GMT"
