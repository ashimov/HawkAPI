"""Declarative permission/RBAC system for HawkAPI routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from hawkapi.exceptions import HTTPException
from hawkapi.requests.request import Request

PermissionResolver = Callable[[Request], Awaitable[set[str]]]


class PermissionPolicy:
    """Configures how route permissions are checked.

    Usage:
        async def get_user_permissions(request: Request) -> set[str]:
            token = request.headers.get("authorization", "")
            user = await decode_token(token)
            return user.permissions

        app = HawkAPI()
        app.permission_policy = PermissionPolicy(
            resolver=get_user_permissions,
            mode="all",
        )
    """

    __slots__ = ("resolver", "mode", "error_status", "error_detail")

    _VALID_MODES = frozenset({"all", "any"})

    def __init__(
        self,
        resolver: PermissionResolver,
        *,
        mode: str = "all",
        error_status: int = 403,
        error_detail: str = "Insufficient permissions",
    ) -> None:
        """Create a permission policy with a resolver function and check mode."""
        if mode not in self._VALID_MODES:
            msg = f"mode must be 'all' or 'any', got {mode!r}"
            raise ValueError(msg)
        self.resolver = resolver
        self.mode = mode
        self.error_status = error_status
        self.error_detail = error_detail

    async def check(self, request: Request, required: list[str]) -> None:
        """Check if the request has the required permissions.

        Raises HTTPException if the check fails.
        """
        user_perms = await self.resolver(request)

        if self.mode == "all":
            missing = set(required) - user_perms
            if missing:
                raise HTTPException(
                    self.error_status,
                    detail=f"{self.error_detail}. Missing: {', '.join(sorted(missing))}",
                )
        elif self.mode == "any":
            if not set(required).intersection(user_perms):
                raise HTTPException(
                    self.error_status,
                    detail=self.error_detail,
                )
