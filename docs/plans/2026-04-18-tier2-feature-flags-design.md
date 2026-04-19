# Tier 2 — Feature flags — design spec

**Status:** Approved — ready for implementation
**Date:** 2026-04-18
**Scope:** Built-in runtime feature flag system for HawkAPI. Ships `FlagProvider` Protocol, three built-in providers (Static / Env / File with mtime-based hot reload), DI helper, `@requires_flag` decorator, plugin hook for audit logging.

---

## Goal

```python
from hawkapi import HawkAPI, Depends
from hawkapi.flags import Flags, StaticFlagProvider, get_flags, requires_flag

provider = StaticFlagProvider({"new_checkout": True, "max_retries": 3})
app = HawkAPI(flags=provider)

@app.get("/checkout")
async def checkout(flags: Flags = Depends(get_flags)) -> dict:
    if await flags.bool("new_checkout", default=False):
        return await new_checkout_flow()
    return await old_checkout_flow()


@app.get("/beta/reports")
@requires_flag("beta.reports")  # 404 when the flag is off
async def beta_reports() -> dict:
    ...
```

Zero extra dependencies. No OpenFeature, no LaunchDarkly SDK required. Integrations ship as plugins later.

## Semantics

### `FlagProvider` Protocol

```python
class FlagProvider(Protocol):
    async def get_bool(
        self, key: str, default: bool, *, context: EvalContext | None = None
    ) -> bool: ...

    async def get_string(
        self, key: str, default: str, *, context: EvalContext | None = None
    ) -> str: ...

    async def get_number(
        self, key: str, default: float, *, context: EvalContext | None = None
    ) -> float: ...
```

All methods accept an optional `EvalContext` — providers that don't care about it ignore it. `default` is what the provider returns when the key is missing or the value is the wrong type.

### `EvalContext`

```python
@dataclass(frozen=True, slots=True)
class EvalContext:
    user_id: str | None = None
    tenant_id: str | None = None
    headers: Mapping[str, str] = MappingProxyType({})
    attrs: Mapping[str, Any] = MappingProxyType({})
```

The DI helper (`get_flags`) constructs it from the `Request` automatically: user/tenant pulled from configurable headers (default `X-User-ID` / `X-Tenant-ID`), request headers dict exposed for custom targeting rules.

### `Flags` facade

A tiny user-facing wrapper returned by `get_flags`. Methods:

- `await flags.bool(key: str, default: bool = False) -> bool`
- `await flags.string(key: str, default: str = "") -> str`
- `await flags.number(key: str, default: float = 0.0) -> float`
- `await flags.require(key: str) -> None` — raises `FlagDisabled` if the flag is off; useful for short-circuit guards inside handlers.

`Flags` carries an `EvalContext`; per-call overrides via `context=` kwarg are allowed.

### Built-in providers

- **`StaticFlagProvider(values: Mapping[str, Any])`** — trivial dict-backed; doesn't read `EvalContext`. Intended for tests and simple setups.
- **`EnvFlagProvider(prefix: str = "HAWKAPI_FLAG_")`** — reads from `os.environ`. Flag `new_checkout` resolves to `HAWKAPI_FLAG_NEW_CHECKOUT` with case-insensitive key normalisation; standard truthy values (`1` / `true` / `yes`) → `True`.
- **`FileFlagProvider(path: str | Path)`** — loads JSON/YAML/TOML (extension-driven). Re-reads the file on mtime change — lazy, at evaluation time. No background thread, no watcher dependency. YAML is optional (skipped with clear error if `pyyaml` isn't installed).

Users can compose providers by writing a `ChainedFlagProvider(*providers)` themselves; not built-in v1.

### DI helper — `get_flags`

```python
async def get_flags(request: Request) -> Flags:
    app = request.scope["app"]
    provider = app.flags  # stored by HawkAPI(flags=...)
    ctx = EvalContext(
        user_id=request.headers.get("x-user-id"),
        tenant_id=request.headers.get("x-tenant-id"),
        headers=request.headers,
    )
    return Flags(provider, ctx)
```

Users inject `flags: Flags = Depends(get_flags)` in handler signatures.

### `@requires_flag(key)` decorator

Wraps a handler; evaluates the flag per request; if falsy, raises `HTTPException(404)` (matching how "missing route" feels to the client — flags-off routes should be indistinguishable from non-existent routes, not 403).

Optional kwargs:
- `status_code: int = 404` — override.
- `default: bool = False` — what the provider returns if the key is missing (fail-closed by default).

### Plugin hook — `on_flag_evaluated`

When the app has a `Plugin` registered with an `on_flag_evaluated(key, value, context)` hook, the helper calls it after each evaluation. Useful for audit logs, metrics, and debugging. Synchronous hook; async hooks are fire-and-forget via `asyncio.create_task`.

### HawkAPI ctor integration

New optional kwarg:

```python
class HawkAPI(Router):
    def __init__(self, *, flags: FlagProvider | None = None, ...) -> None:
        ...
        self.flags = flags or StaticFlagProvider({})
```

`flags` is a plain attribute for introspection (tests assert `app.flags`). When `None`, an empty `StaticFlagProvider` is used — calling `flags.bool("x", default=False)` just returns the default.

## Module layout

```
src/hawkapi/flags/
    __init__.py          # re-exports FlagProvider, Flags, EvalContext,
                         # StaticFlagProvider, EnvFlagProvider, FileFlagProvider,
                         # get_flags, requires_flag, FlagDisabled
    base.py              # FlagProvider Protocol, EvalContext, Flags, FlagDisabled
    providers.py         # StaticFlagProvider, EnvFlagProvider, FileFlagProvider
    _decorator.py        # requires_flag
    _di.py               # get_flags
```

Source files each < 150 lines, single-responsibility, all imports lazy where they pull third-party deps (YAML).

## Tests — `tests/unit/test_flags.py`

Target ~20 tests covering:

- **StaticFlagProvider**: returns stored values, returns default on missing, returns default on wrong type.
- **EnvFlagProvider**: reads env, normalises key, truthy/falsy parsing, defaults on missing.
- **FileFlagProvider**: loads JSON, loads TOML, loads YAML (skip if pyyaml missing), hot-reloads on mtime change, raises clear error on unknown extension.
- **Flags facade**: `.bool`, `.string`, `.number`, `.require` happy + missing + wrong-type paths.
- **`get_flags` DI helper**: injected via `Depends`, receives correct Request → context mapping.
- **`@requires_flag`**: 404 when off, passes through when on, custom status code works.
- **HawkAPI(flags=...)**: stored on `app.flags`; default is an empty StaticFlagProvider so calls with `default=` return gracefully.
- **Plugin hook**: `on_flag_evaluated` called when registered; not called when absent.
- Integration: route with `flags: Flags = Depends(get_flags)` evaluates correctly end-to-end through TestClient.

## Docs — `docs/guide/feature-flags.md`

Covers: when to use, `Flags`-via-DI pattern, decorator pattern, built-in providers (Static/Env/File), targeting via `EvalContext`, roadmap (LaunchDarkly/OpenFeature plugins, percentage rollouts).

## Mkdocs nav + CHANGELOG

- `mkdocs.yml`: new `Feature flags` entry under Guide (after Client codegen, before Bulkhead).
- `CHANGELOG.md`: one `[Unreleased] ### Added` bullet.

## Out of scope

- **LaunchDarkly / Flagsmith / Unleash SDK integrations** — v2 plugin packages.
- **OpenFeature SDK adapter** — v2 plugin, but worth tracking.
- **Percentage rollouts, A/B variant targeting** — needs a rules DSL; v2.
- **Web UI for flag management** — separate project.
- **Redis-backed provider** — follow-up (bulkhead / circuit-breaker / rate-limit show the shape).
- **Hot reload via filesystem watcher** — v1 uses mtime-check-at-read for zero-dep simplicity.

## Success criteria

1. `flags: Flags = Depends(get_flags)` in a handler returns a working `Flags` with request-derived context.
2. `StaticFlagProvider({"x": True}).get_bool("x", False)` → `True`; `.get_bool("missing", True)` → `True`.
3. `EnvFlagProvider` reads `HAWKAPI_FLAG_NEW_CHECKOUT=true` → `True`; case-insensitive key normalisation.
4. `FileFlagProvider` on a JSON file reloads when mtime changes.
5. `@requires_flag` returns 404 on off; 200 on on.
6. Plugin hook `on_flag_evaluated(key, value, context)` fires on each evaluation.
7. `HawkAPI()` without `flags=` still works (empty provider, defaults returned).
8. Full suite + ruff + mkdocs strict clean.

## Files touched

- `src/hawkapi/flags/__init__.py` — new
- `src/hawkapi/flags/base.py` — new
- `src/hawkapi/flags/providers.py` — new
- `src/hawkapi/flags/_decorator.py` — new
- `src/hawkapi/flags/_di.py` — new
- `src/hawkapi/app.py` — +`flags=` kwarg
- `src/hawkapi/__init__.py` — re-exports
- `tests/unit/test_flags.py` — new
- `docs/guide/feature-flags.md` — new
- `mkdocs.yml` — nav entry
- `CHANGELOG.md` — bullet

## Rollback

New module tree + additive kwarg + new docs. No existing paths change. Revert = delete `flags/` package, revert one kwarg on HawkAPI, revert three doc diffs.
