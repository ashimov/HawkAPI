"""Tests for generator (yield) dependencies."""

from typing import Annotated

from hawkapi import Depends, HawkAPI
from hawkapi.testing import TestClient


def test_sync_generator_dependency():
    """Sync generator: code after yield runs after handler."""
    cleanup_ran = False

    def get_db():
        nonlocal cleanup_ran
        db = {"connection": True}
        yield db
        cleanup_ran = True

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(db: Annotated[dict, Depends(get_db)]):
        return {"connected": db["connection"]}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json() == {"connected": True}
    assert cleanup_ran


def test_async_generator_dependency():
    """Async generator: code after yield runs after handler."""
    cleanup_ran = False

    async def get_db():
        nonlocal cleanup_ran
        db = {"connection": True}
        yield db
        cleanup_ran = True

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(db: Annotated[dict, Depends(get_db)]):
        return {"connected": db["connection"]}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json() == {"connected": True}
    assert cleanup_ran


def test_generator_cleanup_on_handler_error():
    """Generator cleanup runs even when handler raises."""
    cleanup_ran = False

    async def get_resource():
        nonlocal cleanup_ran
        try:
            yield "resource"
        finally:
            cleanup_ran = True

    app = HawkAPI(openapi_url=None)

    @app.get("/fail")
    async def handler(res: Annotated[str, Depends(get_resource)]):
        raise ValueError("handler error")

    client = TestClient(app)
    resp = client.get("/fail")
    assert resp.status_code == 500
    assert cleanup_ran


def test_generator_cleanup_error_does_not_crash():
    """If cleanup code raises, it is logged but does not crash."""

    def bad_cleanup():
        yield "value"
        raise RuntimeError("cleanup failed")

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(val: Annotated[str, Depends(bad_cleanup)]):
        return {"val": val}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json() == {"val": "value"}


def test_multiple_generators_reverse_cleanup():
    """Multiple generators clean up in reverse order."""
    order: list[str] = []

    def dep_a():
        order.append("a_setup")
        yield "a"
        order.append("a_cleanup")

    def dep_b():
        order.append("b_setup")
        yield "b"
        order.append("b_cleanup")

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(
        a: Annotated[str, Depends(dep_a)],
        b: Annotated[str, Depends(dep_b)],
    ):
        return {"a": a, "b": b}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert order == ["a_setup", "b_setup", "b_cleanup", "a_cleanup"]


def test_generator_with_request_param():
    """Generator dependency can receive the request object."""

    async def get_auth(request):
        yield request.headers.get("authorization", "none")

    app = HawkAPI(openapi_url=None)

    @app.get("/auth")
    async def handler(auth: Annotated[str, Depends(get_auth)]):
        return {"auth": auth}

    client = TestClient(app)
    resp = client.get("/auth", headers={"Authorization": "Bearer token123"})
    assert resp.json() == {"auth": "Bearer token123"}
