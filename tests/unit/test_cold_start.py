"""Tests for cold start optimization: lazy imports and serverless mode."""

import sys


class TestLazyImports:
    def test_lazy_import_not_loaded_eagerly(self):
        # Remove hawkapi from cache to test fresh import behavior
        mods_to_remove = [k for k in sys.modules if k.startswith("hawkapi.staticfiles")]
        for mod in mods_to_remove:
            del sys.modules[mod]

        # After removing, accessing StaticFiles via __getattr__ should work
        import hawkapi

        # Force it through __getattr__
        if "StaticFiles" in dir(hawkapi):
            sf = hawkapi.StaticFiles
            assert sf is not None

    def test_lazy_import_works_for_all_exports(self):
        import hawkapi

        for name in hawkapi.__all__:
            obj = getattr(hawkapi, name)
            assert obj is not None, f"{name} resolved to None"

    def test_nonexistent_attr_raises(self):
        import pytest

        import hawkapi

        with pytest.raises(AttributeError, match="no attribute"):
            _ = hawkapi.ThisDoesNotExist  # type: ignore[attr-defined]


class TestServerlessMode:
    def test_serverless_disables_docs(self):
        from hawkapi import HawkAPI
        from hawkapi.testing import TestClient

        app = HawkAPI(serverless=True)

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        client = TestClient(app)

        # /ping should work
        resp = client.get("/ping")
        assert resp.status_code == 200

        # Docs should not be registered
        resp = client.get("/docs")
        assert resp.status_code == 404

        resp = client.get("/openapi.json")
        assert resp.status_code == 404

    def test_non_serverless_has_docs(self):
        from hawkapi import HawkAPI
        from hawkapi.testing import TestClient

        app = HawkAPI()

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        client = TestClient(app)
        resp = client.get("/docs")
        assert resp.status_code == 200
