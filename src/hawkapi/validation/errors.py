"""RFC 9457 Problem Details error formatting."""

from __future__ import annotations

from typing import Any

import msgspec


class ValidationErrorDetail(msgspec.Struct, frozen=True):
    """A single validation error."""

    field: str
    message: str
    value: Any = None


class ProblemDetail(msgspec.Struct, frozen=True):
    """RFC 9457 Problem Details response body."""

    type: str = "about:blank"
    title: str = "Error"
    status: int = 400
    detail: str | None = None
    errors: list[ValidationErrorDetail] | None = None


class RequestValidationError(Exception):
    """Raised when request validation fails."""

    def __init__(
        self,
        errors: list[ValidationErrorDetail],
        *,
        status_code: int = 400,
    ) -> None:
        self.errors = errors
        self.status_code = status_code
        detail = f"{len(errors)} validation error{'s' if len(errors) != 1 else ''}"
        self.detail = detail
        super().__init__(detail)

    def to_problem_detail(self) -> ProblemDetail:
        """Convert this error into an RFC 9457 Problem Details object."""
        return ProblemDetail(
            type="https://hawkapi.ashimov.com/errors/validation",
            title="Validation Error",
            status=self.status_code,
            detail=self.detail,
            errors=self.errors,
        )


def format_msgspec_error(
    exc: msgspec.ValidationError,
    body: Any = None,
) -> list[ValidationErrorDetail]:
    """Convert a msgspec ValidationError into a flat list of error details."""
    msg = str(exc)
    # msgspec errors look like: "Expected `int`, got `str` - at `$.age`"
    # Parse the field path from the error message
    errors: list[ValidationErrorDetail] = []

    if " - at `$." in msg:
        parts = msg.rsplit(" - at `$.", 1)
        message = parts[0].strip()
        field = parts[1].rstrip("`").strip()
        errors.append(ValidationErrorDetail(field=field, message=message))
    elif " - at `$" in msg:
        parts = msg.rsplit(" - at `$", 1)
        message = parts[0].strip()
        field = parts[1].rstrip("`").strip()
        errors.append(ValidationErrorDetail(field=field or "$", message=message))
    else:
        errors.append(ValidationErrorDetail(field="$", message=msg))

    return errors
