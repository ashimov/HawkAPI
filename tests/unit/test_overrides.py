"""Tests for scoped DI overrides."""

from hawkapi import HawkAPI
from hawkapi.di import Container
from hawkapi.testing import TestClient, override


class ItemStore:
    def __init__(self, items=None):
        self.items = items or []


def test_override_with_app():
    container = Container()
    container.singleton(ItemStore, factory=lambda: ItemStore([1, 2, 3]))
    app = HawkAPI(openapi_url=None, container=container)

    @app.get("/items")
    async def items(store: ItemStore):
        return {"items": store.items}

    with override(app, {ItemStore: lambda: ItemStore([99])}):
        client = TestClient(app)
        resp = client.get("/items")
        assert resp.json() == {"items": [99]}

    # After override, original is restored
    client = TestClient(app)
    resp = client.get("/items")
    assert resp.json() == {"items": [1, 2, 3]}


def test_override_with_container():
    container = Container()
    container.singleton(ItemStore, factory=lambda: ItemStore(["original"]))

    with override(container, {ItemStore: lambda: ItemStore(["mock"])}):
        pass  # Just verify context manager works
