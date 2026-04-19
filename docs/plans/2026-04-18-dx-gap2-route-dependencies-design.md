# DX Gap #2 — route-level and router-level `dependencies=[Depends(...)]`

**Status:** Approved — ready for implementation
**Date:** 2026-04-18
**Scope:** Third of the top-5 DX gaps. Add `dependencies=[Depends(...)]` kwarg to route decorators and `Router()` so users can declare side-effect-only dependencies (auth guards, audit writers, etc.) without threading them through handler signatures.

**Audit:** [docs/audits/2026-04-18-dx-vs-fastapi.md](../audits/2026-04-18-dx-vs-fastapi.md) (Gap #2)

---

## Goal

```python
# Route-level
@app.get("/admin/reports", dependencies=[Depends(require_admin)])
async def reports() -> Response: ...

# Router-level — applies to every route the router registers
admin_router = Router(prefix="/admin", dependencies=[Depends(require_admin)])

@admin_router.get("/stats")
async def stats() -> Response: ...
```

`require_admin` runs before the handler every request; its return value is discarded. Any `HTTPException` it raises short-circuits to the corresponding response. Sub-dependencies (the callable accepting its own `Depends(...)` params) resolve via the existing DI machinery.

## Execution semantics

1. Router-level deps run **before** route-level deps (outer ring first).
2. Deps run **before** the handler's own kwargs are resolved and **before** the handler is invoked. Auth guards therefore don't pay body-parse cost if they reject.
3. Return value is **discarded** — side-effect only.
4. Sub-dependencies supported — each `Depends(callable)` in the list can itself depend on other `Depends`, path/query/header params, request, etc. Reuses `_build_dep_callable_plan` + `DepCallablePlan` already used for in-signature `Depends(...)`.
5. Raising `HTTPException` propagates through the existing app dispatch try/except; request short-circuits to the corresponding Problem Details response.
6. Raising any other exception propagates normally (user-registered `@app.exception_handler`s or the fallback 500).

## Implementation

### `src/hawkapi/routing/route.py`

Add one tuple field (keeps the dataclass frozen + slotted):

```python
dependencies: tuple[Depends, ...] = ()
```

### `src/hawkapi/routing/router.py`

- `Router.__init__` — new `dependencies: list[Depends] | None = None` kwarg; stores a tuple on `self._dependencies`.
- `add_route` (and therefore all seven decorators via `_route_decorator`) — new `dependencies: list[Depends] | None = None` kwarg. Merged: `router_deps + route_deps` (order matters).
- `include_router` — router deps of the parent are prepended onto each sub-route's dependency list during the include merge.
- At route-registration time, each merged `Depends` is compiled into a `DepCallablePlan` via a new helper (see below) and stored on a parallel side-effect-plan tuple on the `Route` — pre-computing once is consistent with how the main `HandlerPlan` is built.

### `src/hawkapi/di/param_plan.py`

New function:

```python
def build_side_effect_dep_plans(
    deps: Sequence[Depends],
    *,
    container: Container | None,
    path_params: AbstractSet[str],
) -> tuple[DepCallablePlan, ...]:
    """Pre-compile side-effect Depends callables; return values will be discarded."""
```

Wraps the existing `_build_dep_callable_plan` (already present, used for in-signature `Depends`). Returns a tuple suitable to cache on `Route`.

### `src/hawkapi/app.py`

In the main dispatch loop, between "kwargs resolved" and "handler invoked", execute each pre-compiled side-effect plan in order. Each plan resolution uses the same DI scope as the main handler (so a side-effect dep and a handler dep that share a sub-dependency both see the cached value). Errors propagate into the existing try/except that already handles `HTTPException`, `RequestValidationError`, and generic exceptions.

Concretely: add a helper `_run_side_effect_deps(plans, request, container_scope)` called just before the handler invocation; iterate and `await` each resolved callable; discard return value.

### Tests (`tests/unit/test_route_dependencies.py`)

- Route-level `dependencies=[Depends(fn)]` runs `fn` before the handler.
- `Router(dependencies=[...])` applies to every route registered on that router.
- Router deps run before route deps (order observable via a shared side-effect log).
- Sub-deps work: the callable in `dependencies=[Depends(cb)]` has its own `cb(token: str = Depends(get_token))` resolved.
- `HTTPException(403)` raised inside a dep → client sees 403 Problem Details; handler never runs.
- Generic `RuntimeError` raised inside a dep → propagates to exception handler / 500.
- Empty `dependencies` (default) → zero overhead and behavior unchanged.
- Caching: same `Depends(fn)` used in both `dependencies=[]` AND handler signature — `fn` runs once per request (scope cache).

### CHANGELOG

One `[Unreleased] ### Added` bullet.

## Out of scope

- **App-level `HawkAPI(dependencies=[...])`** — natural follow-up; not part of Gap #2.
- **Dependency-level response headers / cookies** — deps are side-effect only.
- **Injecting dep return values into handler** — covered by existing `Depends()` in handler signatures; not redundantly exposed via `dependencies=[]`.
- **Yield-dependencies** inside `dependencies=[]` — out of scope for Gap #2; Gap #1 introduces yield support; once it lands, side-effect deps inherit it automatically.

## Success criteria

1. All seven route decorators + `Router()` accept `dependencies=[Depends(...)]`.
2. Router deps fire before route deps.
3. Sub-deps of side-effect deps resolve via normal DI.
4. `HTTPException` short-circuits; generic exceptions propagate.
5. `dependencies=[]` → zero overhead; no regressions in existing suite.
6. Lint + format + full suite green.

## Files touched

- `src/hawkapi/routing/route.py` (+1 field)
- `src/hawkapi/routing/router.py` (new kwarg in 7 decorators + `Router.__init__` + `add_route` + `include_router` merge)
- `src/hawkapi/di/param_plan.py` (+1 helper)
- `src/hawkapi/app.py` (+1 helper `_run_side_effect_deps` + dispatch wire-up)
- `tests/unit/test_route_dependencies.py` (new)
- `CHANGELOG.md` (+1 line)

## Rollback

Revert the six files. `Route` field + `Router` kwarg are purely additive, existing callers don't use them. Full revert is one squash.
