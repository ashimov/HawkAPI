"""Generate Markdown changelog from OpenAPI diff changes."""

from __future__ import annotations

from hawkapi.openapi.breaking_changes import Change, Severity

_SEVERITY_HEADINGS: dict[Severity, str] = {
    Severity.BREAKING: "Breaking",
    Severity.WARNING: "Changed",
    Severity.INFO: "Info",
}

# Render order: most severe first.
_SEVERITY_ORDER: list[Severity] = [Severity.BREAKING, Severity.WARNING, Severity.INFO]


def generate_changelog(
    changes: list[Change],
    *,
    title: str = "API Changelog",
) -> str:
    """Generate a Markdown changelog from a list of API changes.

    Changes are grouped by severity under ``## Breaking``, ``## Changed``,
    and ``## Info`` headings.  Each change is rendered as a bullet point
    containing the HTTP method, path, and description.

    Parameters
    ----------
    changes:
        The list of :class:`Change` objects (typically produced by
        :func:`~hawkapi.openapi.breaking_changes.detect_breaking_changes`).
    title:
        The top-level ``# heading`` of the generated document.

    Returns
    -------
    str
        A Markdown-formatted changelog string.
    """
    if not changes:
        return f"# {title}\n\nNo changes detected.\n"

    grouped: dict[Severity, list[Change]] = {}
    for change in changes:
        grouped.setdefault(change.severity, []).append(change)

    lines: list[str] = [f"# {title}", ""]

    for severity in _SEVERITY_ORDER:
        group = grouped.get(severity)
        if not group:
            continue
        heading = _SEVERITY_HEADINGS[severity]
        lines.append(f"## {heading}")
        lines.append("")
        for change in group:
            lines.append(f"- **{change.method.upper()} {change.path}**: {change.description}")
        lines.append("")

    return "\n".join(lines)
