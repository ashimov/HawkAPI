"""Orchestration: load app, run all rules, collect findings."""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, Any

from hawkapi.doctor._types import Finding, Severity

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI

logger = logging.getLogger("hawkapi.doctor")


def run(
    app: HawkAPI,
    rules: list[Any] | None = None,
    *,
    min_severity: Severity = Severity.INFO,
) -> list[Finding]:
    """Run all rules against *app* and return filtered findings.

    Each rule is wrapped in a try/except so a single broken rule never
    crashes the entire run — it emits an INFO finding instead.

    Parameters
    ----------
    app:
        The HawkAPI application instance to inspect.
    rules:
        List of rule objects to run. Defaults to ALL_RULES.
    min_severity:
        Only return findings at or above this severity level.
    """
    if rules is None:
        from hawkapi.doctor.rules import ALL_RULES

        rules = ALL_RULES

    all_findings: list[Finding] = []
    for rule in rules:
        try:
            findings = rule.check(app)
        except Exception as exc:
            tb = traceback.format_exc()
            logger.debug("Rule %s raised an exception:\n%s", rule.id, tb)
            findings = [
                Finding(
                    rule_id=rule.id,
                    severity=Severity.INFO,
                    message=f"Rule {rule.id} raised an exception: {exc!r}",
                    fix="Check the rule implementation or file a bug report.",
                )
            ]
        all_findings.extend(findings)

    return [f for f in all_findings if f.severity >= min_severity]


def load_app(module_path: str, attr_name: str) -> HawkAPI:
    """Import *module_path* and return the *attr_name* attribute.

    Raises SystemExit on import failure or missing attribute (mirrors the
    pattern used by the other CLI subcommands).
    """
    import importlib
    import sys

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        print(f"Error: could not import module '{module_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    app = getattr(module, attr_name, None)
    if app is None:
        print(
            f"Error: module '{module_path}' has no attribute '{attr_name}'",
            file=sys.stderr,
        )
        sys.exit(1)
    return app  # type: ignore[return-value]
