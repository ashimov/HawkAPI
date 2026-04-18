# Performance

HawkAPI is fast out of the box because the request path leans on msgspec for
serialization and granian for the ASGI runtime — both written in compiled
languages. For latency-sensitive deployments you can squeeze additional
throughput by compiling HawkAPI's hot Python modules with
[mypyc](https://mypyc.readthedocs.io/).

## When to enable mypyc

Enable mypyc when:

- You are deploying to CPython 3.12+ on a platform that already has a C
  toolchain available (most Linux containers, macOS with Xcode CLT, Windows
  with MSVC Build Tools).
- You can rebuild from source as part of your image pipeline.
- The marginal RPS / tail-latency improvement matters for your workload.

Skip mypyc when:

- You run on PyPy. PyPy already JIT-compiles Python and cannot load
  CPython C extensions.
- You install on a host without a C compiler.
- You depend on `pip install hawkapi` being a fast, no-build operation.

The default `pip install hawkapi` always installs the pure-Python wheel; mypyc
compilation is strictly opt-in.

## Installing the mypyc-compiled build

The build is gated by the `HAWKAPI_BUILD_MYPYC` environment variable.

```bash
# 1. Install the build-only extras (mypy >= 1.13).
pip install "hawkapi[build]"

# 2. Reinstall HawkAPI from source with mypyc compilation enabled.
HAWKAPI_BUILD_MYPYC=1 pip install hawkapi --no-binary hawkapi
```

`--no-binary hawkapi` forces pip to build the wheel locally, which lets the
hatchling build hook see `HAWKAPI_BUILD_MYPYC=1` and invoke mypyc.

If you use uv:

```bash
uv pip install "hawkapi[build]"
HAWKAPI_BUILD_MYPYC=1 uv pip install hawkapi --no-binary hawkapi --reinstall
```

After installation, verify the compiled `.so` files are loaded instead of the
`.py` source:

```bash
python -c "import hawkapi.routing._radix_tree; print(hawkapi.routing._radix_tree.__file__)"
# .../site-packages/hawkapi/routing/_radix_tree.cpython-313-<plat>.so
```

Pre-built mypyc wheels for common platforms may be published in a future
release; until then, building from source is required.

## What gets compiled

The build hook compiles only the request-routing hot path. Response classes are
intentionally left interpreted because user code (and the bundled
`PlainTextResponse` / `HTMLResponse` / `RedirectResponse` helpers) subclass
them, and mypyc forbids interpreted classes from inheriting from compiled
ones.

| Module | Reason |
| --- | --- |
| `hawkapi.routing._radix_tree` | Per-request URL match — the hottest pure-Python loop. |
| `hawkapi.routing.route` | `Route` dataclass instantiation in the lookup result. |
| `hawkapi.routing.param_converters` | Path parameter coercion. |
| `hawkapi.middleware._pipeline` | Middleware chain assembly at startup. |

## Expected gains

The dominant per-request cost in HawkAPI is already in C (granian, msgspec). On
the bundled competitive benchmark suite (`benchmarks/competitive/runner.py`)
mypyc compilation typically adds 2–5 % throughput to the routing-heavy
scenarios on macOS / arm64 — `json`, `path_param`, `query_params`,
`routing_stress`. CPU-bound services with many small handlers and complex
routing tables tend to see the largest deltas.

You can measure the delta on your own hardware:

```bash
# Pure-Python baseline.
uv run python benchmarks/competitive/runner.py --framework hawkapi --duration 8

# Compiled run.
HAWKAPI_BUILD_MYPYC=1 uv pip install . --reinstall --no-build-isolation
uv run python benchmarks/competitive/runner.py --framework hawkapi --duration 8
```

## Caveats

- **PyPy is unsupported.** mypyc emits CPython C extensions; PyPy users get the
  pure-Python build automatically.
- **A C compiler is required at install time.** clang, gcc, or MSVC must be
  reachable from the build environment along with the matching CPython headers
  (`python3-dev` on Debian/Ubuntu, the `Xcode Command Line Tools` on macOS).
- **Wheels are platform-tagged.** Compiled wheels are tied to the CPython ABI,
  OS, and architecture they were built on. Build inside the same container
  image you deploy.
- **Response subclasses.** If you subclass `Response`, `JSONResponse`, or any
  `Middleware` defined inside HawkAPI, they remain pure Python — mypyc only
  touches the modules listed above.
