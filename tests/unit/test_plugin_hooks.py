"""Tests for expanded Plugin hooks (on_startup, on_shutdown, on_exception, on_middleware_added)."""

from __future__ import annotations

from typing import Any

import pytest

from hawkapi import HawkAPI
from hawkapi.middleware.base import Middleware
from hawkapi.plugins import Plugin

# Disable all built-in doc/health routes so only test routes exist.
_NO_DOCS = dict(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    scalar_url=None,
    health_url=None,
)


class TestOnStartup:
    """Plugin.on_startup is called during lifespan startup."""

    @pytest.mark.asyncio
    async def test_on_startup_called_during_startup(self) -> None:
        started: list[bool] = []

        class StartupPlugin(Plugin):
            def on_startup(self) -> None:
                started.append(True)

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(StartupPlugin())

        sent: list[dict[str, Any]] = []
        msgs = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive() -> dict[str, Any]:
            return next(msgs)

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
        assert started == [True]


class TestOnShutdown:
    """Plugin.on_shutdown is called during lifespan shutdown."""

    @pytest.mark.asyncio
    async def test_on_shutdown_called_during_shutdown(self) -> None:
        stopped: list[bool] = []

        class ShutdownPlugin(Plugin):
            def on_shutdown(self) -> None:
                stopped.append(True)

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(ShutdownPlugin())

        sent: list[dict[str, Any]] = []
        msgs = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive() -> dict[str, Any]:
            return next(msgs)

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
        assert stopped == [True]


class TestOnException:
    """Plugin.on_exception is called when an unhandled exception occurs."""

    @pytest.mark.asyncio
    async def test_on_exception_called_on_unhandled_exception(self) -> None:
        captured: list[tuple[Any, Exception]] = []

        class ExceptionPlugin(Plugin):
            def on_exception(self, request: Any, exc: Exception) -> None:
                captured.append((request, exc))

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(ExceptionPlugin())

        @app.get("/fail")
        async def handler() -> dict[str, str]:
            raise RuntimeError("boom")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/fail",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app(scope, receive, send)

        assert len(captured) == 1
        req, exc = captured[0]
        assert isinstance(exc, RuntimeError)
        assert str(exc) == "boom"


class TestOnMiddlewareAdded:
    """Plugin.on_middleware_added is called when middleware is added."""

    def test_on_middleware_added_called(self) -> None:
        captured: list[tuple[type, dict[str, Any]]] = []

        class MWPlugin(Plugin):
            def on_middleware_added(self, middleware_class: type, kwargs: dict[str, Any]) -> None:
                captured.append((middleware_class, kwargs))

        class DummyMiddleware(Middleware):
            async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
                await self.app(scope, receive, send)

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(MWPlugin())
        app.add_middleware(DummyMiddleware, some_option="test")

        assert len(captured) == 1
        cls, kwargs = captured[0]
        assert cls is DummyMiddleware
        assert kwargs == {"some_option": "test"}


class TestMultiplePluginsReceiveHooks:
    """Multiple plugins all receive hook callbacks."""

    @pytest.mark.asyncio
    async def test_all_plugins_receive_startup_and_shutdown(self) -> None:
        order: list[str] = []

        class PluginA(Plugin):
            def on_startup(self) -> None:
                order.append("A-startup")

            def on_shutdown(self) -> None:
                order.append("A-shutdown")

        class PluginB(Plugin):
            def on_startup(self) -> None:
                order.append("B-startup")

            def on_shutdown(self) -> None:
                order.append("B-shutdown")

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(PluginA())
        app.add_plugin(PluginB())

        sent: list[dict[str, Any]] = []
        msgs = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive() -> dict[str, Any]:
            return next(msgs)

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)

        assert "A-startup" in order
        assert "B-startup" in order
        assert "A-shutdown" in order
        assert "B-shutdown" in order

    def test_all_plugins_receive_middleware_added(self) -> None:
        captured_a: list[type] = []
        captured_b: list[type] = []

        class PluginA(Plugin):
            def on_middleware_added(self, middleware_class: type, kwargs: dict[str, Any]) -> None:
                captured_a.append(middleware_class)

        class PluginB(Plugin):
            def on_middleware_added(self, middleware_class: type, kwargs: dict[str, Any]) -> None:
                captured_b.append(middleware_class)

        class DummyMiddleware(Middleware):
            async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
                await self.app(scope, receive, send)

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(PluginA())
        app.add_plugin(PluginB())
        app.add_middleware(DummyMiddleware)

        assert captured_a == [DummyMiddleware]
        assert captured_b == [DummyMiddleware]

    @pytest.mark.asyncio
    async def test_all_plugins_receive_on_exception(self) -> None:
        captured_a: list[Exception] = []
        captured_b: list[Exception] = []

        class PluginA(Plugin):
            def on_exception(self, request: Any, exc: Exception) -> None:
                captured_a.append(exc)

        class PluginB(Plugin):
            def on_exception(self, request: Any, exc: Exception) -> None:
                captured_b.append(exc)

        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(PluginA())
        app.add_plugin(PluginB())

        @app.get("/fail")
        async def handler() -> dict[str, str]:
            raise ValueError("multi-plugin error")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/fail",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            pass

        await app(scope, receive, send)

        assert len(captured_a) == 1
        assert len(captured_b) == 1
        assert str(captured_a[0]) == "multi-plugin error"
        assert str(captured_b[0]) == "multi-plugin error"


class TestDefaultNoOpImplementations:
    """Default no-op implementations don't crash."""

    def test_default_on_startup_does_not_crash(self) -> None:
        plugin = Plugin()
        plugin.on_startup()  # Should not raise

    def test_default_on_shutdown_does_not_crash(self) -> None:
        plugin = Plugin()
        plugin.on_shutdown()  # Should not raise

    def test_default_on_exception_does_not_crash(self) -> None:
        plugin = Plugin()
        plugin.on_exception(None, RuntimeError("test"))  # Should not raise

    def test_default_on_middleware_added_does_not_crash(self) -> None:
        plugin = Plugin()
        plugin.on_middleware_added(object, {})  # Should not raise

    @pytest.mark.asyncio
    async def test_default_plugin_survives_full_lifecycle(self) -> None:
        """A Plugin with no overrides survives startup, request, and shutdown."""
        app = HawkAPI(**_NO_DOCS)
        app.add_plugin(Plugin())

        @app.get("/test")
        async def handler() -> dict[str, str]:
            return {"ok": True}

        sent: list[dict[str, Any]] = []
        msgs = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive() -> dict[str, Any]:
            return next(msgs)

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)

        types = [m["type"] for m in sent]
        assert "lifespan.startup.complete" in types
        assert "lifespan.shutdown.complete" in types
