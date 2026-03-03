"""Global error handler middleware.

Catches unhandled exceptions and returns RFC 9457 Problem Details responses.
"""

from __future__ import annotations

import traceback
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.responses.json_response import JSONResponse
from hawkapi.validation.errors import ProblemDetail, RequestValidationError


class ErrorHandlerMiddleware(Middleware):
    """Catch exceptions and return structured error responses."""

    def __init__(self, app: ASGIApp, *, debug: bool = False) -> None:
        super().__init__(app)
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False
        original_send = send

        async def guarded_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await original_send(message)

        try:
            await self.app(scope, receive, guarded_send)
        except RequestValidationError as exc:
            if response_started:
                raise
            problem = exc.to_problem_detail()
            response = JSONResponse(problem, status_code=exc.status_code)
            await response(scope, receive, send)
        except Exception as exc:
            if response_started:
                raise
            detail: str | None = None
            if self.debug:
                detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            else:
                detail = "Internal Server Error"

            problem = ProblemDetail(
                type="https://hawkapi.ashimov.com/errors/internal",
                title="Internal Server Error",
                status=500,
                detail=detail,
            )
            response = JSONResponse(problem, status_code=500)
            await response(scope, receive, send)
