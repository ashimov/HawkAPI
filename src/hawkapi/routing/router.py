"""Router with route registration and radix tree dispatching."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hawkapi.middleware.base import Middleware

from hawkapi._types import ASGIApp, RouteHandler
from hawkapi.di.depends import Depends
from hawkapi.di.param_plan import (
    ParamSource,
    build_handler_plan,
    build_side_effect_dep_plans,
    collect_route_scopes,
    extract_path_param_names,
)
from hawkapi.routing._radix_tree import RadixTree
from hawkapi.routing.route import Route

# Parameter sources that the trivial fast path can resolve without any
# extra machinery. Any other source requires the full _execute_route path.
_TRIVIAL_PARAM_SOURCES = frozenset(
    (
        ParamSource.REQUEST,
        ParamSource.PATH,
        ParamSource.IMPLICIT_PATH,
        ParamSource.QUERY,
        ParamSource.IMPLICIT_QUERY,
    )
)


def _compute_is_trivial(
    plan: Any,
    response_model: type[Any] | None,
    permissions: list[str] | None,
    dependencies: tuple[Any, ...],
    deprecated: bool,
    middleware: Any,
    response_model_exclude_none: bool = False,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
) -> bool:
    """Return True when a route qualifies for the zero-overhead fast path.

    A route is trivial when ALL of the following hold at registration time:
    - async handler (plan.is_async)
    - no DI scope needed (not plan.needs_di_scope)
    - no DEPENDS_CALLABLE params (no arbitrary callable injection)
    - no cleanup generator deps
    - no permissions configured
    - no side-effect dependencies
    - no background tasks injected
    - no response_model (handler returns a Response subclass directly)
    - no response_model_exclude_* flags (exclude filters require full path)
    - not deprecated
    - no per-route middleware
    - all param sources are in _TRIVIAL_PARAM_SOURCES
    The fast path in _core_handler_inner then skips all the bookkeeping that
    only matters when these features are in use.
    """
    if plan is None:
        return False
    if not plan.is_async:
        return False
    if plan.needs_di_scope:
        return False
    if plan.has_cleanup_deps:
        return False
    if plan.has_background_tasks:
        return False
    if permissions:
        return False
    if dependencies:
        return False
    if response_model is not None:
        return False
    if response_model_exclude_none or response_model_exclude_unset or response_model_exclude_defaults:  # noqa: E501
        return False
    if deprecated:
        return False
    if middleware:
        return False
    # Verify every param can be resolved by the trivial path
    return all(spec.source in _TRIVIAL_PARAM_SOURCES for spec in plan.params)


def _infer_response_model(handler: Any) -> type[Any] | None:
    """Return the handler's return annotation as a ``response_model``, or None.

    Inclusion rules (see ``docs/plans/2026-04-18-tier3-typed-routes-design.md``):
    structured types only — msgspec Structs, Pydantic models, parameterized
    generics, unions with None. Primitives, bare containers, ``Response``
    subclasses, ``None`` / ``Any`` / absent annotation all fall through.
    """
    from typing import Any as _Any  # noqa: PLC0415
    from typing import get_type_hints  # noqa: PLC0415

    # Build localns from the handler's closure so `from __future__ import
    # annotations` still resolves nested types (tests often define models
    # inside a test function and rely on closure capture).
    localns: dict[str, object] | None = None
    closure = getattr(handler, "__closure__", None)
    freevars = getattr(getattr(handler, "__code__", None), "co_freevars", ())
    if closure and freevars:
        localns = {name: cell.cell_contents for name, cell in zip(freevars, closure, strict=False)}
    try:
        hints = get_type_hints(handler, localns=localns, include_extras=False)
    except Exception:
        return None
    ret = hints.get("return", None)
    if ret is None or ret is type(None) or ret is _Any:
        return None
    # HawkAPI's response classes don't share a single base; enumerate them.
    from hawkapi.responses import (  # noqa: PLC0415
        FileResponse,
        HTMLResponse,
        JSONResponse,
        PlainTextResponse,
        RedirectResponse,
        StreamingResponse,
    )
    from hawkapi.responses.response import Response  # noqa: PLC0415

    _response_classes = (
        Response,
        JSONResponse,
        HTMLResponse,
        PlainTextResponse,
        RedirectResponse,
        FileResponse,
        StreamingResponse,
    )
    if isinstance(ret, type) and any(issubclass(ret, c) for c in _response_classes):
        return None
    if ret in (str, int, float, bool, bytes):
        return None
    if ret in (dict, list, tuple, set, frozenset):
        return None
    return ret


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

        # Auto-infer response_model from the handler's return annotation when
        # the caller did not pass one explicitly.
        if response_model is None:
            response_model = _infer_response_model(handler)

        # Router-level deps run before route-level deps.
        merged_deps = self._dependencies + (tuple(dependencies) if dependencies else ())
        dep_plans = build_side_effect_dep_plans(merged_deps)
        required_scopes = collect_route_scopes(list(merged_deps), handler)

        mw_tuple = tuple(middleware) if middleware else None
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
            middleware=mw_tuple,
            dependencies=dep_plans,
            required_scopes=required_scopes,
            _handler_plan=plan,
            _is_trivial=_compute_is_trivial(
                plan,
                response_model,
                permissions,
                dep_plans,
                deprecated,
                mw_tuple,
                response_model_exclude_none=response_model_exclude_none,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
            ),
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
            merged_required = tuple(
                sorted(
                    set(collect_route_scopes(list(self._dependencies))) | set(route.required_scopes)
                )
            )
            merged_deps = parent_dep_plans + route.dependencies
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
                dependencies=merged_deps,
                required_scopes=merged_required,
                _handler_plan=plan,
                _is_trivial=_compute_is_trivial(
                    plan,
                    route.response_model,
                    route.permissions,
                    merged_deps,
                    route.deprecated,
                    route.middleware,
                    response_model_exclude_none=route.response_model_exclude_none,
                    response_model_exclude_unset=route.response_model_exclude_unset,
                    response_model_exclude_defaults=route.response_model_exclude_defaults,
                ),
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
