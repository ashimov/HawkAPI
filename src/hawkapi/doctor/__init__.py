"""hawkapi doctor — one-shot health-check CLI for HawkAPI applications."""

from __future__ import annotations

from hawkapi.doctor._formatter import exit_code, format_human, format_json
from hawkapi.doctor._runner import load_app, run
from hawkapi.doctor._types import Finding, Rule, Severity
from hawkapi.doctor.rules import ALL_RULES

__all__ = [
    "ALL_RULES",
    "Finding",
    "Rule",
    "Severity",
    "exit_code",
    "format_human",
    "format_json",
    "load_app",
    "run",
]
