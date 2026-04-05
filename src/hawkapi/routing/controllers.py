"""Class-based controllers — group related endpoints in a class.

Usage:
    class UserController(Controller):
        prefix = "/users"
        tags = ["users"]

        @get("/")
        async def list_users(self) -> list[dict]:
            return [{"id": 1, "name": "Alice"}]

        @get("/{user_id:int}")
        async def get_user(self, user_id: int) -> dict:
            return {"id": user_id, "name": "Alice"}

        @post("/")
        async def create_user(self, body: CreateUser) -> dict:
            return {"id": 1, **vars(body)}

    app.include_controller(UserController)
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

_ROUTE_ATTR = "__hawk_route__"


class _RouteInfo:
    """Stores route metadata on a method."""

    __slots__ = (
        "path",
        "methods",
        "status_code",
        "name",
        "tags",
        "summary",
        "description",
        "version",
        "permissions",
    )

    def __init__(
        self,
        path: str,
        methods: set[str],
        status_code: int,
        name: str | None,
        tags: list[str] | None,
        summary: str | None,
        description: str | None,
        version: str | None = None,
        permissions: list[str] | None = None,
    ) -> None:
        self.path = path
        self.methods = methods
        self.status_code = status_code
        self.name = name
        self.tags = tags
        self.summary = summary
        self.description = description
        self.version = version
        self.permissions = permissions


def _method_decorator(
    path: str,
    *,
    methods: set[str],
    status_code: int = 200,
    name: str | None = None,
    tags: list[str] | None = None,
    summary: str | None = None,
    description: str | None = None,
    version: str | None = None,
    permissions: list[str] | None = None,
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(
            func,
            _ROUTE_ATTR,
            _RouteInfo(
                path, methods, status_code, name, tags, summary, description, version, permissions
            ),
        )
        return func

    return decorator


def get(
    path: str,
    *,
    status_code: int = 200,
    name: str | None = None,
    tags: list[str] | None = None,
    summary: str | None = None,
    description: str | None = None,
    version: str | None = None,
    permissions: list[str] | None = None,
) -> Callable[..., Any]:
    """Mark a controller method as a GET handler."""
    return _method_decorator(
        path,
        methods={"GET", "HEAD"},
        status_code=status_code,
        name=name,
        tags=tags,
        summary=summary,
        description=description,
        version=version,
        permissions=permissions,
    )


def post(
    path: str,
    *,
    status_code: int = 201,
    name: str | None = None,
    tags: list[str] | None = None,
    summary: str | None = None,
    description: str | None = None,
    version: str | None = None,
    permissions: list[str] | None = None,
) -> Callable[..., Any]:
    """Mark a controller method as a POST handler."""
    return _method_decorator(
        path,
        methods={"POST"},
        status_code=status_code,
        name=name,
        tags=tags,
        summary=summary,
        description=description,
        version=version,
        permissions=permissions,
    )


def put(
    path: str,
    *,
    status_code: int = 200,
    name: str | None = None,
    tags: list[str] | None = None,
    summary: str | None = None,
    description: str | None = None,
    version: str | None = None,
    permissions: list[str] | None = None,
) -> Callable[..., Any]:
    """Mark a controller method as a PUT handler."""
    return _method_decorator(
        path,
        methods={"PUT"},
        status_code=status_code,
        name=name,
        tags=tags,
        summary=summary,
        description=description,
        version=version,
        permissions=permissions,
    )


def patch(
    path: str,
    *,
    status_code: int = 200,
    name: str | None = None,
    tags: list[str] | None = None,
    summary: str | None = None,
    description: str | None = None,
    version: str | None = None,
    permissions: list[str] | None = None,
) -> Callable[..., Any]:
    """Mark a controller method as a PATCH handler."""
    return _method_decorator(
        path,
        methods={"PATCH"},
        status_code=status_code,
        name=name,
        tags=tags,
        summary=summary,
        description=description,
        version=version,
        permissions=permissions,
    )


def delete(
    path: str,
    *,
    status_code: int = 204,
    name: str | None = None,
    tags: list[str] | None = None,
    summary: str | None = None,
    description: str | None = None,
    version: str | None = None,
    permissions: list[str] | None = None,
) -> Callable[..., Any]:
    """Mark a controller method as a DELETE handler."""
    return _method_decorator(
        path,
        methods={"DELETE"},
        status_code=status_code,
        name=name,
        tags=tags,
        summary=summary,
        description=description,
        version=version,
        permissions=permissions,
    )


class Controller:
    """Base class for class-based controllers.

    Subclass attributes:
        prefix: URL prefix for all routes in this controller
        tags: Default tags for all routes
    """

    prefix: str = ""
    tags: list[str] = []

    @classmethod
    def collect_routes(cls) -> list[tuple[_RouteInfo, Callable[..., Any]]]:
        """Collect all decorated methods from this controller.

        A fresh controller instance is created per request to avoid shared
        mutable state between concurrent requests.
        """
        routes: list[tuple[_RouteInfo, Callable[..., Any]]] = []
        for name in dir(cls):
            if name.startswith("_"):
                continue
            method = getattr(cls, name, None)
            if method is None:
                continue
            info = getattr(method, _ROUTE_ATTR, None)
            if info is None:
                continue
            # Create a wrapper that instantiates the controller per-request
            _method_name = name

            def make_handler(m_name: str) -> Callable[..., Any]:
                async def handler(**kwargs: Any) -> Any:
                    instance = cls()
                    bound = getattr(instance, m_name)
                    result = bound(**kwargs)
                    if inspect.isawaitable(result):
                        return await result
                    return result

                # Preserve the original method's signature for DI resolution
                original = getattr(cls, m_name)
                functools.update_wrapper(handler, original)
                # Fix annotations: strip 'self' from the signature
                sig = inspect.signature(original)
                params = [p for n, p in sig.parameters.items() if n != "self"]
                handler.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]
                # Copy annotations without 'self'
                anns = getattr(original, "__annotations__", {})
                handler.__annotations__ = {k: v for k, v in anns.items() if k != "self"}
                return handler

            routes.append((info, make_handler(_method_name)))
        return routes
