"""Tests for the mypyc build gate in ``build_mypyc.py``.

The module lives at the repository root (not under ``src/``), so these tests
import it by adjusting ``sys.path`` instead of relying on the installed package.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def build_mypyc(monkeypatch: pytest.MonkeyPatch):
    """Import ``build_mypyc`` from the project root with a clean cache."""
    monkeypatch.syspath_prepend(str(PROJECT_ROOT))
    sys.modules.pop("build_mypyc", None)
    module = importlib.import_module("build_mypyc")
    yield module
    sys.modules.pop("build_mypyc", None)


def test_is_enabled_false_when_env_unset(
    build_mypyc, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HAWKAPI_BUILD_MYPYC", raising=False)
    assert build_mypyc.is_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_is_enabled_true_when_env_set_and_gil_on(
    build_mypyc, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("HAWKAPI_BUILD_MYPYC", value)
    # Simulate a GIL-enabled interpreter (the default everywhere today).
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: True, raising=False)
    assert build_mypyc.is_enabled() is True


def test_is_enabled_false_on_free_threaded_even_when_env_set(
    build_mypyc, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Free-threaded interpreters must never build mypyc extensions."""
    monkeypatch.setenv("HAWKAPI_BUILD_MYPYC", "1")
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: False, raising=False)
    assert build_mypyc.is_enabled() is False
    captured = capsys.readouterr()
    assert "free-threaded" in captured.err.lower()
