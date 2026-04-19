"""Core types for hawkapi doctor: Severity, Finding, Rule Protocol."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI


class Severity(IntEnum):
    """Severity levels for doctor findings."""

    INFO = 1
    WARN = 2
    ERROR = 3


@dataclass(frozen=True, slots=True)
class Finding:
    """A single finding emitted by a doctor rule."""

    rule_id: str
    severity: Severity
    message: str
    fix: str | None = None
    location: str | None = None
    docs_url: str | None = None


@runtime_checkable
class Rule(Protocol):
    """Protocol that every doctor rule must satisfy."""

    id: str
    category: str
    severity: Severity
    title: str
    docs_url: str

    def check(self, app: HawkAPI) -> list[Finding]: ...


def docs_url(rule_id: str) -> str:
    """Return the canonical docs URL for a rule."""
    return f"https://hawkapi.ashimov.com/doctor/{rule_id}"
