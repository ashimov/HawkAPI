"""HawkAPI application — the ASGI entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Callable
from typing import Any

from hawkapi._docs import setup_docs_routes
from hawkapi._health import setup_health_routes
from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.background import BackgroundTasks
from hawkapi.di.container import Container
from hawkapi.di.resolver import resolve_dependencies, resolve_from_plan
from hawkapi.di.scope import Scope as DIScope
from hawkapi.exceptions import HTTPException
from hawkapi.lifespan.hooks import HookRegistry
from hawkapi.lifespan.manager import LifespanManager
from hawkapi.middleware._pipeline import MiddlewareEntry, build_pipeline
from hawkapi.middleware.base import Middleware
from hawkapi.requests.request import Request, RequestEntityTooLarge
from hawkapi.responses.json_response import JSONResponse
from hawkapi.responses.response import Response
from hawkapi.responses.streaming import StreamingResponse
from hawkapi.routing.route import Route
from hawkapi.routing.router import Router
from hawkapi.security.api_key import MissingCredentialError as _MissingCred
from hawkapi.security.scopes import SecurityScopes as _SecurityScopes
from hawkapi.serialization.encoder import encode_response
from hawkapi.validation.errors import (
    ProblemDetail,
    RequestValidationError,
)

logger = logging.getLogger("hawkapi")


class HawkAPI(Router):
    """The main application class. An ASGI 3.0 callable.

    Integrates routing, middleware pipeline, DI container, and lifespan management.
    """

    def __init__(
        self,
        *,
        title: str = "HawkAPI",
        version: str = "0.1.0",
        description: str = "",
        debug: bool = False,
        validation_error_status: int = 400,
        max_body_size: int = 10 * 1024 * 1024,
        prefix: str = "",
        tags: list[str] | None = None,
        container: Container | None = None,
        lifespan: Callable[..., Any] | None = None,
        docs_url: str | None = "/docs",
        redoc_url: str | None = "/redoc",
        scalar_url: str | None = "/scalar",
        openapi_url: str | None = "/openapi.json",
        observability: bool | Any | None = None,
        serverless: bool = False,
        health_url: str | None = "/healthz",
        readyz_url: str | None = "/readyz",
        livez_url: str | None = "/livez",
        request_timeout: float | None = None,
        flags: Any = None,
    ) -> None:
        super().__init__(prefix=prefix, tags=tags)
        self.title = title
        self.version = version
        self.description = description
        self.debug = debug
        self.validation_error_status = validation_error_status
        self.max_body_size = max_body_size
        self.container = container or Container()
        self._exception_handlers: dict[type[Exception], Callable[..., Any]] = {}
        self._middleware_stack: list[MiddlewareEntry] = []
        self._pipeline: ASGIApp | None = None
        self._hooks = HookRegistry()
        self._lifespan_func = lifespan
        self._lifespan_manager = LifespanManager(self._hooks, lifespan)
        self._plugins: list[Any] = []
        self._permission_policy: Any = None
        self._request_timeout = request_timeout
        # Single-threaded asyncio: int += 1 is atomic under GIL.
        # Free-threaded Python 3.13 (no-GIL) would need a lock here and in
        # _core_handler. For now, simple counter for max throughput.
        self._in_flight = 0

        # Observability
        if observability is not None:
            from hawkapi.observability.config import ObservabilityConfig
            from hawkapi.observability.middleware import ObservabilityMiddleware

            if observability is True:
                obs_config = ObservabilityConfig()
            elif isinstance(observability, ObservabilityConfig):
                obs_config = observability
            else:
                obs_config = ObservabilityConfig()
            self._middleware_stack.insert(
                0,
                MiddlewareEntry(cls=ObservabilityMiddleware, kwargs={"config": obs_config}),
            )

        # OpenAPI docs
        self._openapi_url = openapi_url
        self._docs_url = docs_url
        self._redoc_url = redoc_url
        self._scalar_url = scalar_url
        self._openapi_cache: dict[str, dict[str, Any]] = {}

        if serverless:
            self._openapi_url = None
            self._docs_url = None
            self._redoc_url = None
            self._scalar_url = None
        else:
            setup_docs_routes(
                self,
                openapi_url=self._openapi_url,
                docs_url=self._docs_url,
                redoc_url=self._redoc_url,
                scalar_url=self._scalar_url,
            )

        # Health probes
        self._readiness_checks: dict[str, Callable[..., Any]] = {}
        setup_health_routes(
            self,
            health_url=health_url,
            readyz_url=readyz_url,
            livez_url=livez_url,
        )

        # Graceful shutdown: wait for in-flight requests
        self._hooks.on_shutdown(self._wait_for_in_flight)

        # Plugin lifecycle hooks
        self._hooks.on_startup(self._run_plugin_startup)
        self._hooks.on_shutdown(self._run_plugin_shutdown)

        # Feature flags
        if flags is None:
            from hawkapi.flags.providers import StaticFlagProvider  # noqa: PLC0415

            flags = StaticFlagProvider({})
        self.flags = flags

        logger.debug("HawkAPI initialized: %s v%s", title, version)

    # --- OpenAPI ---

    @property
    def permission_policy(self) -> Any:
        """The active permission policy, if any."""
        return self._permission_policy

    @permission_policy.setter
    def permission_policy(self, policy: Any) -> None:
        self._permission_policy = policy

    # --- Plugin API ---

    def add_plugin(self, plugin: Any) -> None:
        """Register a plugin that will receive lifecycle hook callbacks."""
        self._plugins.append(plugin)

    def openapi(self, api_version: str | None = None) -> dict[str, Any]:
        """Generate (or return cached) the OpenAPI schema.

        Pass *api_version* to get a spec filtered to routes of that version.
        """
        from hawkapi.openapi.schema import generate_openapi

        cache_key = api_version or "__all__"
        if cache_key not in self._openapi_cache:
            spec = generate_openapi(
                self._collect_routes(),
                title=self.title,
                version=self.version,
                description=self.description,
                api_version=api_version,
            )
            for plugin in self._plugins:
                spec = plugin.on_schema_generated(spec)
            self._openapi_cache[cache_key] = spec
        import copy

        return copy.deepcopy(self._openapi_cache[cache_key])

    def _invalidate_openapi_cache(self) -> None:
        """Clear cached OpenAPI specs so they regenerate on next access."""
        self._openapi_cache.clear()

    def add_route(self, path: str, handler: Any, **kwargs: Any) -> Route:  # type: ignore[override]
        """Register a route and invalidate cached OpenAPI specs."""
        self._invalidate_openapi_cache()
        route = super().add_route(path, handler, **kwargs)
        for plugin in self._plugins:
            plugin.on_route_registered(route)
        return route

    def include_router(self, router: Router) -> None:
        """Include a sub-router and invalidate cached OpenAPI specs."""
        self._invalidate_openapi_cache()
        super().include_router(router)

    def include_controller(self, controller_class: type) -> None:
        """Include a controller and invalidate cached OpenAPI specs."""
        self._invalidate_openapi_cache()
        super().include_controller(controller_class)

    def mount_graphql(
        self,
        path: str,
        *,
        executor: Any,
        graphiql: bool = True,
        allow_get: bool = True,
        context_factory: Callable[..., Any] | None = None,
    ) -> None:
        """Mount a GraphQL endpoint at *path*.

        Args:
            path: URL path to mount the endpoint (e.g. ``"/graphql"``).
            executor: An async callable implementing ``GraphQLExecutor``.
            graphiql: Serve the GraphiQL UI for browser GET requests (default True).
            allow_get: Allow ``GET ?query=…`` requests (default True).
            context_factory: Optional callable that receives the ``Request`` and
                returns extra context dict (may be async).
        """
        from hawkapi.graphql._handler import make_graphql_handler  # noqa: PLC0415

        _handler = make_graphql_handler(
            executor,
            graphiql=graphiql,
            allow_get=allow_get,
            context_factory=context_factory,
        )

        async def _endpoint(request: Request) -> Any:
            return await _handler(request)

        self.add_route(
            path,
            _endpoint,
            methods={"GET", "POST"},
            include_in_schema=False,
            name=f"graphql:{path}",
        )

    def mount_grpc(
        self,
        servicer: object,
        *,
        add_to_server: Callable[[object, Any], None],
        port: int = 50051,
        host: str = "[::]",
        interceptors: Any = (),
        observability: bool = True,
        reflection: bool = False,
        reflection_service_names: Any = None,
        ssl_credentials: Any = None,
        autostart: bool = True,
        max_workers: int | None = None,
        options: Any = (),
    ) -> Any:
        """Mount a gRPC servicer and tie its lifecycle to ASGI lifespan.

        Args:
            servicer: The servicer object (from ``*_pb2_grpc.py``).
            add_to_server: The generated ``add_XxxServicer_to_server`` function.
            port: TCP port to listen on (default 50051).
            host: Bind address (default ``"[::]"`` = all interfaces).
            interceptors: Additional ``grpc.aio.ServerInterceptor`` instances.
            observability: Install the built-in ``HawkAPIObservabilityInterceptor``
                first (default True).
            reflection: Enable gRPC server reflection (requires ``grpcio-reflection``
                and ``reflection_service_names``).
            reflection_service_names: Fully-qualified service names for reflection.
            ssl_credentials: ``grpc.ServerCredentials`` for TLS; ``None`` = insecure.
            autostart: Start automatically on ASGI lifespan startup (default True).
            max_workers: Reserved for future thread-pool use; currently unused.
            options: Extra ``(key, value)`` channel options for ``grpc.aio.server()``.

        Returns:
            A ``GrpcMount`` with ``.server``, ``.port``, ``.start()``, ``.stop(grace)``.
        """
        from hawkapi.grpc._interceptor import HawkAPIObservabilityInterceptor  # noqa: PLC0415
        from hawkapi.grpc._mount import GrpcMount  # noqa: PLC0415

        # Initialise mount registry on first call and install lifespan hooks once
        if not hasattr(self, "_grpc_mounts"):
            self._grpc_mounts: list[Any] = []
            self._grpc_ports: dict[int, Any] = {}
            self._hooks.on_startup(self._start_grpc_mounts)
            self._hooks.on_shutdown(self._stop_grpc_mounts)

        # Build interceptor list — observability interceptor goes first
        all_interceptors: list[Any] = []
        if observability:
            all_interceptors.append(HawkAPIObservabilityInterceptor(self))
        all_interceptors.extend(interceptors)

        # Same port → reuse existing mount; different port → new mount
        if port in self._grpc_ports:
            mount: Any = self._grpc_ports[port]
            mount._add_servicer(servicer, add_to_server)
        else:
            mount = GrpcMount(
                port=port,
                host=host,
                interceptors=all_interceptors,
                ssl_credentials=ssl_credentials,
                reflection=reflection,
                reflection_service_names=reflection_service_names,
                options=options,
                max_workers=max_workers,
            )
            mount._autostart = autostart
            mount._add_servicer(servicer, add_to_server)
            self._grpc_mounts.append(mount)
            self._grpc_ports[port] = mount

        return mount

    async def _start_grpc_mounts(self) -> None:
        """ASGI startup hook: start all autostart gRPC mounts."""
        for mount in getattr(self, "_grpc_mounts", []):
            if getattr(mount, "_autostart", True):
                await mount._start()

    async def _stop_grpc_mounts(self) -> None:
        """ASGI shutdown hook: stop all gRPC mounts."""
        for mount in getattr(self, "_grpc_mounts", []):
            await mount._stop()

    def readiness_check(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a readiness check (decorator).

        The decorated function must be an async callable returning
        ``(ok: bool, detail: str)``.
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._readiness_checks[name] = func
            return func

        return decorator

    def _collect_routes(self) -> list[Route]:
        """Collect all routes that should appear in the OpenAPI schema."""
        return [r for r in self.routes if r.include_in_schema]

    # --- Middleware API ---

    def add_middleware(
        self,
        middleware_class: type[Middleware],
        **kwargs: Any,
    ) -> None:
        """Add a middleware class to the stack.

        Middleware is applied in order: first added = outermost (runs first).
        """
        self._middleware_stack.append(MiddlewareEntry(cls=middleware_class, kwargs=kwargs))
        # Invalidate pipeline cache
        self._pipeline = None
        # Notify plugins
        for plugin in self._plugins:
            plugin.on_middleware_added(middleware_class, kwargs)

    # --- Lifecycle API ---

    def on_startup(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Register a startup hook (decorator)."""
        self._hooks.on_startup(func)
        return func

    def on_shutdown(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Register a shutdown hook (decorator)."""
        self._hooks.on_shutdown(func)
        return func

    async def _wait_for_in_flight(self, timeout: float = 10.0) -> None:
        """Wait for in-flight requests to complete before shutdown."""
        if self._in_flight <= 0:
            return
        logger.info("Waiting for %d in-flight request(s) to complete...", self._in_flight)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self._in_flight > 0 and loop.time() < deadline:
            await asyncio.sleep(0.1)
        if self._in_flight > 0:
            logger.warning(
                "Shutdown: %d request(s) still in-flight after %.1fs",
                self._in_flight,
                timeout,
            )

    def _run_plugin_startup(self) -> None:
        """Call on_startup() on all registered plugins."""
        for plugin in self._plugins:
            plugin.on_startup()

    def _run_plugin_shutdown(self) -> None:
        """Call on_shutdown() on all registered plugins."""
        for plugin in self._plugins:
            plugin.on_shutdown()

    # --- Exception handlers ---

    def exception_handler(
        self, exc_class: type[Exception]
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a custom exception handler."""

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self._exception_handlers[exc_class] = handler
            return handler

        return decorator

    # --- ASGI entrypoint ---

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 3.0 entrypoint."""
        scope_type = scope["type"]

        if scope_type == "http":
            pipeline = self._get_pipeline()
            await pipeline(scope, receive, send)
        elif scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)
        elif scope_type == "lifespan":
            await self._lifespan_manager.handle(scope, receive, send)

    def _get_pipeline(self) -> ASGIApp:
        """Build (or return cached) the middleware pipeline."""
        if self._pipeline is None:
            self._pipeline = build_pipeline(self._middleware_stack, self._core_handler)
        return self._pipeline

    async def _handle_websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle WebSocket connections."""
        from hawkapi.websocket.connection import WebSocket

        path = scope["path"]
        entry = self._ws_routes.get(path)

        if entry is None:
            # No WebSocket handler registered — consume connect then close
            message = await receive()
            if message["type"] == "websocket.connect":
                await send({"type": "websocket.close", "code": 4004})
            return

        handler, permissions = entry
        ws = WebSocket(dict(scope), receive, send)

        # Wait for the connection request
        message = await receive()
        if message["type"] != "websocket.connect":
            return

        # Check permissions before accepting
        if permissions and self._permission_policy is not None:
            try:
                request = Request(scope, receive, max_body_size=0)
                await self._permission_policy.check(request, permissions)
            except HTTPException:
                await send({"type": "websocket.close", "code": 4003})
                return

        di_scope: DIScope | None = None
        try:
            ws_kwargs, di_scope = await self._resolve_ws_dependencies(handler, ws)
            await handler(**ws_kwargs)
        except Exception:
            logger.exception("WebSocket handler error: %s", path)
            await ws.close(code=1011)
        finally:
            if di_scope is not None:
                try:
                    await di_scope.close()
                except Exception:
                    logger.exception("WebSocket DI scope teardown error")

    async def _resolve_ws_dependencies(
        self, handler: Callable[..., Any], ws: Any
    ) -> tuple[dict[str, Any], DIScope | None]:
        """Resolve dependencies for a WebSocket handler.

        Returns (kwargs, di_scope) where di_scope must be closed by caller.
        """
        from hawkapi.websocket.connection import WebSocket

        sig = inspect.signature(handler)
        hints: dict[str, Any] = {}
        try:
            hints = inspect.get_annotations(handler, eval_str=True)
        except Exception:
            hints = getattr(handler, "__annotations__", {})

        kwargs: dict[str, Any] = {}
        di_scope: DIScope | None = None
        needs_di = False
        for name, param in sig.parameters.items():
            ann = hints.get(name, param.annotation)
            if ann is WebSocket or (ann is inspect.Parameter.empty and not kwargs):
                continue  # handled below
            elif isinstance(ann, type) and self.container.has(ann):
                needs_di = True
                break
            # else: default or ws fallback

        if needs_di:
            di_scope = self.container.scope()
            await di_scope.__aenter__()

        for name, param in sig.parameters.items():
            ann = hints.get(name, param.annotation)
            if ann is WebSocket or (ann is inspect.Parameter.empty and not kwargs):
                kwargs[name] = ws
            elif isinstance(ann, type) and self.container.has(ann) and di_scope is not None:
                kwargs[name] = await di_scope.resolve(ann)
            elif param.default is not inspect.Parameter.empty:
                kwargs[name] = param.default
            else:
                kwargs[name] = ws
        return kwargs, di_scope

    def _make_route_handler(self, result: Any) -> ASGIApp:
        """Create an ASGI app that executes a route (for per-route middleware wrapping)."""
        app_ref = self

        async def _route_app(scope: Scope, receive: Receive, send: Send) -> None:
            # Re-run the route execution logic without middleware
            route = result.route
            plan = route._handler_plan  # pyright: ignore[reportPrivateUsage]
            request = Request(
                scope,
                receive,
                path_params=result.params,
                max_body_size=app_ref.max_body_size,
            )
            await app_ref._execute_route(scope, receive, send, route, plan, request)

        return _route_app

    async def _execute_trivial_route(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        route: Route,
        plan: Any,
        request: Request,
    ) -> None:
        """Minimal hot path for routes with no DI/deps/perms/bg-tasks/deprecation.

        Skips all bookkeeping that _execute_route does. Only safe to call when
        route._trivial is True (guaranteed by _compute_trivial at
        registration time). Handles Request-only and no-arg handlers via the
        pre-computed plan.kwargs_specs via ParamSource.REQUEST detection.
        """
        # Build kwargs from plan — trivial routes have only REQUEST or
        # IMPLICIT_PATH/IMPLICIT_QUERY/PATH params, no DI, no body, no cleanup.
        # Coercion (e.g. int query params) can raise RequestValidationError,
        # so the entire kwargs-build + handler call is inside the try block.
        from hawkapi.di.param_plan import ParamSource  # noqa: PLC0415
        from hawkapi.di.resolver import (
            _coerce_fast,  # noqa: PLC0415  # pyright: ignore[reportPrivateUsage]
        )

        try:
            kwargs: dict[str, Any] = {}
            if plan is not None:
                for spec in plan.params:
                    src = spec.source
                    if src is ParamSource.REQUEST:
                        kwargs[spec.name] = request
                    elif src is ParamSource.PATH or src is ParamSource.IMPLICIT_PATH:
                        value = request.path_params.get(spec.alias or spec.name)
                        if value is None and spec.has_marker_default:
                            mdf = spec.marker_default_factory
                            value = mdf() if mdf is not None else spec.marker_default
                        kwargs[spec.name] = value
                    elif src is ParamSource.QUERY or src is ParamSource.IMPLICIT_QUERY:
                        qval = request.query_params.get(spec.alias or spec.name)
                        if qval is not None:
                            kwargs[spec.name] = _coerce_fast(qval, spec.coerce_type)
                        elif spec.has_marker_default:
                            mdf = spec.marker_default_factory
                            kwargs[spec.name] = mdf() if mdf is not None else spec.marker_default
                        elif spec.has_param_default:
                            kwargs[spec.name] = spec.param_default
                    # BODY, DI, cleanup, bg-tasks cannot appear on trivial routes

            coro = route.handler(**kwargs)
            if self._request_timeout is not None:
                handler_result = await asyncio.wait_for(coro, timeout=self._request_timeout)
            else:
                handler_result = await coro
            response: Response | JSONResponse = self._build_response(
                handler_result,
                route.status_code,
                None,  # response_model is always None on trivial routes
            )
        except TimeoutError:
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/timeout",
                        "title": "Request Timeout",
                        "status": 504,
                        "detail": f"Handler exceeded {self._request_timeout}s timeout",
                    }
                ),
                status_code=504,
                content_type="application/problem+json",
            )
        except RequestValidationError as exc:
            response = self._build_validation_error_response(exc)
        except HTTPException as exc:
            response = exc.to_response()
        except Exception as exc:
            response = await self._handle_exception(request, exc)

        # Minimal HEAD handling: zero out the body but keep content-length.
        # StreamingResponse is not a Response subclass — fall back to the
        # general path if somehow one slips through (guards _trivial calc).
        if isinstance(response, StreamingResponse):
            await self._execute_route(scope, receive, send, route, plan, request)
            return

        if scope["method"] == "HEAD" and hasattr(response, "body"):
            original_len = str(len(response.body))
            response.body = b""
            response._headers["content-length"] = original_len  # pyright: ignore[reportPrivateUsage]

        await response(scope, receive, send)

    async def _execute_route(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        route: Route,
        plan: Any,
        request: Request,
    ) -> None:
        """Execute a resolved route — shared by direct dispatch and per-route middleware."""
        method = scope["method"]
        di_scope: DIScope | None = None
        background_tasks = None
        response: Response | JSONResponse
        cleanup_stack: list[Any] = []
        handler_succeeded = False
        try:
            if route.permissions and self._permission_policy is not None:
                await self._permission_policy.check(request, route.permissions)
            if plan is None or plan.needs_di_scope:
                di_scope = self.container.scope()
                await di_scope.__aenter__()
            security_scopes = _SecurityScopes(scopes=route.required_scopes)
            if plan is not None:
                kwargs, cleanup_stack = await resolve_from_plan(
                    plan, request, di_scope, self.container, security_scopes=security_scopes
                )
            else:
                kwargs, cleanup_stack = await resolve_dependencies(
                    route.handler,
                    request,
                    di_scope,
                    self.container,
                    security_scopes=security_scopes,
                )
            if plan is not None and plan.has_background_tasks and plan.bg_tasks_param_name:
                background_tasks = kwargs.get(plan.bg_tasks_param_name)
            else:
                for _k, v in kwargs.items():
                    if isinstance(v, BackgroundTasks):
                        background_tasks = v
                        break
            # Run side-effect ``dependencies=[Depends(...)]`` before the
            # handler. Return values are discarded; HTTPException short-
            # circuits via the existing try/except below.
            if route.dependencies:
                from hawkapi.di.resolver import (
                    _execute_dep_plan,  # noqa: PLC0415  # pyright: ignore[reportPrivateUsage]
                )

                for dep_plan in route.dependencies:
                    await _execute_dep_plan(
                        dep_plan, request, cleanup_stack, security_scopes=security_scopes
                    )
            if plan is not None:
                is_async = plan.is_async
            else:
                is_async = inspect.iscoroutinefunction(route.handler)
            if is_async:
                coro = route.handler(**kwargs)
                if self._request_timeout is not None:
                    handler_result = await asyncio.wait_for(coro, timeout=self._request_timeout)
                else:
                    handler_result = await coro
            else:
                handler_result = await asyncio.to_thread(route.handler, **kwargs)
            response = self._build_response(
                handler_result,
                route.status_code,
                route.response_model,
                exclude_none=route.response_model_exclude_none,
                exclude_unset=route.response_model_exclude_unset,
                exclude_defaults=route.response_model_exclude_defaults,
            )
            handler_succeeded = True
        except TimeoutError:
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/timeout",
                        "title": "Request Timeout",
                        "status": 504,
                        "detail": f"Handler exceeded {self._request_timeout}s timeout",
                    }
                ),
                status_code=504,
                content_type="application/problem+json",
            )
        except RequestValidationError as exc:
            response = self._build_validation_error_response(exc)
        except _MissingCred as exc:
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/http",
                        "title": "Unauthorized",
                        "status": 401,
                        "detail": exc.detail,
                    }
                ),
                status_code=401,
                headers=exc.headers,
                content_type="application/problem+json",
            )
        except RequestEntityTooLarge as exc:
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/payload-too-large",
                        "title": "Payload Too Large",
                        "status": 413,
                        "detail": str(exc),
                    }
                ),
                status_code=413,
                content_type="application/problem+json",
            )
        except HTTPException as exc:
            response = exc.to_response()
        except Exception as exc:
            response = await self._handle_exception(request, exc)
        finally:
            for gen in reversed(cleanup_stack):
                try:
                    if handler_succeeded:
                        if inspect.isasyncgen(gen):
                            with contextlib.suppress(StopAsyncIteration):
                                await anext(gen)
                        else:
                            with contextlib.suppress(StopIteration):
                                next(gen)
                    else:
                        if inspect.isasyncgen(gen):
                            await gen.aclose()
                        else:
                            gen.close()
                except Exception:
                    logger.exception("Generator dependency cleanup error")

        if method == "HEAD":
            if isinstance(response, StreamingResponse):
                _aclose = getattr(response.body_iterator, "aclose", None)
                if _aclose is not None:
                    await _aclose()
                head_response = Response(
                    status_code=response.status_code,
                    headers=dict(response._headers),  # pyright: ignore[reportPrivateUsage]
                    content_type=response.content_type,
                )
                head_response._headers.pop("content-length", None)  # pyright: ignore[reportPrivateUsage]
                response = head_response
            elif hasattr(response, "body"):
                original_len = str(len(response.body))
                response.body = b""
                response._headers["content-length"] = original_len  # pyright: ignore[reportPrivateUsage]

        if route.deprecated:
            response._headers["deprecation"] = "true"  # pyright: ignore[reportPrivateUsage]
            if route.sunset is not None:
                response._headers["sunset"] = route.sunset  # pyright: ignore[reportPrivateUsage]
            if route.deprecation_link is not None:
                response._headers["link"] = (  # pyright: ignore[reportPrivateUsage]
                    f'<{route.deprecation_link}>; rel="deprecation"'
                )

        try:
            await response(scope, receive, send)
            if background_tasks is not None:
                await background_tasks.run()
        finally:
            if di_scope is not None:
                try:
                    await di_scope.close()
                except ExceptionGroup:
                    logger.exception("DI scope teardown errors")

    async def _core_handler(self, scope: Scope, receive: Receive, send: Send) -> None:
        """The innermost handler: routing + DI + handler execution."""
        self._in_flight += 1
        try:
            await self._core_handler_inner(scope, receive, send)
        finally:
            self._in_flight -= 1

    async def _core_handler_inner(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Inner handler: routing + DI + handler execution."""
        path = scope["path"]
        method = scope["method"]

        # Look up in radix tree
        result = self._tree.lookup(path, method)

        if result is None:
            # Check mounted sub-applications
            for mount_path, mount_app in self._mounts.items():
                if path == mount_path or path.startswith(mount_path + "/"):
                    # Strip the mount prefix for the sub-app
                    sub_path = path[len(mount_path) :] or "/"
                    sub_scope = dict(scope)
                    sub_scope["path"] = sub_path
                    sub_scope["root_path"] = scope.get("root_path", "") + mount_path
                    await mount_app(sub_scope, receive, send)
                    return

            # Check if path exists but method is wrong -> 405
            allowed = self._tree.find_allowed_methods(path)
            if allowed:
                response: Response | JSONResponse = Response(
                    content=encode_response(
                        {
                            "type": "https://hawkapi.ashimov.com/errors/method-not-allowed",
                            "title": "Method Not Allowed",
                            "status": 405,
                            "detail": (
                                f"Method {method} not allowed. "
                                f"Allowed: {', '.join(sorted(allowed))}"
                            ),
                        }
                    ),
                    status_code=405,
                    headers={"allow": ", ".join(sorted(allowed))},
                    content_type="application/problem+json",
                )
            else:
                response = Response(
                    content=encode_response(
                        {
                            "type": "https://hawkapi.ashimov.com/errors/not-found",
                            "title": "Not Found",
                            "status": 404,
                            "detail": f"No route matches {method} {path}",
                        }
                    ),
                    status_code=404,
                    content_type="application/problem+json",
                )
            await response(scope, receive, send)
            return

        route = result.route

        # If route has per-route middleware, build a mini pipeline
        if route.middleware:
            inner = self._make_route_handler(result)
            for mw in reversed(route.middleware):
                if isinstance(mw, tuple):
                    cls, kw = mw
                    inner = cls(inner, **kw)
                else:
                    inner = mw(inner)
            await inner(scope, receive, send)
            return

        plan = route._handler_plan  # pyright: ignore[reportPrivateUsage]
        request = Request(
            scope,
            receive,
            path_params=result.params,
            max_body_size=self.max_body_size,
        )

        # Fast path: trivial routes skip all bookkeeping (DI scope, cleanup
        # stack, background tasks, HEAD special-case, deprecation headers,
        # permissions, timeout wrapping). The flag is computed once at
        # registration time — no per-request isinstance/attribute checks.
        if route._trivial:  # pyright: ignore[reportPrivateUsage]
            await self._execute_trivial_route(scope, receive, send, route, plan, request)
            return

        await self._execute_route(scope, receive, send, route, plan, request)

    def _build_response(
        self,
        result: Any,
        status_code: int,
        response_model: type[Any] | None = None,
        *,
        exclude_none: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
    ) -> Response | JSONResponse:
        """Convert a handler's return value into a Response."""
        if isinstance(result, (Response, JSONResponse)):
            return result
        if result is None:
            return Response(status_code=status_code if status_code != 200 else 204)
        if response_model is not None:
            result = self._apply_response_model(result, response_model)
        if exclude_none or exclude_unset or exclude_defaults:
            from hawkapi.serialization.filters import apply_exclude_filters

            result = apply_exclude_filters(
                result,
                response_model,
                exclude_none=exclude_none,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
            )
        return JSONResponse(result, status_code=status_code)

    @staticmethod
    def _apply_response_model(result: Any, response_model: type[Any]) -> Any:
        """Validate/filter the result through response_model."""
        import msgspec  # type: ignore[import-untyped]

        from hawkapi._compat.pydantic_adapter import is_pydantic_model

        if is_pydantic_model(response_model):
            if isinstance(result, response_model):
                return result
            converted: Any
            if isinstance(result, msgspec.Struct):
                converted = msgspec.to_builtins(result)
            elif isinstance(result, dict):
                converted = result  # pyright: ignore[reportUnknownVariableType]
            else:
                converted = vars(result) if hasattr(result, "__dict__") else result  # pyright: ignore[reportUnknownVariableType]
            return response_model.model_validate(converted)  # pyright: ignore[reportUnknownArgumentType]

        # msgspec path: skip round-trip when already the right type; otherwise
        # convert to builtins and validate through the model. ``isinstance`` is
        # guarded by ``isinstance(response_model, type)`` because parameterized
        # generics like ``list[Item]`` cannot be the second arg of isinstance.
        if isinstance(response_model, type) and isinstance(result, response_model):  # pyright: ignore[reportUnnecessaryIsInstance]
            return result
        return msgspec.convert(msgspec.to_builtins(result), response_model)

    def _build_validation_error_response(self, exc: RequestValidationError) -> JSONResponse:
        """Build a Problem Details response from a validation error."""
        problem = exc.to_problem_detail()
        return JSONResponse(problem, status_code=self.validation_error_status)

    async def _handle_exception(self, request: Request, exc: Exception) -> Response | JSONResponse:
        """Handle an unhandled exception."""
        # Notify plugins first
        for plugin in self._plugins:
            plugin.on_exception(request, exc)

        for exc_class, handler in self._exception_handlers.items():
            if isinstance(exc, exc_class):
                try:
                    result = handler(request, exc)
                    if inspect.isawaitable(result):
                        result = await result
                    if isinstance(result, (Response, JSONResponse)):
                        return result
                    return JSONResponse(result, status_code=500)
                except Exception:
                    logger.exception("Exception in custom exception handler")
                    break

        logger.exception("Unhandled exception: %s %s", request.method, request.path)
        detail = str(exc) if self.debug else "Internal Server Error"
        problem = ProblemDetail(
            type="https://hawkapi.ashimov.com/errors/internal",
            title="Internal Server Error",
            status=500,
            detail=detail,
        )
        return JSONResponse(problem, status_code=500)
