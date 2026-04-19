"""Human-readable and JSON output formatters for doctor findings."""

from __future__ import annotations

import json
import sys
from typing import Any

from hawkapi.doctor._types import Finding, Severity

# ANSI colour codes — only applied when stdout is a TTY.
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RESET = "\033[0m"

_EMOJI = {
    Severity.ERROR: "✗",
    Severity.WARN: "⚠",
    Severity.INFO: "ℹ",
}


def _colour(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


def _severity_colour(sev: Severity) -> str:
    if sev == Severity.ERROR:
        return _RED
    if sev == Severity.WARN:
        return _YELLOW
    return _CYAN


def exit_code(findings: list[Finding]) -> int:
    """Return the appropriate exit code for the given findings list."""
    if any(f.severity == Severity.ERROR for f in findings):
        return 2
    if any(f.severity == Severity.WARN for f in findings):
        return 1
    return 0


def format_human(findings: list[Finding], app_spec: str) -> str:
    """Render findings as a human-readable report grouped by severity."""
    lines: list[str] = []
    lines.append(f"hawkapi doctor — {app_spec}")
    lines.append("")

    if not findings:
        lines.append("No findings. All checks passed.")
        lines.append("")
        lines.append("Summary: 0 errors, 0 warnings, 0 info · exit 0")
        return "\n".join(lines)

    ordered = sorted(findings, key=lambda f: -f.severity)

    for finding in ordered:
        emoji = _EMOJI[finding.severity]
        col = _severity_colour(finding.severity)
        loc = finding.location or finding.rule_id
        header = _colour(f"{emoji}  {finding.rule_id}  {loc}", col)
        lines.append(header)
        lines.append(f"   {finding.message}")
        if finding.fix:
            lines.append(f"   Fix: {finding.fix}")
        if finding.docs_url:
            lines.append(f"   {finding.docs_url}")
        lines.append("")

    errors = sum(1 for f in findings if f.severity == Severity.ERROR)
    warnings = sum(1 for f in findings if f.severity == Severity.WARN)
    info = sum(1 for f in findings if f.severity == Severity.INFO)
    code = exit_code(findings)
    lines.append(
        f"Summary: {errors} error{'s' if errors != 1 else ''}, "
        f"{warnings} warning{'s' if warnings != 1 else ''}, "
        f"{info} info · exit {code}"
    )
    return "\n".join(lines)


def format_json(findings: list[Finding], app_spec: str) -> str:
    """Render findings as a stable JSON document."""
    errors = sum(1 for f in findings if f.severity == Severity.ERROR)
    warnings = sum(1 for f in findings if f.severity == Severity.WARN)
    info = sum(1 for f in findings if f.severity == Severity.INFO)

    _SEV_STR: dict[Severity, str] = {
        Severity.ERROR: "error",
        Severity.WARN: "warning",
        Severity.INFO: "info",
    }

    payload: dict[str, Any] = {
        "app": app_spec,
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "total": len(findings),
        },
        "findings": [
            {
                "rule_id": f.rule_id,
                "severity": _SEV_STR[f.severity],
                "message": f.message,
                "fix": f.fix,
                "location": f.location,
                "docs_url": f.docs_url,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2)
