# Performance

HawkAPI is fast out of the box because the request path leans on msgspec for
serialization and granian for the ASGI runtime — both written in compiled
languages. For latency-sensitive deployments you can squeeze additional
throughput by compiling HawkAPI's hot Python modules with
[mypyc](https://mypyc.readthedocs.io/).

## Automatic fast paths

Two dispatcher fast paths trigger at route-registration time — no opt-in flag,
no runtime overhead, no behavioural difference.

### Static-response cache (Wave 4, since 0.1.7)

Handlers whose body is exactly `return SomeResponse(literal_args)` with no
parameters have their two ASGI messages (`http.response.start` +
`http.response.body`) built **once** at registration time and re-emitted on
every request. No handler call, no Response allocation, no header construction
per request.

```python
@app.get("/plaintext")
async def plaintext() -> PlainTextResponse:
    return PlainTextResponse("Hello, World!")

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
```

Local micro-benchmark on Darwin / Python 3.13: plaintext handler at
**0.89 µs / request (1.1 M req/s on ASGI directly)** vs the previous
trivial-path 6.76 µs / request — a 7.5× speedup for static endpoints.

Eligible handlers:

- No parameters of any kind (no `Request`, no `Depends`, no path/query)
- Async function (sync handlers fall through to the regular path)
- Single `return` statement (an optional docstring is allowed)
- Return value is a `Call` to `Response`, `PlainTextResponse`, `JSONResponse`,
  or `HTMLResponse` by bare name
- Every positional and keyword argument is a literal (`Constant`, list,
  tuple, set, dict of literals, or unary +/− of a numeric constant)

Anything else falls through to the trivial / general path. No regression on
dynamic handlers.

### Trivial-route fast path (Wave 3, since 0.1.4)

When the static-response cache does not apply but the route has no DI, no
`Depends(...)`, no permissions, no background tasks, no `response_model`, no
deprecation headers, and no per-route middleware, the dispatcher takes a
slimmer execution path that skips the DI scope, cleanup stack, and exception
classifier branches. Path / query params are still coerced via `_coerce_fast`
(since 0.1.5).

The eligibility flag is computed once at registration; the per-request branch
is a single boolean check.

## Manual fast paths

### When to enable mypyc

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

### Installing the mypyc-compiled build

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

### What gets compiled

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

### Expected gains

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

### Caveats

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
