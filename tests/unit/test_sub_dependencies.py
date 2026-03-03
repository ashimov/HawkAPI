"""Tests for sub-dependencies (nested Depends)."""

from typing import Annotated

from hawkapi import Depends, HawkAPI
from hawkapi.testing import TestClient


def test_sub_dependency_default_value():
    """Depends as default value resolves recursively."""

    def get_db():
        return {"db": True}

    def get_service(db=Depends(get_db)):  # noqa: B008
        return {"service": True, "has_db": db["db"]}

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(svc: Annotated[dict, Depends(get_service)]):
        return svc

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json() == {"service": True, "has_db": True}


def test_sub_dependency_annotated():
    """Depends in Annotated resolves recursively."""

    def get_db():
        return {"db": True}

    def get_service(db: Annotated[dict, Depends(get_db)]):
        return {"service": True, "has_db": db["db"]}

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(svc: Annotated[dict, Depends(get_service)]):
        return svc

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json() == {"service": True, "has_db": True}


def test_three_level_chain():
    """Three-level dependency chain resolves correctly."""

    def get_config():
        return "postgres://localhost/db"

    def get_db(url=Depends(get_config)):  # noqa: B008
        return {"url": url}

    def get_repo(db=Depends(get_db)):  # noqa: B008
        return {"repo": True, "db_url": db["url"]}

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(repo: Annotated[dict, Depends(get_repo)]):
        return repo

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo"] is True
    assert data["db_url"] == "postgres://localhost/db"


def test_sub_dependency_with_request():
    """Sub-dependency can access the request object."""

    def get_token(request):
        return request.headers.get("authorization", "")

    def get_user(token=Depends(get_token)):  # noqa: B008
        return {"user": "admin"} if token == "Bearer secret" else {"user": "anon"}

    app = HawkAPI(openapi_url=None)

    @app.get("/me")
    async def handler(user: Annotated[dict, Depends(get_user)]):
        return user

    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": "Bearer secret"})
    assert resp.json() == {"user": "admin"}

    resp = client.get("/me")
    assert resp.json() == {"user": "anon"}


def test_sub_dependency_generator():
    """Generator sub-dependency cleans up correctly."""
    order: list[str] = []

    def get_db():
        order.append("db_open")
        yield {"db": True}
        order.append("db_close")

    def get_service(db=Depends(get_db)):  # noqa: B008
        return {"service": True, "has_db": db["db"]}

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(svc: Annotated[dict, Depends(get_service)]):
        return svc

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json() == {"service": True, "has_db": True}
    assert order == ["db_open", "db_close"]


def test_sub_dependency_async():
    """Async sub-dependency resolves correctly."""

    async def get_db():
        return {"db": True}

    async def get_service(db: Annotated[dict, Depends(get_db)]):
        return {"service": True, "has_db": db["db"]}

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(svc: Annotated[dict, Depends(get_service)]):
        return svc

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json() == {"service": True, "has_db": True}


def test_sub_dependency_with_default_param():
    """Sub-dep with non-Depends default uses that default."""

    def get_service(timeout: int = 30):
        return {"timeout": timeout}

    app = HawkAPI(openapi_url=None)

    @app.get("/test")
    async def handler(svc: Annotated[dict, Depends(get_service)]):
        return svc

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.json() == {"timeout": 30}
