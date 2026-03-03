"""Tests for ErrorHandlerMiddleware."""

import pytest

from hawkapi.middleware.error_handler import ErrorHandlerMiddleware
from hawkapi.validation.errors import RequestValidationError, ValidationErrorDetail


def _make_scope(path="/"):
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("localhost", 8000),
    }


async def _collect(app, scope=None):
    msgs = []
    scope = scope or _make_scope()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        msgs.append(msg)

    await app(scope, receive, send)
    return msgs


async def test_passthrough_on_success():
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = ErrorHandlerMiddleware(inner)
    msgs = await _collect(app)
    assert msgs[0]["status"] == 200


async def test_catches_unhandled_exception():
    async def inner(scope, receive, send):
        raise RuntimeError("boom")

    app = ErrorHandlerMiddleware(inner)
    msgs = await _collect(app)
    assert msgs[0]["status"] == 500
    body = msgs[1]["body"]
    assert b"Internal Server Error" in body


async def test_debug_mode_shows_traceback():
    async def inner(scope, receive, send):
        raise ValueError("debug error")

    app = ErrorHandlerMiddleware(inner, debug=True)
    msgs = await _collect(app)
    assert msgs[0]["status"] == 500
    body = msgs[1]["body"]
    assert b"debug error" in body
    assert b"ValueError" in body


async def test_catches_validation_error():
    async def inner(scope, receive, send):
        raise RequestValidationError(
            [
                ValidationErrorDetail(field="name", message="required"),
            ]
        )

    app = ErrorHandlerMiddleware(inner)
    msgs = await _collect(app)
    assert msgs[0]["status"] == 400
    body = msgs[1]["body"]
    assert b"Validation Error" in body


async def test_reraises_if_response_started():
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("late error")

    app = ErrorHandlerMiddleware(inner)
    with pytest.raises(RuntimeError, match="late error"):
        await _collect(app)


async def test_non_http_passthrough():
    async def inner(scope, receive, send):
        await send({"type": "lifespan.startup.complete"})

    app = ErrorHandlerMiddleware(inner)
    scope = {"type": "lifespan", "asgi": {"version": "3.0"}}
    msgs = await _collect(app, scope)
    assert msgs[0]["type"] == "lifespan.startup.complete"
