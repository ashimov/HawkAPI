"""Tests for lifespan management."""

import pytest

from hawkapi.lifespan.hooks import HookRegistry
from hawkapi.lifespan.manager import LifespanManager


class TestHookRegistry:
    @pytest.mark.asyncio
    async def test_startup_hooks_run_in_order(self):
        registry = HookRegistry()
        order = []

        @registry.on_startup
        async def first():
            order.append("first")

        @registry.on_startup
        async def second():
            order.append("second")

        await registry.run_startup()
        assert order == ["first", "second"]

    @pytest.mark.asyncio
    async def test_shutdown_hooks_run_in_reverse(self):
        registry = HookRegistry()
        order = []

        @registry.on_shutdown
        async def first():
            order.append("first")

        @registry.on_shutdown
        async def second():
            order.append("second")

        await registry.run_shutdown()
        assert order == ["second", "first"]

    @pytest.mark.asyncio
    async def test_sync_hooks_work(self):
        registry = HookRegistry()
        called = []

        @registry.on_startup
        def sync_hook():
            called.append("sync")

        await registry.run_startup()
        assert called == ["sync"]

    def test_merge_registries(self):
        r1 = HookRegistry()
        r2 = HookRegistry()

        @r1.on_startup
        async def hook1():
            pass

        @r2.on_startup
        async def hook2():
            pass

        r1.merge(r2)
        assert len(r1.startup_hooks) == 2


class TestLifespanManager:
    @pytest.mark.asyncio
    async def test_startup_shutdown_protocol(self):
        registry = HookRegistry()
        started = []
        stopped = []

        @registry.on_startup
        async def startup():
            started.append(True)

        @registry.on_shutdown
        async def shutdown():
            stopped.append(True)

        manager = LifespanManager(registry)

        messages = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        msg_idx = 0
        sent = []

        async def receive():
            nonlocal msg_idx
            msg = messages[msg_idx]
            msg_idx += 1
            return msg

        async def send(message):
            sent.append(message)

        scope = {"type": "lifespan", "state": {}}
        await manager.handle(scope, receive, send)

        assert started == [True]
        assert stopped == [True]
        assert sent[0]["type"] == "lifespan.startup.complete"
        assert sent[1]["type"] == "lifespan.shutdown.complete"

    @pytest.mark.asyncio
    async def test_lifespan_context_manager(self):
        from contextlib import asynccontextmanager

        registry = HookRegistry()
        state_log = []

        @asynccontextmanager
        async def lifespan(app):
            state_log.append("startup")
            app.state.db = "connected"
            yield
            state_log.append("shutdown")

        manager = LifespanManager(registry, lifespan)

        messages = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        msg_idx = 0
        sent = []

        async def receive():
            nonlocal msg_idx
            msg = messages[msg_idx]
            msg_idx += 1
            return msg

        async def send(message):
            sent.append(message)

        scope = {"type": "lifespan", "state": {}}
        await manager.handle(scope, receive, send)

        assert state_log == ["startup", "shutdown"]

    @pytest.mark.asyncio
    async def test_hooks_and_lifespan_coexist(self):
        """Unlike FastAPI, both hooks AND lifespan work together."""
        from contextlib import asynccontextmanager

        registry = HookRegistry()
        order = []

        @registry.on_startup
        async def hook_startup():
            order.append("hook-startup")

        @registry.on_shutdown
        async def hook_shutdown():
            order.append("hook-shutdown")

        @asynccontextmanager
        async def lifespan(app):
            order.append("lifespan-startup")
            yield
            order.append("lifespan-shutdown")

        manager = LifespanManager(registry, lifespan)

        messages = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        msg_idx = 0

        async def receive():
            nonlocal msg_idx
            msg = messages[msg_idx]
            msg_idx += 1
            return msg

        async def send(message):
            pass

        scope = {"type": "lifespan", "state": {}}
        await manager.handle(scope, receive, send)

        # Hooks run first, then lifespan
        assert order == [
            "hook-startup",
            "lifespan-startup",
            "lifespan-shutdown",
            "hook-shutdown",
        ]
