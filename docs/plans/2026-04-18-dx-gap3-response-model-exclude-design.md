# DX Gap #3 — `response_model_exclude_{none,unset,defaults}` flags

**Status:** Approved — ready for implementation
**Date:** 2026-04-18
**Scope:** Second-smallest of the top-5 DX gaps. Add three route-level boolean kwargs that mirror FastAPI's response shaping controls. Already-coerced response bodies are passed through a shared filter helper before encoding.

**Audit:** [docs/audits/2026-04-18-dx-vs-fastapi.md](../audits/2026-04-18-dx-vs-fastapi.md) (Gap #3)

---

## Goal

```python
@app.get(
    "/items/{id}",
    response_model=Item,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    response_model_exclude_defaults=True,
)
async def get_item(id: int) -> dict: ...
```

...produces the same JSON a FastAPI user would expect, across msgspec Structs and Pydantic models.

## Semantics

- **`exclude_none=True`** — drop keys whose value is `None`, recursively. Works uniformly for any model type (post-processing step over the already-encoded dict tree).
- **`exclude_defaults=True`** — drop keys whose value equals the model field's default.
  - Pydantic: `obj.model_dump(exclude_defaults=True)` native.
  - msgspec: `msgspec.structs.fields(model)` exposes defaults; compare per-field.
- **`exclude_unset=True`** — drop keys the user never explicitly set.
  - Pydantic: `obj.model_dump(exclude_unset=True)` via `__fields_set__`.
  - msgspec: requires the user to declare fields as `field: T | UnsetType = UNSET`; any other field cannot be "unset" in msgspec's model. For non-UNSET fields the flag is a no-op — intentional and documented.

All three flags default to `False`. When none is set, the existing hot path in `_apply_response_model` / `JSONResponse` runs unchanged — zero overhead.

## Implementation

### `src/hawkapi/routing/route.py`

Add three fields to the `Route` dataclass (default `False`), alongside the existing `response_model`.

### `src/hawkapi/routing/router.py`

Each of the seven entry points (`add_route` + `.get/.post/.put/.patch/.delete/.head/.options`) accepts three new kwargs, default `False`, and forwards them to `Route`. Router-level `include_router` also accepts them but defers wiring through to a follow-up (router-level defaults are explicit out-of-scope per the spec).

### `src/hawkapi/serialization/filters.py` (new)

```python
def apply_exclude_filters(
    data: Any,
    model: type[Any] | None,
    *,
    exclude_none: bool,
    exclude_unset: bool,
    exclude_defaults: bool,
) -> Any:
    """Apply FastAPI-style response_model_exclude_* filters.

    ``data`` is either an instance of ``model`` (Pydantic or msgspec Struct) or
    a dict produced by prior validation. Returns a plain dict/list/primitive
    tree ready for JSON encoding.
    """
```

Behaviour:

1. If `data` is a Pydantic model instance, delegate to `model_dump(exclude_none=..., exclude_unset=..., exclude_defaults=...)`. Done.
2. If `data` is a msgspec Struct instance:
   a. Convert via `msgspec.to_builtins(data)` (returns dict tree).
   b. Walk the tree with the Struct's field metadata (`msgspec.structs.fields(model)`) to apply `exclude_defaults` / `exclude_unset`.
   c. If `exclude_none`, walk the final tree and drop None values.
3. If `data` is already a dict, only `exclude_none` is meaningful (no type info). Apply that, leave everything else.
4. Primitives / lists pass through unchanged.

### `src/hawkapi/app.py`

- `_build_response(result, status_code, response_model, *, exclude_none, exclude_unset, exclude_defaults)` receives the flags.
- `_apply_response_model(result, response_model)` keeps its current coercion job.
- After coercion, if any flag is set, `_build_response` calls `apply_exclude_filters(...)` and passes the resulting dict to `JSONResponse`.
- Fast path (no flags set): unchanged.

### Tests (`tests/unit/test_response_model_exclude.py`)

- `exclude_none` on a msgspec Struct with a nullable field → key dropped.
- `exclude_none` on a dict return with nested structures — recursive.
- `exclude_defaults` on msgspec Struct with field defaults.
- `exclude_defaults` on Pydantic model (uses model_dump natively).
- `exclude_unset` on Pydantic model.
- `exclude_unset` on msgspec Struct with UnsetType field.
- `exclude_unset` on msgspec Struct WITHOUT UnsetType — documented no-op (all non-unset values are emitted).
- All three combined on one nested model.
- Zero-flag baseline: serialization unchanged.
- `None` return still short-circuits to 204 (pre-existing behavior).

### CHANGELOG

Single `[Unreleased] ### Added` bullet referencing the three flags.

## Out of scope

- Router-level / app-level defaults (FastAPI has them). Follow-up.
- `response_model_include`, `response_model_by_alias` — not in audit top-5.
- Retroactive filtering of already-shipped routes — opt-in only.

## Success criteria

1. All three flags work independently.
2. Work in combination, recursively, through nested structures.
3. Zero overhead when all three are `False` (default path).
4. Full unit suite + ruff + format + mkdocs strict build stay clean.
5. No regressions in existing `test_response_model.py`.

## Files touched

- `src/hawkapi/routing/route.py` (+3 fields)
- `src/hawkapi/routing/router.py` (7 signatures × 3 kwargs)
- `src/hawkapi/app.py` (flags plumbed through `_build_response`)
- `src/hawkapi/serialization/filters.py` (new)
- `tests/unit/test_response_model_exclude.py` (new)
- `CHANGELOG.md` (+1 line)

## Rollback

Delete the new filters module, revert the three dataclass fields and router-decorator signatures, revert the `_build_response` call-site change, delete the new test file. One-PR revert.
