"""Tests for the hawkapi-diff CLI subcommand."""

import types

from hawkapi import HawkAPI
from hawkapi.cli import _diff_specs, _load_app_spec
from hawkapi.openapi.breaking_changes import Severity


class TestDiffSpecs:
    def test_no_changes(self):
        spec = {
            "openapi": "3.1.0",
            "paths": {"/ping": {"get": {"responses": {"200": {}}}}},
        }
        changes = _diff_specs(spec, spec)
        assert len(changes) == 0

    def test_removed_endpoint_is_breaking(self):
        old = {
            "openapi": "3.1.0",
            "paths": {"/a": {"get": {"responses": {"200": {}}}}},
        }
        new = {"openapi": "3.1.0", "paths": {}}
        changes = _diff_specs(old, new)
        assert any(c.severity == Severity.BREAKING for c in changes)

    def test_added_endpoint_is_not_breaking(self):
        old = {"openapi": "3.1.0", "paths": {}}
        new = {
            "openapi": "3.1.0",
            "paths": {"/a": {"get": {"responses": {"200": {}}}}},
        }
        changes = _diff_specs(old, new)
        breaking = [c for c in changes if c.severity == Severity.BREAKING]
        assert len(breaking) == 0


class TestLoadAppSpec:
    def test_load_from_module(self):
        mod = types.ModuleType("_test_mod")
        app = HawkAPI(openapi_url=None)

        @app.get("/hello")
        async def hello():
            return {"msg": "hi"}

        mod.app = app  # type: ignore[attr-defined]
        spec = _load_app_spec(mod, "app")
        assert "/hello" in spec["paths"]
