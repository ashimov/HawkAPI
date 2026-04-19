"""HawkAPIObservabilityInterceptor — logging + Prometheus for gRPC."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger("hawkapi.grpc")

# Module-level metric cache so re-imports in tests don't blow up
_METRICS: dict[str, Any] = {}


def _get_metrics() -> tuple[Any, Any]:
    """Return (requests_total counter, request_duration histogram), creating once."""
    if "requests_total" not in _METRICS:
        try:
            from prometheus_client import (  # noqa: PLC0415  # pyright: ignore[reportMissingImports]
                Counter,  # pyright: ignore[reportUnknownVariableType]
                Histogram,  # pyright: ignore[reportUnknownVariableType]
            )

            _METRICS["requests_total"] = Counter(
                "hawkapi_grpc_requests_total",
                "Total gRPC requests",
                ["method", "code"],
            )
            _METRICS["request_duration"] = Histogram(
                "hawkapi_grpc_request_duration_seconds",
                "gRPC request duration in seconds",
                ["method"],
            )
        except Exception:  # prometheus not installed or duplicate  # noqa: BLE001
            _METRICS["requests_total"] = None
            _METRICS["request_duration"] = None
    return _METRICS["requests_total"], _METRICS["request_duration"]  # pyright: ignore[reportUnknownVariableType]


class _ContextProxy:
    """Proxy around ``grpc.aio.ServicerContext`` that allows arbitrary attribute storage.

    grpcio's Cython ServicerContext uses ``__slots__`` and disallows attribute
    assignment.  This proxy delegates all attribute lookups to the real context
    while allowing extra attrs (e.g. ``hawkapi_app``) to be stored in a normal
    ``__dict__``.
    """

    # _ctx uses a slot for speed; __dict__ is declared explicitly so instances
    # can hold arbitrary extra attributes (hawkapi_app, hawkapi_request_id…).
    __slots__ = ("_ctx", "__dict__")

    def __init__(self, ctx: Any) -> None:
        object.__setattr__(self, "_ctx", ctx)

    def __getattr__(self, name: str) -> Any:
        try:
            return object.__getattribute__(self, "__dict__")[name]
        except KeyError:
            pass
        return getattr(object.__getattribute__(self, "_ctx"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_ctx":
            object.__setattr__(self, name, value)
        else:
            object.__getattribute__(self, "__dict__")[name] = value


def _build_interceptor_class() -> type:
    """Build HawkAPIObservabilityInterceptor inheriting from grpc.aio.ServerInterceptor.

    Called lazily so grpc is only imported when actually used.
    """
    import grpc  # noqa: PLC0415
    import grpc.aio  # noqa: PLC0415

    class _HawkAPIObservabilityInterceptor(grpc.aio.ServerInterceptor):  # type: ignore[misc]
        """gRPC server interceptor: context injection, logging, and Prometheus metrics."""

        def __init__(self, app: Any) -> None:
            self._app = app

        async def intercept_service(
            self,
            continuation: Any,
            handler_call_details: Any,
        ) -> Any:
            """Wrap the RPC handler with observability."""
            handler = await continuation(handler_call_details)
            if handler is None:
                return handler

            method: str = handler_call_details.method
            app = self._app

            original_fn = (
                handler.unary_unary
                or handler.unary_stream
                or handler.stream_unary
                or handler.stream_stream
            )
            response_streaming: bool = handler.response_streaming
            request_streaming: bool = handler.request_streaming
            deser = handler.request_deserializer
            ser = handler.response_serializer

            if response_streaming:
                wrapped_fn = _make_streaming_wrapper(original_fn, app, method)
                return grpc.unary_stream_rpc_method_handler(wrapped_fn, deser, ser)
            elif not request_streaming:
                wrapped_fn = _make_unary_wrapper(original_fn, app, method)
                return grpc.unary_unary_rpc_method_handler(wrapped_fn, deser, ser)
            else:
                wrapped_fn = _make_unary_wrapper(original_fn, app, method)
                return grpc.stream_unary_rpc_method_handler(wrapped_fn, deser, ser)

    return _HawkAPIObservabilityInterceptor


# Cache the built class so we don't rebuild on every mount_grpc call
_interceptor_class: type | None = None


class HawkAPIObservabilityInterceptor:
    """Public name for the observability interceptor.

    Instantiation lazily builds the real class (inheriting from
    ``grpc.aio.ServerInterceptor``) so grpc is not imported at module load.
    """

    def __new__(cls, app: Any) -> Any:  # type: ignore[misc]
        global _interceptor_class
        if _interceptor_class is None:
            _interceptor_class = _build_interceptor_class()
        return _interceptor_class(app)


def _make_unary_wrapper(original_fn: Any, app: Any, method: str) -> Any:
    """Build a coroutine wrapper for unary handlers."""

    async def _unary(request_or_iterator: Any, context: Any) -> Any:
        request_id = uuid.uuid4().hex
        proxy = _ContextProxy(context)
        proxy.hawkapi_app = app
        proxy.hawkapi_request_id = request_id

        peer = _safe_peer(proxy)
        logger.info(
            "grpc.request",
            extra={
                "event": "grpc.request",
                "method": method,
                "peer": peer,
                "request_id": request_id,
            },
        )

        start = time.monotonic()
        code_str = "OK"
        try:
            result = await original_fn(request_or_iterator, proxy)
            return result
        except Exception:
            code_str = _safe_code(proxy)
            raise
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 3)
            if code_str == "OK":
                code_str = _safe_code(proxy)
            logger.info(
                "grpc.response",
                extra={
                    "event": "grpc.response",
                    "method": method,
                    "code": code_str,
                    "duration_ms": duration_ms,
                },
            )
            _emit_metrics(method, code_str, time.monotonic() - start)

    return _unary


def _make_streaming_wrapper(original_fn: Any, app: Any, method: str) -> Any:
    """Build an async-generator wrapper for server-streaming handlers."""

    async def _streaming(request_or_iterator: Any, context: Any) -> Any:
        request_id = uuid.uuid4().hex
        proxy = _ContextProxy(context)
        proxy.hawkapi_app = app
        proxy.hawkapi_request_id = request_id

        peer = _safe_peer(proxy)
        logger.info(
            "grpc.request",
            extra={
                "event": "grpc.request",
                "method": method,
                "peer": peer,
                "request_id": request_id,
            },
        )

        start = time.monotonic()
        code_str = "OK"
        try:
            async for item in original_fn(request_or_iterator, proxy):
                yield item
        except Exception:
            code_str = _safe_code(proxy)
            raise
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 3)
            if code_str == "OK":
                code_str = _safe_code(proxy)
            logger.info(
                "grpc.response",
                extra={
                    "event": "grpc.response",
                    "method": method,
                    "code": code_str,
                    "duration_ms": duration_ms,
                },
            )
            _emit_metrics(method, code_str, time.monotonic() - start)

    return _streaming


def _safe_peer(context: Any) -> str:
    try:
        return str(context.peer())
    except Exception:  # noqa: BLE001
        return ""


def _safe_code(context: Any) -> str:
    try:
        c = context.code()
        return str(c) if c is not None else "OK"
    except Exception:  # noqa: BLE001
        return "OK"


def _emit_metrics(method: str, code_str: str, duration_s: float) -> None:
    try:
        req_total, req_dur = _get_metrics()
        if req_total is not None:
            req_total.labels(method=method, code=code_str).inc()
        if req_dur is not None:
            req_dur.labels(method=method).observe(duration_s)
    except Exception:  # noqa: BLE001, S110
        pass
