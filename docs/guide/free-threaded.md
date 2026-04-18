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
