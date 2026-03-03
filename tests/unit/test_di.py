"""Tests for Dependency Injection system."""

import pytest

from hawkapi.di.container import Container
from hawkapi.di.depends import Depends


class FakeDB:
    def __init__(self, url: str = "sqlite://"):
        self.url = url
        self.closed = False

    async def close(self):
        self.closed = True


class FakeSession:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FakeLogger:
    pass


class TestContainer:
    def test_register_singleton(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("postgres://"))
        assert container.has(FakeDB)

    def test_register_scoped(self):
        container = Container()
        container.scoped(FakeSession, factory=FakeSession)
        assert container.has(FakeSession)

    def test_register_transient(self):
        container = Container()
        container.transient(FakeLogger, factory=FakeLogger)
        assert container.has(FakeLogger)

    def test_duplicate_registration_raises(self):
        container = Container()
        container.singleton(FakeDB, factory=FakeDB)
        with pytest.raises(ValueError, match="already registered"):
            container.singleton(FakeDB, factory=FakeDB)

    def test_named_dependencies(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("cache"), name="cache")
        container.singleton(FakeDB, factory=lambda: FakeDB("main"), name="main")
        assert container.has(FakeDB, "cache")
        assert container.has(FakeDB, "main")

    def test_has_returns_false_for_unregistered(self):
        container = Container()
        assert not container.has(FakeDB)

    @pytest.mark.asyncio
    async def test_resolve_singleton(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("test://"))

        db1 = await container.resolve(FakeDB)
        db2 = await container.resolve(FakeDB)
        assert db1 is db2  # Same instance
        assert db1.url == "test://"

    @pytest.mark.asyncio
    async def test_resolve_transient(self):
        container = Container()
        container.transient(FakeLogger, factory=FakeLogger)

        logger1 = await container.resolve(FakeLogger)
        logger2 = await container.resolve(FakeLogger)
        assert logger1 is not logger2  # Different instances

    @pytest.mark.asyncio
    async def test_resolve_scoped_without_scope_raises(self):
        container = Container()
        container.scoped(FakeSession, factory=FakeSession)

        with pytest.raises(RuntimeError, match="without a scope"):
            await container.resolve(FakeSession)

    @pytest.mark.asyncio
    async def test_resolve_not_registered_raises(self):
        container = Container()
        with pytest.raises(LookupError, match="No provider"):
            await container.resolve(FakeDB)


class TestScope:
    @pytest.mark.asyncio
    async def test_scoped_same_within_scope(self):
        container = Container()
        container.scoped(FakeSession, factory=FakeSession)

        async with container.scope() as scope:
            s1 = await scope.resolve(FakeSession)
            s2 = await scope.resolve(FakeSession)
            assert s1 is s2  # Same within scope

    @pytest.mark.asyncio
    async def test_scoped_different_across_scopes(self):
        container = Container()
        container.scoped(FakeSession, factory=FakeSession)

        async with container.scope() as scope1:
            s1 = await scope1.resolve(FakeSession)

        async with container.scope() as scope2:
            s2 = await scope2.resolve(FakeSession)

        assert s1 is not s2  # Different across scopes

    @pytest.mark.asyncio
    async def test_scope_teardown_closes_resources(self):
        container = Container()
        container.scoped(FakeSession, factory=FakeSession)

        async with container.scope() as scope:
            session = await scope.resolve(FakeSession)
            assert not session.closed

        assert session.closed  # Closed on scope exit

    @pytest.mark.asyncio
    async def test_singleton_shared_across_scopes(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("shared"))

        async with container.scope() as scope1:
            db1 = await scope1.resolve(FakeDB)

        async with container.scope() as scope2:
            db2 = await scope2.resolve(FakeDB)

        assert db1 is db2  # Same singleton

    @pytest.mark.asyncio
    async def test_named_dependency_in_scope(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("cache"), name="cache")
        container.singleton(FakeDB, factory=lambda: FakeDB("main"), name="main")

        async with container.scope() as scope:
            cache = await scope.resolve(FakeDB, "cache")
            main = await scope.resolve(FakeDB, "main")
            assert cache.url == "cache"
            assert main.url == "main"
            assert cache is not main


class TestOverride:
    @pytest.mark.asyncio
    async def test_override_replaces_provider(self):
        container = Container()
        container.singleton(FakeDB, factory=lambda: FakeDB("production"))

        with container.override(FakeDB, factory=lambda: FakeDB("test")):
            db = await container.resolve(FakeDB)
            assert db.url == "test"

        # After override exits, original is restored
        db = await container.resolve(FakeDB)
        assert db.url == "production"

    @pytest.mark.asyncio
    async def test_override_nonexistent(self):
        container = Container()

        with container.override(FakeDB, factory=lambda: FakeDB("test")):
            db = await container.resolve(FakeDB)
            assert db.url == "test"

        # After exit, provider is removed
        assert not container.has(FakeDB)


class TestDepends:
    def test_depends_repr(self):
        def get_db():
            pass

        d = Depends(get_db)
        assert "get_db" in repr(d)

    def test_depends_name(self):
        d = Depends(name="cache")
        assert d.name == "cache"
        assert "cache" in repr(d)
