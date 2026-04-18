# Tier 1 — Free-threaded Python 3.13 wheels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `cp313t` (PEP 703 free-threaded) wheels for HawkAPI plus an experimental non-blocking CI job, with mypyc auto-skipping on free-threaded interpreters.

**Architecture:** The "should mypyc compile?" decision moves from cibuildwheel env branching into `build_mypyc.is_enabled()` — it auto-disables when `sys._is_gil_enabled()` returns `False`. CI config stays declarative: one `HAWKAPI_BUILD_MYPYC=1` env var for all builds, the build script self-selects. Free-threaded CI job is separate from the main matrix and marked non-blocking.

**Tech Stack:** CPython 3.13 (GIL + free-threaded), mypyc, cibuildwheel 2.21.x, hatchling, uv, GitHub Actions, MkDocs Material.

**Spec:** [docs/plans/2026-04-18-tier1-freethreaded-design.md](2026-04-18-tier1-freethreaded-design.md)

---

## File Structure

Files touched by this plan and their single responsibility:

| File | Responsibility | New/Modified |
|---|---|---|
| `build_mypyc.py` | mypyc compilation entry point; now also guards against free-threaded interpreters | Modified |
| `tests/unit/test_build_mypyc.py` | Covers `is_enabled()` behaviour across env var and interpreter variants | New |
| `src/hawkapi/_threading.py` | Free-threaded detection + null-lock helpers (already exists, unchanged) | Unchanged |
| `tests/unit/test_threading.py` | Covers `FREE_THREADED`, `maybe_thread_lock`, `maybe_async_lock` | New |
| `.github/workflows/wheels.yml` | cibuildwheel configuration; extended to build `cp313t-*` | Modified |
| `.github/workflows/ci.yml` | CI matrix; new experimental `test-free-threaded` job | Modified |
| `pyproject.toml` | PEP 779 trove classifier for free-threaded support | Modified |
| `docs/guide/free-threaded.md` | User-facing guide — install, status, limitations | New |
| `mkdocs.yml` | Nav entry for the new guide page | Modified |

---

## Task 1: Write failing tests for `build_mypyc.is_enabled()`

**Files:**
- Test: `tests/unit/test_build_mypyc.py` (new)

Tests the invariants of `is_enabled()` — env var gates compilation, and a free-threaded interpreter forces it off even when the env var is set.

- [ ] **Step 1: Create the test file with three tests**

Create `tests/unit/test_build_mypyc.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_build_mypyc.py -v`

Expected: `test_is_enabled_false_on_free_threaded_even_when_env_set` **FAILS** (current `is_enabled()` ignores `_is_gil_enabled`). The other two pass today.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/unit/test_build_mypyc.py
git commit -m "test: cover is_enabled() gating for HAWKAPI_BUILD_MYPYC and free-threaded"
```

---

## Task 2: Make `is_enabled()` auto-skip on free-threaded builds

**Files:**
- Modify: `build_mypyc.py:43-50`

- [ ] **Step 1: Add `sys` import and rewrite `is_enabled()`**

At the top of `build_mypyc.py`, update the import block to include `sys`:

```python
from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any
```

Replace the existing `is_enabled()` function with:

```python
def is_enabled() -> bool:
    """Return True when mypyc compilation has been opted into.

    mypyc-compiled extensions require the GIL. On a PEP 703 free-threaded
    CPython build (``python3.13t``), ``sys._is_gil_enabled()`` returns
    ``False`` — we skip compilation in that case even when the env var is set,
    and warn on stderr so the build log explains the decision.
    """
    if os.environ.get("HAWKAPI_BUILD_MYPYC", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False

    is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
    if is_gil_enabled is not None and not is_gil_enabled():
        print(
            "HAWKAPI_BUILD_MYPYC is set but the interpreter is free-threaded; "
            "skipping mypyc compilation.",
            file=sys.stderr,
        )
        return False

    return True
```

- [ ] **Step 2: Run tests to verify all three pass**

Run: `uv run pytest tests/unit/test_build_mypyc.py -v`

Expected: all three tests PASS.

- [ ] **Step 3: Sanity-check the pure-Python build path**

Run: `HAWKAPI_BUILD_MYPYC= uv build --wheel 2>&1 | tail -5`

Expected: a pure-Python wheel named like `hawkapi-0.1.2-py3-none-any.whl` is produced. This confirms the default opt-out path is unchanged.

- [ ] **Step 4: Commit**

```bash
git add build_mypyc.py
git commit -m "build: auto-skip mypyc on free-threaded CPython (PEP 703)"
```

---

## Task 3: Write tests for the `_threading` helpers

**Files:**
- Test: `tests/unit/test_threading.py` (new)

The `src/hawkapi/_threading.py` module ships today with no dedicated tests. Adding coverage makes the free-threaded CI job meaningful.

- [ ] **Step 1: Create the test file**

Create `tests/unit/test_threading.py`:

```python
"""Tests for ``hawkapi._threading`` — PEP 703 detection + null-lock helpers."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
import threading

import pytest

from hawkapi import _threading


def test_free_threaded_matches_is_gil_enabled() -> None:
    """``FREE_THREADED`` must reflect the interpreter's actual GIL state."""
    is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
    if is_gil_enabled is None:
        assert _threading.FREE_THREADED is False
    else:
        assert _threading.FREE_THREADED is (not is_gil_enabled())


def test_maybe_thread_lock_returns_nullcontext_under_gil(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_threading, "FREE_THREADED", False)
    ctx = _threading.maybe_thread_lock()
    assert isinstance(ctx, contextlib.nullcontext)
    with ctx:
        pass  # no-op must not raise


def test_maybe_thread_lock_returns_real_lock_under_free_threaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_threading, "FREE_THREADED", True)
    lock = _threading.maybe_thread_lock()
    assert isinstance(lock, type(threading.Lock()))
    with lock:
        pass


def test_maybe_async_lock_is_noop_under_gil(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_threading, "FREE_THREADED", False)
    lock = _threading.maybe_async_lock()

    async def use() -> bool:
        async with lock:
            return True

    assert asyncio.run(use()) is True
    # Null async lock must never report being held.
    assert lock.locked() is False


def test_maybe_async_lock_returns_real_lock_under_free_threaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_threading, "FREE_THREADED", True)
    lock = _threading.maybe_async_lock()
    assert isinstance(lock, asyncio.Lock)


def test_detect_free_threaded_handles_missing_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On interpreters without ``sys._is_gil_enabled``, detection returns False."""
    monkeypatch.delattr(sys, "_is_gil_enabled", raising=False)
    fresh = importlib.reload(_threading)
    try:
        assert fresh.FREE_THREADED is False
    finally:
        importlib.reload(_threading)  # restore original module state
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_threading.py -v`

Expected: all six tests PASS. They exercise both branches of the helper without needing an actual free-threaded interpreter (they monkeypatch `FREE_THREADED`).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_threading.py
git commit -m "test: cover hawkapi._threading PEP 703 helpers"
```

---

## Task 4: Add `cp313t` to the cibuildwheel build list

**Files:**
- Modify: `.github/workflows/wheels.yml:50`

- [ ] **Step 1: Extend `CIBW_BUILD` to include free-threaded CPython 3.13**

In `.github/workflows/wheels.yml`, find the line:

```yaml
          CIBW_BUILD: "cp312-* cp313-*"
```

Replace it with:

```yaml
          CIBW_BUILD: "cp312-* cp313-* cp313t-*"
```

No other changes to the workflow file are needed — `CIBW_SKIP` already excludes older CPythons, PyPy, and musllinux without touching `cp313t`. The build script (updated in Task 2) handles the mypyc skip automatically per-interpreter.

- [ ] **Step 2: Verify the YAML is still valid**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/wheels.yml'))"`

Expected: no output (valid YAML).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/wheels.yml
git commit -m "ci(wheels): build cp313t (free-threaded) alongside cp312/cp313"
```

---

## Task 5: Add the experimental `test-free-threaded` CI job

**Files:**
- Modify: `.github/workflows/ci.yml` (append new job after `perf-regression`)

Separate job — not added to the existing `test` matrix, so failures there don't block main.

- [ ] **Step 1: Append the new job at the end of `.github/workflows/ci.yml`**

Append, after the existing `perf-regression` job and keeping the final newline of the file:

```yaml

  test-free-threaded:
    name: Test (Python 3.13 free-threaded, experimental)
    # Non-blocking: surfaces regressions without gating merges.
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true

      - name: Set up Python 3.13 free-threaded
        # uv supports the free-threaded CPython build via the 't' suffix.
        run: uv python install 3.13t

      - name: Install dependencies
        run: uv sync --python 3.13t --extra dev --extra pydantic

      - name: Run unit tests
        run: uv run --python 3.13t pytest tests/unit -x --tb=short -q
```

- [ ] **Step 2: Verify the YAML is valid**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add experimental test-free-threaded job (non-blocking)"
```

---

## Task 6: Add the PEP 779 trove classifier

**Files:**
- Modify: `pyproject.toml:24` (insert after `"Programming Language :: Python :: 3.13",`)

- [ ] **Step 1: Insert the classifier**

In `pyproject.toml`, find the classifier list:

```toml
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Internet :: WWW/HTTP",
```

Insert the new line between `3.13` and `Topic`:

```toml
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: Free Threading :: 1 - Unstable",
    "Topic :: Internet :: WWW/HTTP",
```

- [ ] **Step 2: Verify the metadata still builds cleanly**

Run: `uv build --sdist 2>&1 | tail -5`

Expected: sdist builds without a classifier-validation error. If `uv build` reports "invalid classifier", remove the line and skip to Task 7 — the classifier is cosmetic and can be revisited when PyPI's index updates.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(pyproject): add PEP 779 free-threading trove classifier"
```

---

## Task 7: Create the user-facing free-threaded guide

**Files:**
- Create: `docs/guide/free-threaded.md`

- [ ] **Step 1: Write the guide**

Create `docs/guide/free-threaded.md`:

````markdown
# Free-threaded Python (PEP 703)

HawkAPI ships a wheel for the CPython 3.13 free-threaded build (`python3.13t`,
also known as "no-GIL" or PEP 703). Support is **experimental** — install works,
imports work, and routing works, but shared mutable state inside the framework
has not yet been systematically audited for thread-safety.

## Installation

```bash
pip install hawkapi
```

On a `python3.13t` interpreter, pip picks the `cp313t-cp313t` wheel. This is a
pure-Python build — the mypyc-compiled hot paths we ship for the regular
`cp313` ABI are intentionally disabled for free-threaded builds, because
mypyc-compiled extensions currently require the GIL.

You can confirm which wheel was installed:

```bash
python3.13t -c "import hawkapi, sys; print(hawkapi.__file__); print(sys._is_gil_enabled())"
```

The second line should print `False` on a free-threaded interpreter.

## Status

| Area | Status |
|---|---|
| Install / import | Supported |
| Unit test suite under `python3.13t` | Runs green in CI (non-blocking job) |
| Mypyc hot-path compilation | **Disabled** (upstream-blocked) |
| Audit for shared mutable state | **Not yet done** |

The framework exposes `FREE_THREADED`, `maybe_thread_lock()`, and
`maybe_async_lock()` in `hawkapi._threading` — primitives the internal
codebase will use to add explicit locks around shared state during the upcoming
hardening pass.

## Known limitations

- **No mypyc perf boost.** The `cp313t` wheel is pure Python. Throughput on
  free-threaded interpreters is currently lower than on the regular GIL build.
- **Routing and middleware caches have not been audited.** Building routes at
  startup is safe (single-threaded). Hot-reloading routes or mutating the
  router from request handlers under concurrent threads may race. Avoid both in
  production.

## Reporting issues

Please open a GitHub issue with the `free-threaded` label and include:

- Output of `python3.13t -VV`
- Your install method (`pip`, `uv`, etc.) and the wheel filename pip installed
- A minimal reproducer with explicit thread/task concurrency
- The observed symptom (crash, wrong output, hang)

## Roadmap

A follow-up milestone (tracked as "Tier 1-B") will:

1. Audit every module with shared mutable state (route caches, DI singletons,
   middleware counters, OpenAPI schema cache) and guard mutations with
   `maybe_thread_lock` / `maybe_async_lock`.
2. Expand the CI free-threaded job to cover integration and perf tests.
3. Promote the CI job from `continue-on-error: true` to a required check.
````

- [ ] **Step 2: Smoke-check that mkdocs still builds**

Run: `uv run --extra docs mkdocs build --strict 2>&1 | tail -10` (fall back to `uv run mkdocs build --strict` if `--extra docs` is not recognised).

Expected: build succeeds. A missing-nav-entry warning is acceptable at this step — fixed in Task 8.

- [ ] **Step 3: Commit**

```bash
git add docs/guide/free-threaded.md
git commit -m "docs(guide): add free-threaded Python (PEP 703) guide"
```

---

## Task 8: Add the new guide to `mkdocs.yml` nav

**Files:**
- Modify: `mkdocs.yml` (nav `Guide` section)

- [ ] **Step 1: Insert the nav entry after `Performance`**

In `mkdocs.yml`, find the `Guide` section of the `nav:` list:

```yaml
      - Performance: guide/performance.md
      - Migration from FastAPI: guide/migration-from-fastapi.md
```

Insert a new entry between `Performance` and `Migration from FastAPI`:

```yaml
      - Performance: guide/performance.md
      - Free-threaded Python (PEP 703): guide/free-threaded.md
      - Migration from FastAPI: guide/migration-from-fastapi.md
```

- [ ] **Step 2: Verify mkdocs strict build passes**

Run: `uv run mkdocs build --strict 2>&1 | tail -10`

Expected: `INFO - Documentation built in ...` with no `WARNING` or `ERROR` lines.

- [ ] **Step 3: Commit**

```bash
git add mkdocs.yml
git commit -m "docs(nav): link free-threaded guide under Guide section"
```

---

## Task 9: Final verification — full unit suite still green

- [ ] **Step 1: Run the full unit test suite**

Run: `uv run pytest tests/unit -q`

Expected: all tests pass, including the two new files (`test_build_mypyc.py`, `test_threading.py`).

- [ ] **Step 2: Run the lint and type-check gates**

Run these in sequence:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pyright src/
```

Expected: each exits 0.

- [ ] **Step 3: If any formatting drift, fix and re-commit**

If `ruff format --check` reports changes, run `uv run ruff format src/ tests/` and commit:

```bash
git add -u
git commit -m "style: ruff format"
```

---

## Verification summary

After all tasks are complete, the tree is in this shape:

- `build_mypyc.is_enabled()` returns `False` on free-threaded interpreters even when `HAWKAPI_BUILD_MYPYC=1`.
- `tests/unit/test_build_mypyc.py` and `tests/unit/test_threading.py` exist and pass under the regular GIL interpreter.
- `.github/workflows/wheels.yml` builds `cp313t` wheels on all five OS/arch matrix rows.
- `.github/workflows/ci.yml` has a new `test-free-threaded` job that runs unit tests under `python3.13t` and is marked `continue-on-error: true`.
- `pyproject.toml` declares the PEP 779 trove classifier (if PyPI accepts it).
- `docs/guide/free-threaded.md` exists and is linked from the Guide nav.

Expected CI outcome on the PR:

- `test (3.12)`, `test (3.13)`, `lint`, `typecheck`, `memory-check`, `perf-regression` — required, must pass.
- `test-free-threaded` — visible, non-blocking. Green on clean main, yellow or red when a free-threaded-specific issue surfaces.
- `build_wheels` job (on release only) — produces artefacts named `hawkapi-*-cp313t-cp313t-*.whl` on every matrix row.
