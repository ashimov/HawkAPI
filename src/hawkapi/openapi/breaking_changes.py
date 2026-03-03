"""Breaking changes detection between two OpenAPI specifications."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ChangeType(Enum):
    """Type of API change detected."""

    PATH_REMOVED = "path_removed"
    METHOD_REMOVED = "method_removed"
    PARAMETER_ADDED_REQUIRED = "parameter_added_required"
    PARAMETER_REMOVED = "parameter_removed"
    PARAMETER_TYPE_CHANGED = "parameter_type_changed"
    RESPONSE_FIELD_REMOVED = "response_field_removed"
    STATUS_CODE_CHANGED = "status_code_changed"


class Severity(Enum):
    """Severity of the detected change."""

    BREAKING = "breaking"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Change:
    """A single detected API change."""

    type: ChangeType
    severity: Severity
    path: str
    method: str
    description: str
    old_value: Any = None
    new_value: Any = None


def detect_breaking_changes(
    old_spec: dict[str, Any],
    new_spec: dict[str, Any],
) -> list[Change]:
    """Compare two OpenAPI specs and return a list of detected changes."""
    changes: list[Change] = []

    old_paths = old_spec.get("paths", {})
    new_paths = new_spec.get("paths", {})

    for path, old_methods in old_paths.items():
        if path not in new_paths:
            for method in old_methods:
                if method.startswith("x-"):
                    continue
                changes.append(
                    Change(
                        type=ChangeType.PATH_REMOVED,
                        severity=Severity.BREAKING,
                        path=path,
                        method=method,
                        description=f"Path {path} was removed",
                    )
                )
            continue

        new_methods = new_paths[path]
        for method, old_op in old_methods.items():
            if method.startswith("x-"):
                continue
            if method not in new_methods:
                changes.append(
                    Change(
                        type=ChangeType.METHOD_REMOVED,
                        severity=Severity.BREAKING,
                        path=path,
                        method=method,
                        description=f"Method {method.upper()} removed from {path}",
                    )
                )
                continue

            new_op = new_methods[method]
            changes.extend(_compare_operation(path, method, old_op, new_op))

    return changes


def _compare_operation(
    path: str,
    method: str,
    old_op: dict[str, Any],
    new_op: dict[str, Any],
) -> list[Change]:
    """Compare two operations and detect breaking changes."""
    changes: list[Change] = []

    # Compare parameters
    old_params = {p["name"]: p for p in old_op.get("parameters", [])}
    new_params = {p["name"]: p for p in new_op.get("parameters", [])}

    for name in old_params:
        if name not in new_params:
            changes.append(
                Change(
                    type=ChangeType.PARAMETER_REMOVED,
                    severity=Severity.BREAKING,
                    path=path,
                    method=method,
                    description=f"Parameter '{name}' was removed",
                    old_value=name,
                )
            )

    for name, param in new_params.items():
        if name not in old_params and param.get("required"):
            changes.append(
                Change(
                    type=ChangeType.PARAMETER_ADDED_REQUIRED,
                    severity=Severity.BREAKING,
                    path=path,
                    method=method,
                    description=f"Required parameter '{name}' was added",
                    new_value=name,
                )
            )

    for name in old_params:
        if name in new_params:
            old_type = old_params[name].get("schema", {}).get("type")
            new_type = new_params[name].get("schema", {}).get("type")
            if old_type and new_type and old_type != new_type:
                changes.append(
                    Change(
                        type=ChangeType.PARAMETER_TYPE_CHANGED,
                        severity=Severity.BREAKING,
                        path=path,
                        method=method,
                        description=f"Parameter '{name}': '{old_type}' -> '{new_type}'",
                        old_value=old_type,
                        new_value=new_type,
                    )
                )

    # Compare response status codes
    old_responses = old_op.get("responses", {})
    new_responses = new_op.get("responses", {})

    for status in old_responses:
        if status not in new_responses:
            changes.append(
                Change(
                    type=ChangeType.STATUS_CODE_CHANGED,
                    severity=Severity.WARNING,
                    path=path,
                    method=method,
                    description=f"Response status {status} was removed",
                    old_value=status,
                )
            )

    # Compare response schema fields
    for status in old_responses:
        if status not in new_responses:
            continue
        old_schema = _extract_response_schema(old_responses[status])
        new_schema = _extract_response_schema(new_responses[status])
        if old_schema and new_schema:
            old_props = old_schema.get("properties", {})
            new_props = new_schema.get("properties", {})
            for field_name in old_props:
                if field_name not in new_props:
                    changes.append(
                        Change(
                            type=ChangeType.RESPONSE_FIELD_REMOVED,
                            severity=Severity.WARNING,
                            path=path,
                            method=method,
                            description=f"Response field '{field_name}' was removed",
                            old_value=field_name,
                        )
                    )

    return changes


def _extract_response_schema(response: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the JSON schema from a response object."""
    content = response.get("content", {})
    json_content = content.get("application/json", {})
    return json_content.get("schema")


def format_report(changes: list[Change]) -> str:
    """Format changes into a human-readable report."""
    if not changes:
        return "No breaking changes detected."

    breaking = [c for c in changes if c.severity == Severity.BREAKING]
    warnings = [c for c in changes if c.severity == Severity.WARNING]

    lines: list[str] = []

    if breaking:
        lines.append(f"BREAKING CHANGES ({len(breaking)}):")
        for c in breaking:
            lines.append(f"  - [{c.method.upper()}] {c.path}: {c.description}")

    if warnings:
        lines.append(f"WARNINGS ({len(warnings)}):")
        for c in warnings:
            lines.append(f"  - [{c.method.upper()}] {c.path}: {c.description}")

    return "\n".join(lines)
