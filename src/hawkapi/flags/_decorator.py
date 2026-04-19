"""``@requires_flag`` handler decorator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from hawkapi.exceptions import HTTPException
from hawkapi.flags._di import get_flags
from hawkapi.requests.request import Request

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def requires_flag(key: str, *, status_code: int = 404, default: bool = False) -> Callable[[F], F]:
    """Decorate a handler — responds with *status_code* when the flag is off.

    The decorated handler **must** accept a ``request: Request`` parameter
    (positional or keyword).  If no ``Request`` is found at call time,
    an HTTP 500 is raised immediately (fail-closed).
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request = _find_request(args, kwargs)
            if request is None:
                raise HTTPException(
                    status_code=500,
                    detail="@requires_flag needs a Request param",
                )
            flags = await get_flags(request)
            if not await flags.bool(key, default=default):
                raise HTTPException(
                    status_code=status_code,
                    detail=f"flag {key!r} disabled",
                )
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def _find_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
    for v in args:
        if isinstance(v, Request):
            return v
    for v in kwargs.values():
        if isinstance(v, Request):
            return v
    return None


__all__ = ["requires_flag"]
