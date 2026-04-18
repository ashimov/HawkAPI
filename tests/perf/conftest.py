"""Conftest for memory budget tests.

Responsibilities:
* Auto-skip memory-marked tests when ``pytest-memray`` is not installed
  (e.g., on Windows where the plugin is not supported).
* Compare peak memory of each memory-marked test against a recorded
  baseline (``tests/perf/baseline.json``) and fail when usage grows by
  more than ``MEMORY_REGRESSION_THRESHOLD`` (default 10%).

Baseline file format (JSON)::

    {
      "schema": 1,
      "tests": {
        "tests/perf/test_memory_budget.py::test_app_init_memory_budget": {
          "peak_bytes": 1234567,
          "recorded_at": "2026-04-17T00:00:00Z"
        }
      }
    }

To regenerate the baseline (e.g., after an intentional memory change), run::

    UPDATE_MEMORY_BASELINE=1 uv run pytest tests/perf/ -m memory --memray -v
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any

import pytest

BASELINE_PATH = Path(__file__).parent / "baseline.json"
MEMORY_REGRESSION_THRESHOLD = 0.10  # 10%


def _has_memray() -> bool:
    try:
        import pytest_memray  # noqa: F401  # type: ignore[import-not-found]
    except Exception:
        return False
    return True


HAS_MEMRAY = _has_memray()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip memory-marked tests when pytest-memray is unavailable."""
    if HAS_MEMRAY:
        return
    skip_marker = pytest.mark.skip(
        reason="pytest-memray is not installed (unsupported on this platform)"
    )
    for item in items:
        if "memory" in item.keywords:
            item.add_marker(skip_marker)


def _load_baseline() -> dict[str, Any]:
    if not BASELINE_PATH.exists():
        return {"schema": 1, "tests": {}}
    try:
        data: dict[str, Any] = json.loads(BASELINE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "tests": {}}
    data.setdefault("schema", 1)
    data.setdefault("tests", {})
    return data


def _save_baseline(data: dict[str, Any]) -> None:
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _peak_bytes_for(item: pytest.Item) -> int | None:
    """Extract peak memory (bytes) recorded by pytest-memray for ``item``.

    pytest-memray exposes a ``Manager`` plugin registered as
    ``memray_manager``; its ``results`` dict maps ``nodeid -> Result``,
    where ``result.metadata.peak_memory`` is bytes (int).
    """
    manager = item.config.pluginmanager.get_plugin("memray_manager")
    if manager is None:
        return None
    results = getattr(manager, "results", None)
    if not results:
        return None
    result = results.get(item.nodeid)
    if result is None:
        return None
    metadata = getattr(result, "metadata", None)
    if metadata is None:
        return None
    peak = getattr(metadata, "peak_memory", None)
    if peak is None:
        return None
    try:
        return int(peak)
    except (TypeError, ValueError):
        return None


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item) -> None:
    """Compare measured peak memory to baseline and fail on regression."""
    if not HAS_MEMRAY:
        return
    if "memory" not in item.keywords:
        return

    peak = _peak_bytes_for(item)
    if peak is None:
        return

    baseline = _load_baseline()
    update = os.environ.get("UPDATE_MEMORY_BASELINE") == "1"
    nodeid = item.nodeid
    record = baseline["tests"].get(nodeid)

    if update or record is None:
        baseline["tests"][nodeid] = {
            "peak_bytes": peak,
            "recorded_at": _dt.datetime.now(_dt.UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        _save_baseline(baseline)
        return

    prior = int(record.get("peak_bytes", 0))
    if prior <= 0:
        return

    growth = (peak - prior) / prior
    if growth > MEMORY_REGRESSION_THRESHOLD:
        pct = growth * 100.0
        pytest.fail(
            f"Memory regression: {nodeid} peaked at {peak:,} B "
            f"vs baseline {prior:,} B (+{pct:.1f}% > "
            f"{MEMORY_REGRESSION_THRESHOLD * 100:.0f}%). "
            "If intentional, regenerate the baseline with "
            "UPDATE_MEMORY_BASELINE=1.",
            pytrace=False,
        )
