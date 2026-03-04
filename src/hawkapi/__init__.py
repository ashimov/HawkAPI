"""HawkAPI — High-performance Python web framework."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Eager imports — core types used in every application
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
    from hawkapi.middleware import Middleware
    from hawkapi.middleware.request_limits import RequestLimitsMiddleware
    from hawkapi.observability import ObservabilityConfig, ObservabilityMiddleware
    from hawkapi.openapi import (
        Change,
        ChangeType,
        Severity,
        detect_breaking_changes,
        generate_openapi,
    )
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
        SecurityScheme,
    )
    from hawkapi.staticfiles import StaticFiles
    from hawkapi.testing import TestClient, TestResponse, override
    from hawkapi.validation.constraints import Body, Cookie, Header, Path, Query
    from hawkapi.websocket import WebSocket, WebSocketDisconnect

__version__ = "0.1.0"

# Lazy imports — loaded on first access for faster cold start
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # background
    "BackgroundTasks": ("hawkapi.background", "BackgroundTasks"),
    # config
    "Settings": ("hawkapi.config", "Settings"),
    "env_field": ("hawkapi.config", "env_field"),
    # middleware
    "Middleware": ("hawkapi.middleware", "Middleware"),
    "RequestLimitsMiddleware": ("hawkapi.middleware.request_limits", "RequestLimitsMiddleware"),
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
    "SecurityScheme": ("hawkapi.security", "SecurityScheme"),
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
    "BackgroundTasks",
    "Body",
    "Change",
    "ChangeType",
    "Container",
    "Controller",
    "Cookie",
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
    "Path",
    "PermissionPolicy",
    "PlainTextResponse",
    "Query",
    "RedirectResponse",
    "Request",
    "RequestLimitsMiddleware",
    "Response",
    "Route",
    "Router",
    "SecurityScheme",
    "ServerSentEvent",
    "Settings",
    "Severity",
    "StaticFiles",
    "StreamingResponse",
    "TestClient",
    "TestResponse",
    "VersionRouter",
    "WebSocket",
    "WebSocketDisconnect",
    "delete",
    "detect_breaking_changes",
    "env_field",
    "generate_openapi",
    "get",
    "override",
    "patch",
    "post",
    "put",
]
