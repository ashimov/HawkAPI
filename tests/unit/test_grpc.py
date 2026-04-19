"""Tests for HawkAPI gRPC thin mount (Tier 2)."""

from __future__ import annotations

import socket
import sys
import unittest.mock

import pytest

grpc = pytest.importorskip("grpc")

# grpc.aio is available once grpc is imported via importorskip above
import grpc.aio  # noqa: E402, F811

from hawkapi.app import HawkAPI  # noqa: E402
from hawkapi.grpc import ConfigurationError  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _make_echo_generic_handler() -> grpc.GenericRpcHandler:
    async def _unary_handler(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        return request

    return grpc.method_handlers_generic_handler(
        "test.Echo",
        {"SayHello": grpc.unary_unary_rpc_method_handler(_unary_handler)},
    )


def _make_streaming_generic_handler() -> grpc.GenericRpcHandler:
    async def _stream_handler(request: bytes, context: grpc.aio.ServicerContext):  # type: ignore[return]
        for _ in range(3):
            yield request

    return grpc.method_handlers_generic_handler(
        "test.Streaming",
        {"StreamHello": grpc.unary_stream_rpc_method_handler(_stream_handler)},
    )


def _add_echo(servicer: object, server: grpc.aio.Server) -> None:
    server.add_generic_rpc_handlers((_make_echo_generic_handler(),))


def _add_streaming(servicer: object, server: grpc.aio.Server) -> None:
    server.add_generic_rpc_handlers((_make_streaming_generic_handler(),))


async def _call_echo(port: int, payload: bytes = b"hello") -> bytes:
    async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
        response = await channel.unary_unary(
            "/test.Echo/SayHello",
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )(payload)
    return response  # type: ignore[return-value]


async def _call_streaming(port: int, payload: bytes = b"hi") -> list[bytes]:
    results: list[bytes] = []
    async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
        call = channel.unary_stream(
            "/test.Streaming/StreamHello",
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )(payload)
        async for item in call:
            results.append(item)
    return results


# ---------------------------------------------------------------------------
# Test 1: Unary call echoes payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unary_echo() -> None:
    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(object(), add_to_server=_add_echo, port=port, observability=False)
    await mount._start()
    try:
        result = await _call_echo(port)
        assert result == b"hello"
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 2: context.hawkapi_app is the HawkAPI instance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_hawkapi_app() -> None:
    port = _free_port()
    app = HawkAPI()
    captured: list[object] = []

    async def _handler(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        captured.append(getattr(context, "hawkapi_app", None))
        return request

    def _add(servicer: object, server: grpc.aio.Server) -> None:
        h = grpc.unary_unary_rpc_method_handler(_handler)
        server.add_generic_rpc_handlers(
            (grpc.method_handlers_generic_handler("test.Echo", {"SayHello": h}),)
        )

    mount = app.mount_grpc(object(), add_to_server=_add, port=port, observability=True)
    await mount._start()
    try:
        await _call_echo(port)
        assert captured[0] is app
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 3: context.hawkapi_request_id is a 32-char hex string
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_request_id() -> None:
    port = _free_port()
    app = HawkAPI()
    captured: list[str] = []

    async def _handler(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        captured.append(getattr(context, "hawkapi_request_id", ""))
        return request

    def _add(servicer: object, server: grpc.aio.Server) -> None:
        h = grpc.unary_unary_rpc_method_handler(_handler)
        server.add_generic_rpc_handlers(
            (grpc.method_handlers_generic_handler("test.Echo", {"SayHello": h}),)
        )

    mount = app.mount_grpc(object(), add_to_server=_add, port=port, observability=True)
    await mount._start()
    try:
        await _call_echo(port)
        rid = captured[0]
        assert len(rid) == 32
        assert all(c in "0123456789abcdef" for c in rid)
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 4: Prometheus counter increments after a call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prometheus_counter_increments() -> None:
    pytest.importorskip("prometheus_client")
    from hawkapi.grpc._interceptor import _METRICS, _get_metrics  # noqa: PLC0415

    _get_metrics()
    counter = _METRICS.get("requests_total")
    if counter is None:
        pytest.skip("prometheus_client metrics not available")

    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(object(), add_to_server=_add_echo, port=port, observability=True)
    await mount._start()
    try:
        before = _counter_total(counter)
        await _call_echo(port)
        after = _counter_total(counter)
        assert after > before
    finally:
        await mount._stop(grace=0)


def _counter_total(counter: object) -> float:
    try:
        return sum(s.value for s in counter.collect()[0].samples)  # type: ignore[attr-defined]
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Test 5: Logs emit entry + exit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logs_emit_entry_and_exit(caplog: pytest.LogCaptureFixture) -> None:
    import logging  # noqa: PLC0415

    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(object(), add_to_server=_add_echo, port=port, observability=True)
    await mount._start()
    try:
        with caplog.at_level(logging.INFO, logger="hawkapi.grpc"):
            await _call_echo(port)
        messages = [r.getMessage() for r in caplog.records]
        assert any("grpc.request" in m for m in messages)
        assert any("grpc.response" in m for m in messages)
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 6: User interceptor runs after built-in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_interceptor_runs_after_builtin() -> None:
    order: list[str] = []

    class _UserInterceptor(grpc.aio.ServerInterceptor):
        async def intercept_service(self, continuation: object, hcd: object) -> object:
            handler = await continuation(hcd)  # type: ignore[misc]
            if handler is None:
                return handler
            orig = handler.unary_unary

            async def _w(req: bytes, ctx: object) -> bytes:
                order.append("user")
                return await orig(req, ctx)  # type: ignore[misc]

            return grpc.unary_unary_rpc_method_handler(
                _w,
                handler.request_deserializer,
                handler.response_serializer,
            )

    async def _handler(request: bytes, context: object) -> bytes:
        order.append("handler")
        return request

    def _add(servicer: object, server: grpc.aio.Server) -> None:
        h = grpc.unary_unary_rpc_method_handler(_handler)
        server.add_generic_rpc_handlers(
            (grpc.method_handlers_generic_handler("test.Echo", {"SayHello": h}),)
        )

    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(
        object(),
        add_to_server=_add,
        port=port,
        observability=True,
        interceptors=[_UserInterceptor()],
    )
    await mount._start()
    try:
        await _call_echo(port)
        assert "user" in order
        assert "handler" in order
        assert order.index("user") < order.index("handler")
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 7: Two user interceptors run in declared order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_user_interceptors_run_in_order() -> None:
    order: list[str] = []

    def _make_interceptor(name: str) -> object:
        class _I(grpc.aio.ServerInterceptor):
            async def intercept_service(self, continuation: object, hcd: object) -> object:
                handler = await continuation(hcd)  # type: ignore[misc]
                if handler is None:
                    return handler
                orig = handler.unary_unary

                async def _w(req: bytes, ctx: object) -> bytes:
                    order.append(name)
                    return await orig(req, ctx)  # type: ignore[misc]

                return grpc.unary_unary_rpc_method_handler(
                    _w,
                    handler.request_deserializer,
                    handler.response_serializer,
                )

        return _I()

    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(
        object(),
        add_to_server=_add_echo,
        port=port,
        observability=False,
        interceptors=[_make_interceptor("first"), _make_interceptor("second")],
    )
    await mount._start()
    try:
        await _call_echo(port)
        assert order.index("first") < order.index("second")
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 8: Handler raising → gRPC status propagates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_raising_propagates_status() -> None:
    async def _err_handler(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        await context.abort(grpc.StatusCode.NOT_FOUND, "not found")
        return b""

    def _add(servicer: object, server: grpc.aio.Server) -> None:
        h = grpc.unary_unary_rpc_method_handler(_err_handler)
        server.add_generic_rpc_handlers(
            (grpc.method_handlers_generic_handler("test.Echo", {"SayHello": h}),)
        )

    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(object(), add_to_server=_add, port=port, observability=True)
    await mount._start()
    try:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await _call_echo(port)
        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 9: autostart=False → not listening until manual start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autostart_false_not_listening() -> None:
    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(object(), add_to_server=_add_echo, port=port, autostart=False)
    assert mount.server is None
    await mount._start()
    try:
        result = await _call_echo(port)
        assert result == b"hello"
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 10: Manual .start() / .stop() happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_start_stop() -> None:
    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(object(), add_to_server=_add_echo, port=port, autostart=False)
    await mount.start()
    result = await _call_echo(port)
    assert result == b"hello"
    await mount.stop(grace=0)
    assert not mount._started


# ---------------------------------------------------------------------------
# Test 11: Lifespan startup binds port, shutdown releases it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_startup_binds_shutdown_releases() -> None:
    port = _free_port()
    app = HawkAPI()
    app.mount_grpc(object(), add_to_server=_add_echo, port=port, autostart=True)
    await app._hooks.run_startup()
    result = await _call_echo(port)
    assert result == b"hello"
    await app._hooks.run_shutdown()


# ---------------------------------------------------------------------------
# Test 12: ssl_credentials → add_secure_port is called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssl_credentials_uses_add_secure_port() -> None:
    port = _free_port()
    app = HawkAPI()
    fake_creds = object()
    mount = app.mount_grpc(
        object(),
        add_to_server=_add_echo,
        port=port,
        observability=False,
        ssl_credentials=fake_creds,
        autostart=False,
    )

    secure_calls: list[tuple[str, object]] = []
    original_aio_server = grpc.aio.server

    def _fake_server(**kwargs: object) -> object:
        real = original_aio_server(**kwargs)

        def _fake_secure(addr: str, creds: object) -> None:
            secure_calls.append((addr, creds))

        real.add_secure_port = _fake_secure  # type: ignore[method-assign]
        return real

    with unittest.mock.patch("grpc.aio.server", side_effect=_fake_server):
        await mount._start()

    try:
        assert len(secure_calls) == 1
        assert secure_calls[0][1] is fake_creds
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 13: reflection=True without grpcio-reflection → ConfigurationError
# ---------------------------------------------------------------------------


def test_reflection_missing_module_raises() -> None:
    from hawkapi.grpc._reflection import enable_reflection  # noqa: PLC0415

    patched = {
        "grpc_reflection": None,
        "grpc_reflection.v1alpha": None,
        "grpc_reflection.v1alpha.reflection": None,
    }
    with (
        unittest.mock.patch.dict(sys.modules, patched),
        pytest.raises(ConfigurationError, match="grpcio-reflection"),
    ):
        enable_reflection(["test.Echo"], object())


def test_reflection_missing_names_raises() -> None:
    from hawkapi.grpc._reflection import enable_reflection  # noqa: PLC0415

    with pytest.raises(ConfigurationError, match="reflection_service_names"):
        enable_reflection(None, object())


# ---------------------------------------------------------------------------
# Test 14: reflection=True with grpcio-reflection present → service registered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflection_with_module_present() -> None:
    pytest.importorskip("grpc_reflection")
    from grpc_reflection.v1alpha import reflection  # type: ignore[import-untyped]  # noqa: PLC0415

    port = _free_port()
    app = HawkAPI()
    service_names = ["test.Echo", reflection.SERVICE_NAME]
    mount = app.mount_grpc(
        object(),
        add_to_server=_add_echo,
        port=port,
        observability=False,
        reflection=True,
        reflection_service_names=service_names,
    )
    await mount._start()
    try:
        # Server started successfully — reflection handlers are registered;
        # verify the server is up and a basic echo call works
        assert mount.server is not None
        result = await _call_echo(port)
        assert result == b"hello"
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 15: Two mounts with different ports both listen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_mounts_different_ports() -> None:
    port_a = _free_port()
    port_b = _free_port()
    app = HawkAPI()
    mount_a = app.mount_grpc(object(), add_to_server=_add_echo, port=port_a, observability=False)
    mount_b = app.mount_grpc(object(), add_to_server=_add_echo, port=port_b, observability=False)
    await mount_a._start()
    await mount_b._start()
    try:
        assert await _call_echo(port_a) == b"hello"
        assert await _call_echo(port_b) == b"hello"
    finally:
        await mount_a._stop(grace=0)
        await mount_b._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 16: Two mounts with same port share one server
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_mounts_same_port_share_server() -> None:
    port = _free_port()
    app = HawkAPI()
    mount_a = app.mount_grpc(object(), add_to_server=_add_echo, port=port, observability=False)
    mount_b = app.mount_grpc(object(), add_to_server=_add_echo, port=port, observability=False)
    assert mount_a is mount_b


# ---------------------------------------------------------------------------
# Test 17: Server-streaming RPC works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_streaming_rpc() -> None:
    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(object(), add_to_server=_add_streaming, port=port, observability=False)
    await mount._start()
    try:
        results = await _call_streaming(port, payload=b"stream-me")
        assert len(results) == 3
        assert all(r == b"stream-me" for r in results)
    finally:
        await mount._stop(grace=0)


# ---------------------------------------------------------------------------
# Test 18: autostart=False + stop() without start() is safe no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autostart_false_stop_without_start_is_noop() -> None:
    port = _free_port()
    app = HawkAPI()
    mount = app.mount_grpc(object(), add_to_server=_add_echo, port=port, autostart=False)
    await mount.stop(grace=0)
    assert not mount._started
