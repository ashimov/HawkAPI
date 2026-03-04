"""HawkAPI application — the ASGI entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Callable
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.background import BackgroundTasks
from hawkapi.di.container import Container
from hawkapi.di.resolver import resolve_dependencies, resolve_from_plan
from hawkapi.di.scope import Scope as DIScope
from hawkapi.exceptions import HTTPException
from hawkapi.lifespan.hooks import HookRegistry
from hawkapi.lifespan.manager import LifespanManager
from hawkapi.middleware._pipeline import build_pipeline
from hawkapi.middleware.base import Middleware
from hawkapi.requests.request import Request, RequestEntityTooLarge
from hawkapi.responses.json_response import JSONResponse
from hawkapi.responses.response import Response
from hawkapi.responses.streaming import StreamingResponse
from hawkapi.routing.route import Route
from hawkapi.routing.router import Router
from hawkapi.security.api_key import MissingCredentialError as _MissingCred
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
        self._middleware_stack: list[
            type[Middleware] | tuple[type[Middleware], dict[str, Any]]
        ] = []
        self._pipeline: ASGIApp | None = None
        self._hooks = HookRegistry()
        self._lifespan_func = lifespan
        self._lifespan_manager = LifespanManager(self._hooks, lifespan)
        self._permission_policy: Any = None
        self._request_timeout = request_timeout
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
            self._middleware_stack.insert(0, (ObservabilityMiddleware, {"config": obs_config}))

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
            self._setup_docs_routes()

        # Health check endpoint
        if health_url is not None:
            self._setup_health_route(health_url)

        # Health probes
        self._readiness_checks: dict[str, Callable[..., Any]] = {}
        if readyz_url is not None:
            self._setup_readyz_route(readyz_url)
        if livez_url is not None:
            self._setup_livez_route(livez_url)

        # Graceful shutdown: wait for in-flight requests
        self._hooks.on_shutdown(self._wait_for_in_flight)

        logger.debug("HawkAPI initialized: %s v%s", title, version)

    # --- OpenAPI ---

    @property
    def permission_policy(self) -> Any:
        """The active permission policy, if any."""
        return self._permission_policy

    @permission_policy.setter
    def permission_policy(self, policy: Any) -> None:
        self._permission_policy = policy

    def openapi(self, api_version: str | None = None) -> dict[str, Any]:
        """Generate (or return cached) the OpenAPI schema.

        Pass *api_version* to get a spec filtered to routes of that version.
        """
        from hawkapi.openapi.schema import generate_openapi

        cache_key = api_version or "__all__"
        if cache_key not in self._openapi_cache:
            self._openapi_cache[cache_key] = generate_openapi(
                self._collect_routes(),
                title=self.title,
                version=self.version,
                description=self.description,
                api_version=api_version,
            )
        import copy

        return copy.deepcopy(self._openapi_cache[cache_key])

    def _invalidate_openapi_cache(self) -> None:
        """Clear cached OpenAPI specs so they regenerate on next access."""
        self._openapi_cache.clear()

    def add_route(self, path: str, handler: Any, **kwargs: Any) -> Route:  # type: ignore[override]
        """Register a route and invalidate cached OpenAPI specs."""
        self._invalidate_openapi_cache()
        return super().add_route(path, handler, **kwargs)

    def include_router(self, router: Router) -> None:
        """Include a sub-router and invalidate cached OpenAPI specs."""
        self._invalidate_openapi_cache()
        super().include_router(router)

    def include_controller(self, controller_class: type) -> None:
        """Include a controller and invalidate cached OpenAPI specs."""
        self._invalidate_openapi_cache()
        super().include_controller(controller_class)

    def _setup_docs_routes(self) -> None:
        """Register OpenAPI documentation routes."""
        if self._openapi_url is None:
            return

        openapi_url = self._openapi_url

        @self.get(openapi_url, include_in_schema=False)
        async def openapi_schema(request: Request) -> dict[str, Any]:
            spec = self.openapi()
            root_path = request.scope.get("root_path", "")
            if root_path:
                spec = {**spec, "servers": [{"url": root_path}]}
            return spec

        _ = openapi_schema  # registered via decorator

        if self._docs_url is not None:
            docs_url = self._docs_url

            @self.get(docs_url, include_in_schema=False)
            async def swagger_ui(request: Request) -> Response:
                from hawkapi.openapi.ui import get_swagger_ui_html

                root_path = request.scope.get("root_path", "")
                html = get_swagger_ui_html(self.title, root_path + openapi_url)
                return Response(
                    content=html.encode(),
                    status_code=200,
                    content_type="text/html; charset=utf-8",
                )

            _ = swagger_ui  # registered via decorator

        if self._redoc_url is not None:
            redoc_url = self._redoc_url

            @self.get(redoc_url, include_in_schema=False)
            async def redoc_ui(request: Request) -> Response:
                from hawkapi.openapi.ui import get_redoc_html

                root_path = request.scope.get("root_path", "")
                html = get_redoc_html(self.title, root_path + openapi_url)
                return Response(
                    content=html.encode(),
                    status_code=200,
                    content_type="text/html; charset=utf-8",
                )

            _ = redoc_ui  # registered via decorator

        if self._scalar_url is not None:
            scalar_url = self._scalar_url

            @self.get(scalar_url, include_in_schema=False)
            async def scalar_ui(request: Request) -> Response:
                from hawkapi.openapi.ui import get_scalar_ui_html

                root_path = request.scope.get("root_path", "")
                html = get_scalar_ui_html(self.title, root_path + openapi_url)
                return Response(
                    content=html.encode(),
                    status_code=200,
                    content_type="text/html; charset=utf-8",
                )

            _ = scalar_ui  # registered via decorator

    def _setup_health_route(self, health_url: str) -> None:
        """Register a lightweight health check endpoint."""

        @self.get(health_url, include_in_schema=False)
        async def healthz(request: Request) -> dict[str, str]:
            return {"status": "ok"}

        _ = healthz

    def _setup_livez_route(self, livez_url: str) -> None:
        """Register the liveness probe endpoint."""

        @self.get(livez_url, include_in_schema=False)
        async def livez(request: Request) -> dict[str, str]:
            return {"status": "alive"}

        _ = livez

    def _setup_readyz_route(self, readyz_url: str) -> None:
        """Register the readiness probe endpoint."""

        @self.get(readyz_url, include_in_schema=False)
        async def readyz(request: Request) -> Response:
            checks: dict[str, dict[str, Any]] = {}
            all_ok = True
            for name, check_fn in self._readiness_checks.items():
                ok, detail = await check_fn()
                checks[name] = {"ok": ok, "detail": detail}
                if not ok:
                    all_ok = False
            status = "ready" if all_ok else "not_ready"
            status_code = 200 if all_ok else 503
            body = encode_response({"status": status, "checks": checks})
            return Response(
                content=body,
                status_code=status_code,
                content_type="application/json",
            )

        _ = readyz

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
        if kwargs:
            self._middleware_stack.append((middleware_class, kwargs))
        else:
            self._middleware_stack.append(middleware_class)
        # Invalidate pipeline cache
        self._pipeline = None

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
            # No WebSocket handler registered — close immediately
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
        plan = route._handler_plan  # pyright: ignore[reportPrivateUsage]
        request = Request(
            scope,
            receive,
            path_params=result.params,
            max_body_size=self.max_body_size,
        )

        # Create a DI scope for this request
        di_scope: DIScope | None = None
        background_tasks = None
        response: Response | JSONResponse
        cleanup_stack: list[Any] = []
        try:
            # Check permissions before DI/handler
            if route.permissions and self._permission_policy is not None:
                await self._permission_policy.check(request, route.permissions)

            # Only create DI scope when needed
            if plan is None or plan.needs_di_scope:
                di_scope = self.container.scope()
                await di_scope.__aenter__()

            # Resolve handler arguments
            if plan is not None:
                kwargs, cleanup_stack = await resolve_from_plan(
                    plan, request, di_scope, self.container
                )
            else:
                kwargs, cleanup_stack = await resolve_dependencies(
                    route.handler, request, di_scope, self.container
                )

            # Extract BackgroundTasks using plan for O(1) lookup
            if plan is not None and plan.has_background_tasks and plan.bg_tasks_param_name:
                background_tasks = kwargs.get(plan.bg_tasks_param_name)
            else:
                for _k, v in kwargs.items():
                    if isinstance(v, BackgroundTasks):
                        background_tasks = v
                        break

            # Call the handler (use plan.is_async to avoid per-request inspect)
            if plan is not None:
                is_async = plan.is_async
            else:
                is_async = inspect.iscoroutinefunction(route.handler)

            if is_async:
                coro = route.handler(**kwargs)
            else:
                coro = asyncio.to_thread(route.handler, **kwargs)
            if self._request_timeout is not None:
                handler_result = await asyncio.wait_for(coro, timeout=self._request_timeout)
            else:
                handler_result = await coro
            # Build response
            response = self._build_response(handler_result, route.status_code, route.response_model)
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
            # Clean up generator dependencies (run code after yield)
            for gen in reversed(cleanup_stack):
                try:
                    if inspect.isasyncgen(gen):
                        with contextlib.suppress(StopAsyncIteration):
                            await gen.__anext__()
                    else:
                        with contextlib.suppress(StopIteration):
                            next(gen)
                except Exception:
                    logger.exception("Generator dependency cleanup error")

        # HEAD requests should not include body
        if method == "HEAD":
            if isinstance(response, StreamingResponse):
                response = Response(status_code=response.status_code)
            elif hasattr(response, "body"):
                response.body = b""

        try:
            await response(scope, receive, send)

            # Run background tasks after response is sent
            if background_tasks is not None:
                await background_tasks.run()
        finally:
            if di_scope is not None:
                try:
                    await di_scope.close()
                except ExceptionGroup:
                    logger.exception("DI scope teardown errors")

    def _build_response(
        self,
        result: Any,
        status_code: int,
        response_model: type[Any] | None = None,
    ) -> Response | JSONResponse:
        """Convert a handler's return value into a Response."""
        if isinstance(result, (Response, JSONResponse)):
            return result
        if result is None:
            return Response(status_code=status_code if status_code != 200 else 204)
        if response_model is not None:
            result = self._apply_response_model(result, response_model)
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

        # msgspec path: convert to builtins then validate through the model
        return msgspec.convert(msgspec.to_builtins(result), response_model)

    def _build_validation_error_response(self, exc: RequestValidationError) -> JSONResponse:
        """Build a Problem Details response from a validation error."""
        problem = exc.to_problem_detail()
        return JSONResponse(problem, status_code=self.validation_error_status)

    async def _handle_exception(self, request: Request, exc: Exception) -> Response | JSONResponse:
        """Handle an unhandled exception."""
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
