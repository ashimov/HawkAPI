"""Dependency rules: DOC050–DOC051."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hawkapi.doctor._types import Finding, Severity, docs_url

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI


def _parse_version(ver: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of ints for comparison."""
    parts: list[int] = []
    for segment in ver.split(".")[:3]:
        try:
            parts.append(int(segment))
        except ValueError:
            break
    return tuple(parts)


@dataclass(frozen=True, slots=True)
class _DOC050:
    id: str = "DOC050"
    category: str = "deps"
    severity: Severity = Severity.INFO
    title: str = "HawkAPI version older than latest published on PyPI"
    docs_url: str = docs_url("DOC050")

    def check(self, app: HawkAPI) -> list[Finding]:
        import hawkapi

        current = getattr(hawkapi, "__version__", None)
        if not current:
            return []
        try:
            req = urllib.request.Request(
                "https://pypi.org/pypi/hawkapi/json",
                headers={"User-Agent": "hawkapi-doctor/1"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310
                data: dict[str, Any] = json.loads(resp.read())
            latest: str = data["info"]["version"]
        except Exception:
            return []
        if _parse_version(current) < _parse_version(latest):
            return [
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"hawkapi {current} is installed but {latest} is available on PyPI.",
                    fix=f"Run: pip install --upgrade hawkapi=={latest}",
                    docs_url=self.docs_url,
                )
            ]
        return []


@dataclass(frozen=True, slots=True)
class _DOC051:
    id: str = "DOC051"
    category: str = "deps"
    severity: Severity = Severity.WARN
    title: str = "msgspec version < 0.19"
    docs_url: str = docs_url("DOC051")

    def check(self, app: HawkAPI) -> list[Finding]:
        try:
            import msgspec  # pyright: ignore[reportMissingImports]

            ver_str: str = getattr(msgspec, "__version__", "0.0.0")
            ver = _parse_version(ver_str)
        except ImportError:
            return []
        if ver[:2] < (0, 19):
            return [
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"msgspec {ver_str} is installed; version < 0.19 has "
                    "known performance gaps.",
                    fix="Run: pip install --upgrade 'msgspec>=0.19'",
                    docs_url=self.docs_url,
                )
            ]
        return []


DOC050 = _DOC050()
DOC051 = _DOC051()

DEPS_RULES: list[Any] = [DOC050, DOC051]
