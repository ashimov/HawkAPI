# Tier 1 — Free-threaded Python 3.13 wheels (design spec)

**Status:** Draft — awaiting user review
**Date:** 2026-04-18
**Scope:** Ship-only (option A). Build and ship `cp313t` (PEP 703 free-threaded) wheels plus an experimental, non-blocking CI job. No code audit for shared-mutable-state races in this tier.

---

## Goal

Give HawkAPI users installing on CPython 3.13 free-threaded (`python3.13t`) a wheel that installs and imports cleanly, with CI visibility that catches regressions but does not block mainline merges.

Correctness under no-GIL is best-effort at this tier. The `src/hawkapi/_threading.py` helpers already exist for future per-module audits; actually applying them to every shared-state site is deferred.

## Architecture

Two interpreter ABIs ship from one codebase:

| ABI tag   | Build variant        | Mypyc?             | Status                  |
|-----------|----------------------|--------------------|-------------------------|
| `cp312`   | GIL, CPython 3.12    | Yes                | Stable (unchanged)      |
| `cp313`   | GIL, CPython 3.13    | Yes                | Stable (unchanged)      |
| `cp313t`  | Free-threaded 3.13   | **No** (auto-skip) | **Experimental (new)**  |

The "should mypyc compile?" decision moves from cibuildwheel env branching into `build_mypyc.is_enabled()`. When the build-time interpreter is free-threaded (`sys._is_gil_enabled() is False`), `is_enabled()` returns `False` even if `HAWKAPI_BUILD_MYPYC=1`, and the hatch hook becomes a no-op. This keeps the CI config declarative — one env var for all builds, the build script self-selects.

Rationale for skipping mypyc on `cp313t`: mypyc-compiled extensions historically require the GIL. Rather than discover this mid-release, we opt out deterministically and document it. If upstream mypyc ships free-threaded support later, flipping the guard is a one-line change.

## Changes

### 1. `build_mypyc.py` — free-threaded auto-skip

Modify `is_enabled()` to additionally check the running interpreter:

```python
def is_enabled() -> bool:
    if os.environ.get("HAWKAPI_BUILD_MYPYC", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    # mypyc-compiled extensions require the GIL; skip on free-threaded builds.
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

This is the **load-bearing change**. Every other CI/config edit flows from it: if this works, cibuildwheel needs no per-ABI branching.

### 2. `.github/workflows/wheels.yml` — add `cp313t` to the build matrix

- Extend `CIBW_BUILD` from `"cp312-* cp313-*"` to `"cp312-* cp313-* cp313t-*"`.
- `CIBW_SKIP` already excludes cp36–cp311, pp*, musllinux; `cp313t` is not in the skip list, so nothing to change there.
- `CIBW_ENVIRONMENT` stays `HAWKAPI_BUILD_MYPYC=1`. The build script now self-selects (per change #1).
- `CIBW_TEST_COMMAND` stays the same; the unit suite runs on `cp313t` as a smoke test.
- Free-threaded builds on Windows and macOS are supported by cibuildwheel ≥ 2.21; the current pin (`v2.21.3`) is sufficient.

Expected artefact count increases from 5 to ~10 (5 matrix rows × 2 ABIs, minus any platform that cibuildwheel cannot provide a `cp313t` interpreter for — notably, Linux aarch64 cross-builds may take longer in QEMU).

### 3. `.github/workflows/ci.yml` — new experimental job

Add a job named `test-free-threaded`:

```yaml
test-free-threaded:
  name: Test (Python 3.13 free-threaded, experimental)
  runs-on: ubuntu-latest
  continue-on-error: true
  steps:
    - uses: actions/checkout@v4
    - name: Install uv
      uses: astral-sh/setup-uv@v4
      with:
        enable-cache: true
    - name: Set up Python 3.13t
      # uv supports free-threaded CPython via the 't' suffix.
      run: uv python install 3.13t
    - name: Install dependencies
      # Use the 3.13t interpreter explicitly.
      run: uv sync --python 3.13t --extra dev --extra pydantic
    - name: Run unit tests
      run: uv run --python 3.13t pytest tests/unit -x --tb=short -q
```

Key decisions:

- **Not added to the main `test` matrix.** Keeping it separate prevents the main matrix from flapping when a 3.13t-specific bug surfaces.
- **`continue-on-error: true`** — job status shown on PR checks but does not block merges. Matches "experimental" framing.
- **Unit tests only** — integration, perf, and memory suites are skipped to keep the job fast. When we graduate to Tier 1-B (full audit), we expand coverage.
- **Fallback if `uv python install 3.13t` fails:** replace with `actions/setup-python@v5` using a `3.13` free-threaded variant. We will use uv by default; if CI reports "3.13t not found", we switch in a follow-up.

### 4. `pyproject.toml` — trove classifier

Add the PEP 779 trove classifier:

```toml
"Programming Language :: Python :: Free Threading :: 1 - Unstable",
```

Positioned after the existing `Programming Language :: Python :: 3.13` entry. `requires-python = ">=3.12"` stays unchanged — free-threaded is a build variant, not a version.

**Verification:** Before merging, confirm the classifier is live on PyPI's classifier index. If PyPI rejects it at upload time, fall back to a comment in the README and remove the classifier until PyPI catches up.

### 5. `docs/guide/free-threaded.md` — new user-facing guide

New page covering:

- **Installation:** `pip install hawkapi` under `python3.13t` ships pure-Python (no mypyc) and works out of the box.
- **Status:** Experimental. The `_threading` module already provides `FREE_THREADED`, `maybe_thread_lock()`, and `maybe_async_lock()` primitives, but internal modules have not been audited for shared mutable state yet.
- **Known limitations:**
  - No mypyc perf boost on `cp313t` (upstream-blocked).
  - Routing/middleware caches may race under parallel thread-pool executors. Report observed issues; a hardening pass is planned.
- **How to report bugs:** link to GitHub issues with a "free-threaded" label template.
- **Roadmap pointer:** mention that full audit + required CI is tracked as a follow-up (Tier 1-B).

### 6. `docs/index.md` — nav link

Add a link to `guide/free-threaded.md` under the "Guide" section, ordered after `performance.md`.

### 7. `tests/unit/test_threading.py` (optional smoke test)

Add a test verifying `FREE_THREADED` matches `sys._is_gil_enabled()` (only runs where the attribute exists) and the null-lock helpers behave correctly under both branches. Low priority — the helpers are already covered implicitly, but an explicit test makes the free-threaded CI job meaningful even without a real audit.

## Success criteria

1. `cibuildwheel` produces `hawkapi-*-cp313t-cp313t-*.whl` on every OS/arch in the build matrix (Linux x86_64/aarch64, macOS x86_64/arm64, Windows AMD64).
2. `pip install hawkapi` on a `python3.13t` interpreter installs a pure-Python wheel and `import hawkapi` succeeds.
3. `pytest tests/unit` passes under `python3.13t` locally and in CI.
4. The `test-free-threaded` job appears on every PR, passes on a clean main, and is visibly marked "experimental / non-blocking".
5. PyPI accepts the release with the new trove classifier, OR the classifier is cleanly removed without other breakage.

## Out of scope (explicit)

- No audit of shared mutable state (route caches, DI singletons, middleware counters, OpenAPI schema cache, etc.). That audit is Tier 1-B.
- No mypyc-compiled `cp313t` wheels. Reconsider when upstream mypyc ships PEP 703 support.
- No promotion of `3.13t` to a required CI gate.
- No change to `requires-python` or minimum supported Python version.

## Risks and mitigations

| Risk                                                          | Mitigation                                                                 |
|---------------------------------------------------------------|----------------------------------------------------------------------------|
| `uv python install 3.13t` not supported on current uv version | Fallback: `actions/setup-python@v5` with free-threaded Python              |
| Trove classifier rejected by PyPI                             | Remove classifier, merge without it, revisit when PyPI catches up          |
| Unit test suite hits a GIL-dependent race under `cp313t`      | `continue-on-error: true` absorbs the noise; follow-up issue documents fix |
| cibuildwheel cannot resolve a `cp313t` interpreter on Windows | Expected supported in v2.21+; if not, narrow `CIBW_BUILD` per-OS           |
| Build time for `cp313t` wheels doubles the matrix runtime     | Accept; artefact upload and cache limit remain within budget               |

## Testing approach

- **Local reproduction:** install `python3.13t` via `uv python install 3.13t`, run `pytest tests/unit`.
- **CI:** the new `test-free-threaded` job catches import-time and obvious runtime races on every PR.
- **Release verification:** after a release, manually verify `pip install hawkapi` on a `3.13t` interpreter installs a file named `hawkapi-*-cp313t-cp313t-*.whl`, not the `cp313` wheel.

## Files touched

- `build_mypyc.py` — `is_enabled()` gains a free-threaded check.
- `.github/workflows/wheels.yml` — `CIBW_BUILD` extended with `cp313t-*`.
- `.github/workflows/ci.yml` — new `test-free-threaded` job.
- `pyproject.toml` — new trove classifier.
- `docs/guide/free-threaded.md` — new user guide.
- `docs/index.md` — new nav entry.
- `tests/unit/test_threading.py` — optional smoke test.

## Rollback

If the release produces broken `cp313t` wheels or breaks the main matrix:

1. Revert the commit adding `cp313t-*` to `CIBW_BUILD`. One-line change, safe.
2. Keep the `test-free-threaded` CI job — it's non-blocking and provides ongoing signal.
3. File an issue describing the specific failure mode; Tier 1-B planning picks up from there.
