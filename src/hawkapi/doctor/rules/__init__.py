"""All doctor rules collected into a single static list."""

from __future__ import annotations

from typing import Any

from hawkapi.doctor.rules.correctness import CORRECTNESS_RULES
from hawkapi.doctor.rules.deps import DEPS_RULES
from hawkapi.doctor.rules.observability import OBSERVABILITY_RULES
from hawkapi.doctor.rules.performance import PERFORMANCE_RULES
from hawkapi.doctor.rules.security import SECURITY_RULES

ALL_RULES: list[Any] = (
    SECURITY_RULES + OBSERVABILITY_RULES + PERFORMANCE_RULES + CORRECTNESS_RULES + DEPS_RULES
)

__all__ = ["ALL_RULES"]
