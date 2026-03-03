"""Tests for app.py uncovered branches."""

from __future__ import annotations

from typing import Any

import pytest

from hawkapi import HawkAPI


class TestLifecycleHooks:
    @pytest.mark.asyncio
    async def test_on_startup_decorator(self):
        """Covers app.py lines 190-191: on_startup hook."""
        app = HawkAPI(openapi_url=None)
        started = []

        @app.on_startup
        async def startup():
            started.append(True)

        # Trigger lifespan
        sent: list[dict[str, Any]] = []
        msgs = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive() -> dict[str, Any]:
            return next(msgs)

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
        assert started == [True]

    @pytest.mark.asyncio
    async def test_on_shutdown_decorator(self):
        """Covers app.py lines 195-196: on_shutdown hook."""
        app = HawkAPI(openapi_url=None)
        stopped = []

        @app.on_shutdown
        async def shutdown():
            stopped.append(True)

        sent: list[dict[str, Any]] = []
        msgs = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive() -> dict[str, Any]:
            return next(msgs)

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
        assert stopped == [True]


class TestLifespanScope:
    @pytest.mark.asyncio
    async def test_lifespan_type(self):
        """Covers app.py lines 222-223: lifespan scope type."""
        app = HawkAPI(openapi_url=None)

        sent: list[dict[str, Any]] = []
        msgs = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive() -> dict[str, Any]:
            return next(msgs)

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
        types = [m["type"] for m in sent]
        assert "lifespan.startup.complete" in types
        assert "lifespan.shutdown.complete" in types


class TestExceptionHandlerReturnValue:
    @pytest.mark.asyncio
    async def test_exception_handler_returns_non_response(self):
        """Covers app.py line 452: custom handler returning non-Response (dict)."""
        app = HawkAPI(openapi_url=None)

        @app.exception_handler(ValueError)
        async def handle_value_error(request, exc):
            return {"error": str(exc)}

        @app.get("/fail")
        async def handler() -> dict[str, str]:
            raise ValueError("oops")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/fail",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app(scope, receive, send)
        assert sent[0]["status"] == 500


class TestStreamingResponse:
    @pytest.mark.asyncio
    async def test_streaming_with_custom_content_type_header(self):
        """Covers streaming.py lines 45-48: content-type in headers."""
        from hawkapi.responses.streaming import StreamingResponse

        async def gen():
            yield b"data"

        resp = StreamingResponse(
            gen(),
            headers={"Content-Type": "text/plain"},
        )
        raw = resp._build_raw_headers()
        ct_count = sum(1 for k, _ in raw if k == b"content-type")
        assert ct_count == 1

    @pytest.mark.asyncio
    async def test_streaming_headers_property(self):
        """Covers streaming.py line 39: headers property."""
        from hawkapi.responses.streaming import StreamingResponse

        async def gen():
            yield b"data"

        resp = StreamingResponse(gen(), headers={"X-Custom": "val"})
        assert resp.headers["X-Custom"] == "val"
