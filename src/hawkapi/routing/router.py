"""Router with route registration and radix tree dispatching."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hawkapi.middleware.base import Middleware

from hawkapi._types import ASGIApp, RouteHandler
from hawkapi.di.depends import Depends
from hawkapi.di.param_plan import (
    build_handler_plan,
    build_side_effect_dep_plans,
    extract_path_param_names,
)
from hawkapi.routing._radix_tree import RadixTree
from hawkapi.routing.route import Route


class Router:
    """Collects routes and mounts into the application."""

    def __init__(
        self,
        *,
        prefix: str = "",
        tags: list[str] | None = None,
        dependencies: list[Depends] | None = None,
    ) -> None:
        self.prefix = prefix.rstrip("/")
        self.tags = tags or []
        self._dependencies: tuple[Depends, ...] = tuple(dependencies) if dependencies else ()
        self._tree = RadixTree()
        self._ws_routes: dict[str, tuple[RouteHandler, list[str] | None]] = {}
        self._sub_routers: list[Router] = []
        self._mounts: dict[str, ASGIApp] = {}

    @property
    def routes(self) -> list[Route]:
        """All registered routes."""
        return self._tree.routes

    @property
    def tree(self) -> RadixTree:
        """The underlying radix tree used for route matching."""
        return self._tree

    def add_route(
        self,
        path: str,
        handler: RouteHandler,
        *,
        methods: set[str] | frozenset[str],
        name: str | None = None,
        status_code: int = 200,
        response_model: type[Any] | None = None,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        include_in_schema: bool = True,
        deprecated: bool = False,
        sunset: str | None = None,
        deprecation_link: str | None = None,
        version: str | None = None,
        permissions: list[str] | None = None,
        middleware: list[type[Middleware] | tuple[type[Middleware], dict[str, Any]]] | None = None,
        dependencies: list[Depends] | None = None,
    ) -> Route:
        """Register a route directly."""
        full_path = self.prefix + ("/" + path.strip("/") if path.strip("/") else "") or "/"
        if version:
            full_path = "/" + version.strip("/") + full_path
        merged_tags = self.tags + (tags or [])

        path_param_names = extract_path_param_names(full_path)
        container = getattr(self, "container", None)
        plan = build_handler_plan(handler, container=container, path_params=path_param_names)

        # Router-level deps run before route-level deps.
        merged_deps = self._dependencies + (tuple(dependencies) if dependencies else ())
        dep_plans = build_side_effect_dep_plans(merged_deps)

        route = Route(
            path=full_path,
            handler=handler,
            methods=frozenset(methods),
            name=name or handler.__name__,
            status_code=status_code,
            response_model=response_model,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            tags=merged_tags,
            summary=summary or _extract_summary(handler),
            description=description,
            include_in_schema=include_in_schema,
            deprecated=deprecated,
            sunset=sunset,
            deprecation_link=deprecation_link,
            version=version,
            permissions=permissions,
            middleware=tuple(middleware) if middleware else None,
            dependencies=dep_plans,
            _handler_plan=plan,
        )
        self._tree.insert(route)
        return route

    def _route_decorator(
        self,
        path: str,
        *,
        methods: set[str],
        status_code: int = 200,
        response_model: type[Any] | None = None,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        name: str | None = None,
        include_in_schema: bool = True,
        deprecated: bool = False,
        sunset: str | None = None,
        deprecation_link: str | None = None,
        version: str | None = None,
        permissions: list[str] | None = None,
        middleware: list[type[Middleware] | tuple[type[Middleware], dict[str, Any]]] | None = None,
        dependencies: list[Depends] | None = None,
    ) -> Callable[[RouteHandler], RouteHandler]:
        def decorator(handler: RouteHandler) -> RouteHandler:
            self.add_route(
                path,
                handler,
                methods=methods,
                name=name,
                status_code=status_code,
                response_model=response_model,
                response_model_exclude_none=response_model_exclude_none,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                tags=tags,
                summary=summary,
                description=description,
                include_in_schema=include_in_schema,
                deprecated=deprecated,
                sunset=sunset,
                deprecation_link=deprecation_link,
                version=version,
                permissions=permissions,
                middleware=middleware,
                dependencies=dependencies,
            )
            return handler

        return decorator

    def get(
        self,
        path: str,
        *,
        status_code: int = 200,
        response_model: type[Any] | None = None,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        name: str | None = None,
        include_in_schema: bool = True,
        deprecated: bool = False,
        sunset: str | None = None,
        deprecation_link: str | None = None,
        version: str | None = None,
        permissions: list[str] | None = None,
        middleware: list[type[Middleware] | tuple[type[Middleware], dict[str, Any]]] | None = None,
        dependencies: list[Depends] | None = None,
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a GET route handler."""
        return self._route_decorator(
            path,
            methods={"GET", "HEAD"},
            status_code=status_code,
            response_model=response_model,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            tags=tags,
            summary=summary,
            description=description,
            name=name,
            include_in_schema=include_in_schema,
            deprecated=deprecated,
            sunset=sunset,
            deprecation_link=deprecation_link,
            version=version,
            permissions=permissions,
            middleware=middleware,
            dependencies=dependencies,
        )

    def post(
        self,
        path: str,
        *,
        status_code: int = 201,
        response_model: type[Any] | None = None,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        name: str | None = None,
        include_in_schema: bool = True,
        deprecated: bool = False,
        sunset: str | None = None,
        deprecation_link: str | None = None,
        version: str | None = None,
        permissions: list[str] | None = None,
        middleware: list[type[Middleware] | tuple[type[Middleware], dict[str, Any]]] | None = None,
        dependencies: list[Depends] | None = None,
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a POST route handler."""
        return self._route_decorator(
            path,
            methods={"POST"},
            status_code=status_code,
            response_model=response_model,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            tags=tags,
            summary=summary,
            description=description,
            name=name,
            include_in_schema=include_in_schema,
            deprecated=deprecated,
            sunset=sunset,
            deprecation_link=deprecation_link,
            version=version,
            permissions=permissions,
            middleware=middleware,
            dependencies=dependencies,
        )

    def put(
        self,
        path: str,
        *,
        status_code: int = 200,
        response_model: type[Any] | None = None,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        name: str | None = None,
        include_in_schema: bool = True,
        deprecated: bool = False,
        sunset: str | None = None,
        deprecation_link: str | None = None,
        version: str | None = None,
        permissions: list[str] | None = None,
        middleware: list[type[Middleware] | tuple[type[Middleware], dict[str, Any]]] | None = None,
        dependencies: list[Depends] | None = None,
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a PUT route handler."""
        return self._route_decorator(
            path,
            methods={"PUT"},
            status_code=status_code,
            response_model=response_model,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            tags=tags,
            summary=summary,
            description=description,
            name=name,
            include_in_schema=include_in_schema,
            deprecated=deprecated,
            sunset=sunset,
            deprecation_link=deprecation_link,
            version=version,
            permissions=permissions,
            middleware=middleware,
            dependencies=dependencies,
        )

    def patch(
        self,
        path: str,
        *,
        status_code: int = 200,
        response_model: type[Any] | None = None,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        name: str | None = None,
        include_in_schema: bool = True,
        deprecated: bool = False,
        sunset: str | None = None,
        deprecation_link: str | None = None,
        version: str | None = None,
        permissions: list[str] | None = None,
        middleware: list[type[Middleware] | tuple[type[Middleware], dict[str, Any]]] | None = None,
        dependencies: list[Depends] | None = None,
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a PATCH route handler."""
        return self._route_decorator(
            path,
            methods={"PATCH"},
            status_code=status_code,
            response_model=response_model,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            tags=tags,
            summary=summary,
            description=description,
            name=name,
            include_in_schema=include_in_schema,
            deprecated=deprecated,
            sunset=sunset,
            deprecation_link=deprecation_link,
            version=version,
            permissions=permissions,
            middleware=middleware,
            dependencies=dependencies,
        )

    def delete(
        self,
        path: str,
        *,
        status_code: int = 204,
        response_model: type[Any] | None = None,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        name: str | None = None,
        include_in_schema: bool = True,
        deprecated: bool = False,
        sunset: str | None = None,
        deprecation_link: str | None = None,
        version: str | None = None,
        permissions: list[str] | None = None,
        middleware: list[type[Middleware] | tuple[type[Middleware], dict[str, Any]]] | None = None,
        dependencies: list[Depends] | None = None,
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a DELETE route handler."""
        return self._route_decorator(
            path,
            methods={"DELETE"},
            status_code=status_code,
            response_model=response_model,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            tags=tags,
            summary=summary,
            description=description,
            name=name,
            include_in_schema=include_in_schema,
            deprecated=deprecated,
            sunset=sunset,
            deprecation_link=deprecation_link,
            version=version,
            permissions=permissions,
            middleware=middleware,
            dependencies=dependencies,
        )

    def websocket(
        self,
        path: str,
        *,
        name: str | None = None,
        permissions: list[str] | None = None,
    ) -> Callable[[RouteHandler], RouteHandler]:
        """Register a WebSocket handler."""

        def decorator(handler: RouteHandler) -> RouteHandler:
            full_path = self.prefix + ("/" + path.strip("/") if path.strip("/") else "") or "/"
            self._ws_routes[full_path] = (handler, permissions)
            return handler

        return decorator

    def mount(self, path: str, app: ASGIApp) -> None:
        """Mount a sub-application (e.g., StaticFiles) at the given path.

        Usage:
            app.mount("/static", StaticFiles(directory="static"))
        """
        mount_path = self.prefix + "/" + path.strip("/")
        self._mounts[mount_path] = app

    def include_router(self, router: Router) -> None:
        """Mount a sub-router. Its routes are merged into this router's tree."""
        container = getattr(self, "container", None)
        for route in router.routes:
            # Prepend our prefix to the sub-router's route paths
            full_path = self.prefix + route.path
            merged_tags = self.tags + route.tags

            # Rebuild plan with container if the sub-router didn't have one
            plan = route._handler_plan  # pyright: ignore[reportPrivateUsage]
            if container is not None and plan is not None and not plan.needs_di_scope:
                pp_names = extract_path_param_names(full_path)
                plan = build_handler_plan(
                    route.handler,
                    container=container,
                    path_params=pp_names,
                )

            # Parent router's side-effect deps are prepended to each merged
            # sub-route's existing dep chain (parent outer → child inner).
            parent_dep_plans = build_side_effect_dep_plans(self._dependencies)
            merged_route = Route(
                path=full_path,
                handler=route.handler,
                methods=route.methods,
                name=route.name,
                status_code=route.status_code,
                response_model=route.response_model,
                tags=merged_tags,
                summary=route.summary,
                description=route.description,
                include_in_schema=route.include_in_schema,
                deprecated=route.deprecated,
                sunset=route.sunset,
                deprecation_link=route.deprecation_link,
                version=route.version,
                permissions=route.permissions,
                middleware=route.middleware,
                dependencies=parent_dep_plans + route.dependencies,
                _handler_plan=plan,
            )
            self._tree.insert(merged_route)

        # Merge WebSocket routes
        for ws_path, ws_entry in router._ws_routes.items():
            full_ws_path = self.prefix + ws_path
            self._ws_routes[full_ws_path] = ws_entry

        # Merge mounts
        for mount_path, mount_app in router._mounts.items():
            full_mount_path = self.prefix + mount_path
            self._mounts[full_mount_path] = mount_app

        self._sub_routers.append(router)

    def include_controller(self, controller_class: type) -> None:
        """Mount a class-based controller.

        Collects all decorated methods and registers them as routes.
        """
        from hawkapi.routing.controllers import Controller

        if not (
            isinstance(controller_class, type)  # pyright: ignore[reportUnnecessaryIsInstance]
            and issubclass(controller_class, Controller)
        ):
            raise TypeError(f"{controller_class} is not a Controller subclass")

        ctrl_prefix = controller_class.prefix.rstrip("/")
        ctrl_tags = controller_class.tags

        for info, bound_method in controller_class.collect_routes():
            path = ctrl_prefix + info.path
            tags = (info.tags or []) + ctrl_tags

            self.add_route(
                path,
                bound_method,
                methods=info.methods,
                name=info.name,
                status_code=info.status_code,
                tags=tags if tags else None,
                summary=info.summary,
                description=info.description,
                version=info.version,
                permissions=info.permissions,
            )


def _extract_summary(handler: RouteHandler) -> str | None:
    """Extract the first line of a docstring as summary."""
    doc = getattr(handler, "__doc__", None)
    if doc:
        first_line = doc.strip().split("\n")[0].strip()
        return first_line if first_line else None
    return None
