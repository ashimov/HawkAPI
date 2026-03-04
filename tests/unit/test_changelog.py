"""Tests for the Markdown changelog generator."""

from hawkapi.openapi.breaking_changes import Change, ChangeType, Severity
from hawkapi.openapi.changelog import generate_changelog


class TestGenerateChangelog:
    """Tests for generate_changelog()."""

    def test_empty_changes_returns_no_changes_message(self):
        result = generate_changelog([])
        assert "# API Changelog" in result
        assert "No changes detected." in result

    def test_custom_title(self):
        result = generate_changelog([], title="v2.0 Changes")
        assert "# v2.0 Changes" in result
        assert "No changes detected." in result

    def test_breaking_change_listed_under_breaking_heading(self):
        changes = [
            Change(
                type=ChangeType.PATH_REMOVED,
                severity=Severity.BREAKING,
                path="/users",
                method="get",
                description="Path /users was removed",
            ),
        ]
        result = generate_changelog(changes)
        assert "## Breaking" in result
        assert "**GET /users**" in result
        assert "Path /users was removed" in result

    def test_warning_change_listed_under_changed_heading(self):
        changes = [
            Change(
                type=ChangeType.STATUS_CODE_CHANGED,
                severity=Severity.WARNING,
                path="/items",
                method="get",
                description="Response status 200 was removed",
                old_value="200",
            ),
        ]
        result = generate_changelog(changes)
        assert "## Changed" in result
        assert "**GET /items**" in result
        assert "Response status 200 was removed" in result

    def test_info_change_listed_under_info_heading(self):
        changes = [
            Change(
                type=ChangeType.PATH_REMOVED,
                severity=Severity.INFO,
                path="/health",
                method="get",
                description="Deprecated endpoint removed",
            ),
        ]
        result = generate_changelog(changes)
        assert "## Info" in result
        assert "**GET /health**" in result

    def test_multiple_severity_types_grouped_correctly(self):
        changes = [
            Change(
                type=ChangeType.PATH_REMOVED,
                severity=Severity.BREAKING,
                path="/users",
                method="delete",
                description="Path /users was removed",
            ),
            Change(
                type=ChangeType.STATUS_CODE_CHANGED,
                severity=Severity.WARNING,
                path="/items",
                method="get",
                description="Response status 200 was removed",
                old_value="200",
            ),
            Change(
                type=ChangeType.PARAMETER_REMOVED,
                severity=Severity.BREAKING,
                path="/orders",
                method="post",
                description="Parameter 'filter' was removed",
                old_value="filter",
            ),
            Change(
                type=ChangeType.PATH_REMOVED,
                severity=Severity.INFO,
                path="/debug",
                method="get",
                description="Debug endpoint removed",
            ),
        ]
        result = generate_changelog(changes)

        # All three severity headings present
        assert "## Breaking" in result
        assert "## Changed" in result
        assert "## Info" in result

        # Breaking appears before Changed, Changed before Info
        breaking_pos = result.index("## Breaking")
        changed_pos = result.index("## Changed")
        info_pos = result.index("## Info")
        assert breaking_pos < changed_pos < info_pos

        # Both breaking changes present under Breaking
        assert "**DELETE /users**" in result
        assert "**POST /orders**" in result

        # Warning change under Changed
        assert "**GET /items**" in result

        # Info change under Info
        assert "**GET /debug**" in result

    def test_method_uppercased_in_output(self):
        changes = [
            Change(
                type=ChangeType.METHOD_REMOVED,
                severity=Severity.BREAKING,
                path="/users",
                method="post",
                description="Method POST removed from /users",
            ),
        ]
        result = generate_changelog(changes)
        assert "**POST /users**" in result

    def test_no_empty_sections_for_missing_severities(self):
        """Only severity headings with changes should appear."""
        changes = [
            Change(
                type=ChangeType.STATUS_CODE_CHANGED,
                severity=Severity.WARNING,
                path="/items",
                method="get",
                description="Response status 200 was removed",
                old_value="200",
            ),
        ]
        result = generate_changelog(changes)
        assert "## Changed" in result
        assert "## Breaking" not in result
        assert "## Info" not in result
