"""Tests for OpenAPI specification linter."""

from hawkapi.openapi.linter import (
    LintIssue,
    Severity,
    format_lint_report,
    lint,
)


def _base_spec():
    """Return a clean OpenAPI spec with no lint issues."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1.0"},
        "paths": {
            "/users": {
                "get": {
                    "operationId": "list_users",
                    "summary": "List all users",
                    "responses": {
                        "200": {"description": "Successful response"},
                    },
                },
            },
            "/items": {
                "post": {
                    "operationId": "create_item",
                    "description": "Create a new item",
                    "responses": {
                        "201": {"description": "Created"},
                    },
                },
            },
        },
    }


class TestOperationIdRequired:
    def test_missing_operation_id_detected(self):
        spec = _base_spec()
        del spec["paths"]["/users"]["get"]["operationId"]
        issues = lint(spec)
        matching = [i for i in issues if i.rule == "operation-id-required"]
        assert len(matching) == 1
        assert matching[0].severity == Severity.ERROR
        assert matching[0].path == "/users"
        assert matching[0].method == "get"

    def test_present_operation_id_no_issue(self):
        spec = _base_spec()
        issues = lint(spec)
        matching = [i for i in issues if i.rule == "operation-id-required"]
        assert matching == []


class TestOperationSummaryRequired:
    def test_missing_summary_detected(self):
        spec = _base_spec()
        del spec["paths"]["/users"]["get"]["summary"]
        issues = lint(spec)
        matching = [i for i in issues if i.rule == "operation-summary-required"]
        assert len(matching) == 1
        assert matching[0].severity == Severity.WARNING
        assert matching[0].path == "/users"
        assert matching[0].method == "get"

    def test_description_satisfies_summary_rule(self):
        """Having description instead of summary should not trigger an issue."""
        spec = _base_spec()
        # /items post has description but no summary — should be fine
        issues = lint(spec)
        matching = [
            i for i in issues if i.rule == "operation-summary-required" and i.path == "/items"
        ]
        assert matching == []


class TestResponseDescriptionRequired:
    def test_missing_response_description_detected(self):
        spec = _base_spec()
        del spec["paths"]["/users"]["get"]["responses"]["200"]["description"]
        issues = lint(spec)
        matching = [i for i in issues if i.rule == "response-description-required"]
        assert len(matching) == 1
        assert matching[0].severity == Severity.WARNING
        assert matching[0].path == "/users"
        assert matching[0].method == "get"

    def test_present_response_description_no_issue(self):
        spec = _base_spec()
        issues = lint(spec)
        matching = [i for i in issues if i.rule == "response-description-required"]
        assert matching == []


class TestCleanSpec:
    def test_clean_spec_no_issues(self):
        spec = _base_spec()
        issues = lint(spec)
        assert issues == []

    def test_empty_spec_no_issues(self):
        spec: dict = {}
        issues = lint(spec)
        assert issues == []

    def test_spec_with_no_paths_no_issues(self):
        spec = {"openapi": "3.1.0", "info": {"title": "Test", "version": "1.0"}}
        issues = lint(spec)
        assert issues == []

    def test_spec_with_empty_paths_no_issues(self):
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test", "version": "1.0"},
            "paths": {},
        }
        issues = lint(spec)
        assert issues == []


class TestCustomRules:
    def test_lint_with_subset_of_rules(self):
        """Only the selected rules should run."""
        from hawkapi.openapi.linter import check_operation_id_required

        spec = _base_spec()
        del spec["paths"]["/users"]["get"]["operationId"]
        del spec["paths"]["/users"]["get"]["summary"]
        issues = lint(spec, rules=[check_operation_id_required])
        # Only operation-id-required should be reported, not summary
        assert all(i.rule == "operation-id-required" for i in issues)
        assert len(issues) == 1


class TestFormatLintReport:
    def test_no_issues(self):
        report = format_lint_report([])
        assert "No issues" in report

    def test_with_issues(self):
        issues = [
            LintIssue(
                rule="operation-id-required",
                severity=Severity.ERROR,
                path="/users",
                method="get",
                message="Operation is missing operationId",
            ),
            LintIssue(
                rule="operation-summary-required",
                severity=Severity.WARNING,
                path="/items",
                method="post",
                message="Operation is missing summary or description",
            ),
        ]
        report = format_lint_report(issues)
        assert "ERROR" in report
        assert "WARNING" in report
        assert "/users" in report
        assert "/items" in report
        assert "operation-id-required" in report


class TestExtensionFieldsIgnored:
    def test_extension_methods_skipped(self):
        """x- prefixed keys in paths should be ignored."""
        spec = _base_spec()
        spec["paths"]["/users"]["x-custom"] = {"some": "data"}
        issues = lint(spec)
        assert issues == []
