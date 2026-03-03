"""Tests for sub-app docs isolation."""

from hawkapi import HawkAPI
from hawkapi.testing import TestClient


def test_subapp_docs_accessible():
    main_app = HawkAPI(title="Main", openapi_url=None)
    sub_app = HawkAPI(title="SubApp")

    @sub_app.get("/items")
    async def items():
        return []

    main_app.mount("/api", sub_app)

    client = TestClient(main_app)
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    assert "SubApp" in resp.text


def test_subapp_openapi_has_servers():
    main_app = HawkAPI(title="Main", openapi_url=None)
    sub_app = HawkAPI(title="SubApp")

    @sub_app.get("/items")
    async def items():
        return []

    main_app.mount("/api", sub_app)

    client = TestClient(main_app)
    resp = client.get("/api/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "servers" in data
    assert data["servers"][0]["url"] == "/api"


def test_main_app_no_servers_field():
    app = HawkAPI(title="Main")

    @app.get("/hello")
    async def hello():
        return {"msg": "hi"}

    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "servers" not in data


def test_subapp_swagger_ui_references_correct_url():
    main_app = HawkAPI(title="Main", openapi_url=None)
    sub_app = HawkAPI(title="SubApp")

    @sub_app.get("/items")
    async def items():
        return []

    main_app.mount("/api", sub_app)

    client = TestClient(main_app)
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    assert "/api/openapi.json" in resp.text
