"""Tests for DI scope exception-safe cleanup."""

import pytest

from hawkapi.di.provider import Lifecycle, Provider
from hawkapi.di.scope import Scope


class FakeProvider(Provider):
    def __init__(self, factory, lifecycle=Lifecycle.SCOPED):
        self.factory = factory
        self.lifecycle = lifecycle
        self._instance = None

    async def resolve(self):
        return self.factory()


class GoodResource:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class BadResource:
    def close(self):
        raise RuntimeError("cleanup failed!")


class AsyncResource:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


async def test_scope_cleanup_all_good():
    r1 = GoodResource()
    r2 = GoodResource()
    providers = {
        (GoodResource, "a"): FakeProvider(lambda: r1),
        (GoodResource, "b"): FakeProvider(lambda: r2),
    }
    scope = Scope(providers)
    await scope.resolve(GoodResource, "a")
    await scope.resolve(GoodResource, "b")
    await scope.close()
    assert r1.closed
    assert r2.closed


async def test_scope_cleanup_exception_safe():
    """If one cleanup fails, others still run."""
    good = GoodResource()
    bad = BadResource()
    providers = {
        (BadResource, None): FakeProvider(lambda: bad),
        (GoodResource, None): FakeProvider(lambda: good),
    }
    scope = Scope(providers)
    await scope.resolve(BadResource)
    await scope.resolve(GoodResource)

    with pytest.raises(ExceptionGroup) as exc_info:
        await scope.close()

    # Good resource was still cleaned up
    assert good.closed
    # ExceptionGroup contains the error from bad resource
    assert len(exc_info.value.exceptions) == 1
    assert "cleanup failed" in str(exc_info.value.exceptions[0])


async def test_scope_async_cleanup():
    resource = AsyncResource()
    providers = {
        (AsyncResource, None): FakeProvider(lambda: resource),
    }
    scope = Scope(providers)
    await scope.resolve(AsyncResource)
    await scope.close()
    assert resource.closed
