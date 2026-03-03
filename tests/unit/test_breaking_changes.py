"""Tests for OpenAPI breaking changes detector."""

from hawkapi.openapi.breaking_changes import (
    Change,
    ChangeType,
    Severity,
    detect_breaking_changes,
    format_report,
)


def _base_spec():
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1.0"},
        "paths": {
            "/users": {
                "get": {
                    "parameters": [
                        {
                            "name": "page",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "integer"},
                                            "name": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/items": {
                "get": {"responses": {"200": {"description": "OK"}}},
                "post": {"responses": {"201": {"description": "Created"}}},
            },
        },
    }


class TestDetectBreakingChanges:
    def test_no_changes(self):
        spec = _base_spec()
        changes = detect_breaking_changes(spec, spec)
        assert changes == []

    def test_path_removed(self):
        old = _base_spec()
        new = _base_spec()
        del new["paths"]["/items"]
        changes = detect_breaking_changes(old, new)
        path_removed = [c for c in changes if c.type == ChangeType.PATH_REMOVED]
        assert len(path_removed) == 2  # get + post
        assert all(c.severity == Severity.BREAKING for c in path_removed)

    def test_method_removed(self):
        old = _base_spec()
        new = _base_spec()
        del new["paths"]["/items"]["post"]
        changes = detect_breaking_changes(old, new)
        method_removed = [c for c in changes if c.type == ChangeType.METHOD_REMOVED]
        assert len(method_removed) == 1
        assert method_removed[0].method == "post"

    def test_required_parameter_added(self):
        old = _base_spec()
        new = _base_spec()
        new["paths"]["/users"]["get"]["parameters"].append(
            {"name": "filter", "in": "query", "required": True, "schema": {"type": "string"}}
        )
        changes = detect_breaking_changes(old, new)
        added = [c for c in changes if c.type == ChangeType.PARAMETER_ADDED_REQUIRED]
        assert len(added) == 1
        assert added[0].new_value == "filter"

    def test_parameter_removed(self):
        old = _base_spec()
        new = _base_spec()
        new["paths"]["/users"]["get"]["parameters"] = []
        changes = detect_breaking_changes(old, new)
        removed = [c for c in changes if c.type == ChangeType.PARAMETER_REMOVED]
        assert len(removed) == 1
        assert removed[0].old_value == "page"

    def test_parameter_type_changed(self):
        old = _base_spec()
        new = _base_spec()
        new["paths"]["/users"]["get"]["parameters"][0]["schema"]["type"] = "string"
        changes = detect_breaking_changes(old, new)
        typed = [c for c in changes if c.type == ChangeType.PARAMETER_TYPE_CHANGED]
        assert len(typed) == 1
        assert typed[0].old_value == "integer"
        assert typed[0].new_value == "string"

    def test_response_status_removed(self):
        old = _base_spec()
        new = _base_spec()
        new["paths"]["/users"]["get"]["responses"] = {"201": {"description": "Created"}}
        changes = detect_breaking_changes(old, new)
        status_changed = [c for c in changes if c.type == ChangeType.STATUS_CODE_CHANGED]
        assert len(status_changed) == 1

    def test_response_field_removed(self):
        old = _base_spec()
        new = _base_spec()
        props = new["paths"]["/users"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["properties"]
        del props["name"]
        changes = detect_breaking_changes(old, new)
        field_removed = [c for c in changes if c.type == ChangeType.RESPONSE_FIELD_REMOVED]
        assert len(field_removed) == 1
        assert field_removed[0].old_value == "name"


class TestFormatReport:
    def test_empty(self):
        assert format_report([]) == "No breaking changes detected."

    def test_with_breaking_and_warnings(self):
        changes = [
            Change(
                type=ChangeType.PATH_REMOVED,
                severity=Severity.BREAKING,
                path="/users",
                method="get",
                description="Path /users was removed",
            ),
            Change(
                type=ChangeType.STATUS_CODE_CHANGED,
                severity=Severity.WARNING,
                path="/items",
                method="get",
                description="Response status 200 was removed",
            ),
        ]
        report = format_report(changes)
        assert "BREAKING CHANGES (1):" in report
        assert "WARNINGS (1):" in report
        assert "/users" in report
        assert "/items" in report
