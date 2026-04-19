"""HawkAPI — High-performance Python web framework."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Eager imports — core types used in every application
from hawkapi import status
from hawkapi.app import HawkAPI
from hawkapi.di import Container, Depends
from hawkapi.exceptions import HTTPException
from hawkapi.requests import Request
from hawkapi.responses import JSONResponse, Response
from hawkapi.routing import Route, Router

# TYPE_CHECKING-only imports so pyright sees the symbols
if TYPE_CHECKING:
    from hawkapi.background import BackgroundTasks
    from hawkapi.config import Settings, env_field
    from hawkapi.flags import (
        EnvFlagProvider,
        EvalContext,
        FileFlagProvider,
        FlagDisabled,
        FlagProvider,
        Flags,
        StaticFlagProvider,
        get_flags,
        requires_flag,
    )
    from hawkapi.middleware import Middleware
    from hawkapi.middleware.adaptive_concurrency import AdaptiveConcurrencyMiddleware
    from hawkapi.middleware.circuit_breaker import CircuitBreakerMiddleware
    from hawkapi.middleware.debug import DebugMiddleware
    from hawkapi.middleware.prometheus import PrometheusMiddleware
    from hawkapi.middleware.request_limits import RequestLimitsMiddleware
    from hawkapi.middleware.session import SessionMiddleware
    from hawkapi.middleware.structured_logging import StructuredLoggingMiddleware
    from hawkapi.middleware.trusted_proxy import TrustedProxyMiddleware
    from hawkapi.observability import ObservabilityConfig, ObservabilityMiddleware
    from hawkapi.openapi import (
        Change,
        ChangeType,
        Severity,
        detect_breaking_changes,
        generate_openapi,
    )
    from hawkapi.pagination import CursorPage, CursorParams, Page, PaginationParams
    from hawkapi.plugins import Plugin
    from hawkapi.responses import (
        EventSourceResponse,
        FileResponse,
        HTMLResponse,
        PlainTextResponse,
        RedirectResponse,
        ServerSentEvent,
        StreamingResponse,
    )
    from hawkapi.routing import Controller, VersionRouter
    from hawkapi.routing.controllers import delete, get, patch, post, put
    from hawkapi.security import (
        APIKeyCookie,
        APIKeyHeader,
        APIKeyQuery,
        HTTPBasic,
        HTTPBasicCredentials,
        HTTPBearer,
        HTTPBearerCredentials,
        OAuth2PasswordBearer,
        PermissionPolicy,
        Security,
        SecurityScheme,
        SecurityScopes,
    )
    from hawkapi.staticfiles import StaticFiles
    from hawkapi.testing import TestClient, TestResponse, override
    from hawkapi.validation.constraints import Body, Cookie, Header, Path, Query
    from hawkapi.websocket import WebSocket, WebSocketDisconnect

__version__ = "0.1.2"

# Lazy imports — loaded on first access for faster cold start
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # background
    "BackgroundTasks": ("hawkapi.background", "BackgroundTasks"),
    # config
    "Settings": ("hawkapi.config", "Settings"),
    "env_field": ("hawkapi.config", "env_field"),
    # middleware
    "AdaptiveConcurrencyMiddleware": (
        "hawkapi.middleware.adaptive_concurrency",
        "AdaptiveConcurrencyMiddleware",
    ),
    "CSRFMiddleware": ("hawkapi.middleware.csrf", "CSRFMiddleware"),
    "CircuitBreakerMiddleware": ("hawkapi.middleware.circuit_breaker", "CircuitBreakerMiddleware"),
    "RedisCircuitBreakerMiddleware": (
        "hawkapi.middleware.circuit_breaker_redis",
        "RedisCircuitBreakerMiddleware",
    ),
    "DebugMiddleware": ("hawkapi.middleware.debug", "DebugMiddleware"),
    "Middleware": ("hawkapi.middleware", "Middleware"),
    "MiddlewareEntry": ("hawkapi.middleware._pipeline", "MiddlewareEntry"),
    "PrometheusMiddleware": ("hawkapi.middleware.prometheus", "PrometheusMiddleware"),
    "RequestLimitsMiddleware": ("hawkapi.middleware.request_limits", "RequestLimitsMiddleware"),
    "SessionMiddleware": ("hawkapi.middleware.session", "SessionMiddleware"),
    "StructuredLoggingMiddleware": (
        "hawkapi.middleware.structured_logging",
        "StructuredLoggingMiddleware",
    ),
    "TrustedProxyMiddleware": (
        "hawkapi.middleware.trusted_proxy",
        "TrustedProxyMiddleware",
    ),
    # pagination
    "Page": ("hawkapi.pagination", "Page"),
    "CursorPage": ("hawkapi.pagination", "CursorPage"),
    "PaginationParams": ("hawkapi.pagination", "PaginationParams"),
    "CursorParams": ("hawkapi.pagination", "CursorParams"),
    # plugins
    "Plugin": ("hawkapi.plugins", "Plugin"),
    # openapi
    "generate_openapi": ("hawkapi.openapi", "generate_openapi"),
    "detect_breaking_changes": ("hawkapi.openapi", "detect_breaking_changes"),
    "Change": ("hawkapi.openapi", "Change"),
    "ChangeType": ("hawkapi.openapi", "ChangeType"),
    "Severity": ("hawkapi.openapi", "Severity"),
    # responses
    "EventSourceResponse": ("hawkapi.responses", "EventSourceResponse"),
    "FileResponse": ("hawkapi.responses", "FileResponse"),
    "HTMLResponse": ("hawkapi.responses", "HTMLResponse"),
    "PlainTextResponse": ("hawkapi.responses", "PlainTextResponse"),
    "RedirectResponse": ("hawkapi.responses", "RedirectResponse"),
    "ServerSentEvent": ("hawkapi.responses", "ServerSentEvent"),
    "StreamingResponse": ("hawkapi.responses", "StreamingResponse"),
    # routing
    "Controller": ("hawkapi.routing", "Controller"),
    "VersionRouter": ("hawkapi.routing", "VersionRouter"),
    "get": ("hawkapi.routing.controllers", "get"),
    "post": ("hawkapi.routing.controllers", "post"),
    "put": ("hawkapi.routing.controllers", "put"),
    "patch": ("hawkapi.routing.controllers", "patch"),
    "delete": ("hawkapi.routing.controllers", "delete"),
    # security
    "APIKeyCookie": ("hawkapi.security", "APIKeyCookie"),
    "APIKeyHeader": ("hawkapi.security", "APIKeyHeader"),
    "APIKeyQuery": ("hawkapi.security", "APIKeyQuery"),
    "HTTPBasic": ("hawkapi.security", "HTTPBasic"),
    "HTTPBasicCredentials": ("hawkapi.security", "HTTPBasicCredentials"),
    "HTTPBearer": ("hawkapi.security", "HTTPBearer"),
    "HTTPBearerCredentials": ("hawkapi.security", "HTTPBearerCredentials"),
    "OAuth2PasswordBearer": ("hawkapi.security", "OAuth2PasswordBearer"),
    "PermissionPolicy": ("hawkapi.security", "PermissionPolicy"),
    "Security": ("hawkapi.security", "Security"),
    "SecurityScheme": ("hawkapi.security", "SecurityScheme"),
    "SecurityScopes": ("hawkapi.security", "SecurityScopes"),
    # staticfiles
    "StaticFiles": ("hawkapi.staticfiles", "StaticFiles"),
    # testing
    "TestClient": ("hawkapi.testing", "TestClient"),
    "TestResponse": ("hawkapi.testing", "TestResponse"),
    "override": ("hawkapi.testing", "override"),
    # validation
    "Body": ("hawkapi.validation.constraints", "Body"),
    "Cookie": ("hawkapi.validation.constraints", "Cookie"),
    "Header": ("hawkapi.validation.constraints", "Header"),
    "Path": ("hawkapi.validation.constraints", "Path"),
    "Query": ("hawkapi.validation.constraints", "Query"),
    # websocket
    "WebSocket": ("hawkapi.websocket", "WebSocket"),
    "WebSocketDisconnect": ("hawkapi.websocket", "WebSocketDisconnect"),
    # observability
    "ObservabilityConfig": ("hawkapi.observability", "ObservabilityConfig"),
    "ObservabilityMiddleware": ("hawkapi.observability", "ObservabilityMiddleware"),
    # feature flags
    "EvalContext": ("hawkapi.flags", "EvalContext"),
    "EnvFlagProvider": ("hawkapi.flags", "EnvFlagProvider"),
    "FileFlagProvider": ("hawkapi.flags", "FileFlagProvider"),
    "FlagDisabled": ("hawkapi.flags", "FlagDisabled"),
    "FlagProvider": ("hawkapi.flags", "FlagProvider"),
    "Flags": ("hawkapi.flags", "Flags"),
    "StaticFlagProvider": ("hawkapi.flags", "StaticFlagProvider"),
    "get_flags": ("hawkapi.flags", "get_flags"),
    "requires_flag": ("hawkapi.flags", "requires_flag"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        value: Any = getattr(module, attr_name)
        # Cache in module namespace for subsequent access
        globals()[name] = value
        return value
    msg = f"module 'hawkapi' has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "APIKeyCookie",
    "APIKeyHeader",
    "APIKeyQuery",
    "AdaptiveConcurrencyMiddleware",
    "BackgroundTasks",
    "Body",
    "Change",
    "ChangeType",
    "CircuitBreakerMiddleware",
    "Container",
    "CursorPage",
    "CursorParams",
    "Controller",
    "Cookie",
    "DebugMiddleware",
    "Depends",
    "EventSourceResponse",
    "FileResponse",
    "HTMLResponse",
    "HTTPBasic",
    "HTTPBasicCredentials",
    "HTTPBearer",
    "HTTPBearerCredentials",
    "HTTPException",
    "HawkAPI",
    "Header",
    "JSONResponse",
    "Middleware",
    "OAuth2PasswordBearer",
    "ObservabilityConfig",
    "ObservabilityMiddleware",
    "Page",
    "PaginationParams",
    "Path",
    "PermissionPolicy",
    "Plugin",
    "PlainTextResponse",
    "PrometheusMiddleware",
    "Query",
    "RedirectResponse",
    "Request",
    "RequestLimitsMiddleware",
    "Response",
    "Route",
    "Router",
    "Security",
    "SecurityScheme",
    "SecurityScopes",
    "ServerSentEvent",
    "SessionMiddleware",
    "Settings",
    "Severity",
    "StaticFiles",
    "StreamingResponse",
    "StructuredLoggingMiddleware",
    "TrustedProxyMiddleware",
    "TestClient",
    "TestResponse",
    "status",
    "VersionRouter",
    "WebSocket",
    "WebSocketDisconnect",
    "delete",
    "detect_breaking_changes",
    "env_field",
    "generate_openapi",
    "get",
    "get_flags",
    "override",
    "patch",
    "post",
    "put",
    "requires_flag",
    "EvalContext",
    "EnvFlagProvider",
    "FileFlagProvider",
    "FlagDisabled",
    "FlagProvider",
    "Flags",
    "StaticFlagProvider",
]
