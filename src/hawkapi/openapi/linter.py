"""OpenAPI specification linter with built-in rules."""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

# HTTP methods defined by the OpenAPI specification.
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


class Severity(enum.Enum):
    """Severity level for a lint issue."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class LintIssue:
    """A single lint issue found in an OpenAPI specification."""

    rule: str
    severity: Severity
    path: str
    method: str
    message: str


# ---------------------------------------------------------------------------
# Type alias for rule functions
# ---------------------------------------------------------------------------
RuleFunc = Callable[[dict[str, Any], str, str, dict[str, Any]], list[LintIssue]]


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------


def check_operation_id_required(
    spec: dict[str, Any],
    path: str,
    method: str,
    operation: dict[str, Any],
) -> list[LintIssue]:
    """operationId must be present on every operation."""
    if "operationId" not in operation:
        return [
            LintIssue(
                rule="operation-id-required",
                severity=Severity.ERROR,
                path=path,
                method=method,
                message="Operation is missing operationId",
            )
        ]
    return []


def check_operation_summary_required(
    spec: dict[str, Any],
    path: str,
    method: str,
    operation: dict[str, Any],
) -> list[LintIssue]:
    """Every operation should have a summary or description."""
    if "summary" not in operation and "description" not in operation:
        return [
            LintIssue(
                rule="operation-summary-required",
                severity=Severity.WARNING,
                path=path,
                method=method,
                message="Operation is missing summary or description",
            )
        ]
    return []


def check_response_description_required(
    spec: dict[str, Any],
    path: str,
    method: str,
    operation: dict[str, Any],
) -> list[LintIssue]:
    """Every response object must have a description."""
    issues: list[LintIssue] = []
    responses = operation.get("responses", {})
    for status_code, response in responses.items():
        if not isinstance(response, dict):
            continue
        if "description" not in response:
            issues.append(
                LintIssue(
                    rule="response-description-required",
                    severity=Severity.WARNING,
                    path=path,
                    method=method,
                    message=f"Response {status_code} is missing description",
                )
            )
    return issues


# Default set of built-in rules.
DEFAULT_RULES: list[RuleFunc] = [
    check_operation_id_required,
    check_operation_summary_required,
    check_response_description_required,
]


# ---------------------------------------------------------------------------
# Main lint function
# ---------------------------------------------------------------------------


def lint(
    spec: dict[str, Any],
    *,
    rules: list[RuleFunc] | None = None,
) -> list[LintIssue]:
    """Lint an OpenAPI specification.

    Parameters
    ----------
    spec:
        A parsed OpenAPI specification dictionary.
    rules:
        An optional list of rule functions to run.  When *None* the
        :data:`DEFAULT_RULES` are used.

    Returns
    -------
    list[LintIssue]
        All issues found by the selected rules.
    """
    if rules is None:
        rules = DEFAULT_RULES

    issues: list[LintIssue] = []
    paths: dict[str, Any] = spec.get("paths", {})

    for path_key in paths:
        methods_val: Any = paths[path_key]
        if not isinstance(methods_val, dict):
            continue
        methods = cast(dict[str, Any], methods_val)
        for method_name in methods:
            # Skip extension fields (x-...) and non-HTTP-method keys.
            if method_name not in _HTTP_METHODS:
                continue
            operation_val: Any = methods[method_name]
            if not isinstance(operation_val, dict):
                continue
            operation = cast(dict[str, Any], operation_val)
            for rule in rules:
                issues.extend(rule(spec, str(path_key), method_name, operation))

    return issues


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_lint_report(issues: list[LintIssue]) -> str:
    """Format lint issues into a human-readable report."""
    if not issues:
        return "No issues found."

    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos = [i for i in issues if i.severity == Severity.INFO]

    lines: list[str] = []

    if errors:
        lines.append(f"ERRORS ({len(errors)}):")
        for issue in errors:
            lines.append(f"  [{issue.method.upper()}] {issue.path}: {issue.message} ({issue.rule})")

    if warnings:
        lines.append(f"WARNINGS ({len(warnings)}):")
        for issue in warnings:
            lines.append(f"  [{issue.method.upper()}] {issue.path}: {issue.message} ({issue.rule})")

    if infos:
        lines.append(f"INFO ({len(infos)}):")
        for issue in infos:
            lines.append(f"  [{issue.method.upper()}] {issue.path}: {issue.message} ({issue.rule})")

    total = len(issues)
    lines.append("")
    lines.append(f"Found {total} issue{'s' if total != 1 else ''}.")

    return "\n".join(lines)
