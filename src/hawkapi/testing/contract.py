"""Contract smoke test generator.

Reads application routes and produces contract test cases that can be
used to verify every registered endpoint returns its expected status code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContractTest:
    """A single contract test case."""

    name: str
    method: str
    path: str
    expected_status: int


def generate_contract_tests(app: Any) -> list[ContractTest]:
    """Generate contract test cases from an app's routes.

    Returns a list of :class:`ContractTest` for each registered route.
    Skips routes with path parameters (need sample values).
    Skips routes not included in schema.
    """
    tests: list[ContractTest] = []
    for route in app.routes:
        if not route.include_in_schema:
            continue
        for method in sorted(route.methods):
            if "{" in route.path:
                continue
            name = f"{method} {route.path} -> {route.status_code}"
            tests.append(
                ContractTest(
                    name=name,
                    method=method,
                    path=route.path,
                    expected_status=route.status_code,
                )
            )
    return tests
