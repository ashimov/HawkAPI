# Tier 3 — typed routes: auto-infer `response_model` from return annotation

**Status:** Approved — ready for implementation
**Date:** 2026-04-18
**Scope:** When a handler declares a concrete return-type annotation and no explicit `response_model=` is passed, set `response_model` automatically. Matches Litestar/BlackSheep ergonomics and closes the "types flow everywhere" story that starts at the handler and ends at the generated client SDK (shipped in `36877f4`).

---

## Goal

**Before:**

```python
@app.get("/items", response_model=list[Item])
async def list_items() -> list[Item]:
    ...
```

**After:**

```python
@app.get("/items")
async def list_items() -> list[Item]:
    ...
# response_model auto-inferred from return annotation
```

The chain becomes:

```
handler: -> Item
   ↓ auto-infer
response_model = Item
   ↓ runtime coercion (existing)
JSONResponse shaped as Item
   ↓ OpenAPI generator (existing)
components.schemas.Item
   ↓ hawkapi gen-client (Tier 3a, commit 36877f4)
TS/Python client SDK types
```

## Semantics

When `add_route(handler, response_model=None, ...)` is called (i.e. the caller did not pass `response_model=`), inspect `handler`'s return annotation:

### Infer when the annotation is a "structured" type

- `msgspec.Struct` subclass.
- Pydantic `BaseModel` subclass.
- Parameterized generics: `list[T]`, `dict[K, V]`, `tuple[...]`, `set[T]`.
- Union with `None`: `T | None`, `Optional[T]`.
- `Annotated[T, ...]` — unwrap to `T`, then recurse the rule.

### Do NOT infer when

- No return annotation at all.
- Primitives: `str`, `int`, `float`, `bool`, `bytes`.
- Bare unparameterized containers: `dict`, `list`, `tuple`, `set`.
- `None` / `type(None)` / `typing.Any`.
- `Response` or any subclass (`JSONResponse`, `HTMLResponse`, etc.) — user is returning a Response object directly.
- `get_type_hints` raises (forward-ref resolution failure) — fall back silently.

### Explicit wins

If the user passes `response_model=X`, that value is used unchanged — even when a return annotation is also present. Preserves the existing opt-out.

```python
@app.get("/items", response_model=Raw)  # Raw is used
async def list_items() -> list[Item]: ...  # annotation ignored
```

For users who want to *force* skip inference, the recommended patterns are (a) omit the return annotation, or (b) annotate with `Response` / a subclass.

## Implementation

One new helper in `src/hawkapi/routing/router.py`:

```python
def _infer_response_model(handler: Any) -> type[Any] | None:
    """Return the handler's return-annotation as a response_model, or None.

    See docs/plans/2026-04-18-tier3-typed-routes-design.md for inclusion /
    exclusion rules.
    """
    from typing import Any as _Any
    from typing import get_type_hints
    try:
        hints = get_type_hints(handler, include_extras=False)
    except Exception:
        return None
    ret = hints.get("return", None)
    if ret is None or ret is type(None) or ret is _Any:
        return None
    from hawkapi.responses.response import Response
    if isinstance(ret, type) and issubclass(ret, Response):
        return None
    if ret in (str, int, float, bool, bytes):
        return None
    if ret in (dict, list, tuple, set, frozenset):
        return None
    return ret
```

Call it inside `Router.add_route`:

```python
def add_route(self, ..., response_model=None, ...):
    if response_model is None:
        response_model = _infer_response_model(handler)
    ...
```

All downstream code (`_apply_response_model` in `app.py`, OpenAPI schema generation, codegen) already handles any type in `response_model`.

## Tests (`tests/unit/test_auto_response_model.py`)

- `test_annotation_msgspec_struct_is_used` — `-> Item:` without `response_model=` uses `Item`.
- `test_annotation_pydantic_model_is_used` — with `pytest.importorskip("pydantic")`.
- `test_annotation_list_of_struct_is_used` — `-> list[Item]:`.
- `test_explicit_response_model_wins` — `response_model=Other` + annotation `Item` → `Other`.
- `test_no_return_annotation_no_inference` — handler without `->` → `Route.response_model is None`.
- `test_none_annotation_no_inference` — `-> None:` → not used.
- `test_response_subclass_no_inference` — `-> JSONResponse:` → not used.
- `test_primitive_return_no_inference` — `-> str:` / `-> int:` → not used.
- `test_bare_list_no_inference` — `-> list:` (unparameterized) → not used.
- `test_any_annotation_no_inference` — `-> Any:` → not used.
- `test_optional_of_struct_is_used` — `-> Item | None:` → used (parameterized Union).
- Integration: `@app.get("/x")` with return annotation → endpoint response matches schema.

## Out of scope

- **Typed `app.url_for`** — nice-to-have follow-up.
- **Mypy plugin** — separate, larger effort.
- **Auto-generate `status_code` from annotations.**
- **Auto-response-model on WebSocket routes** — not applicable.
- **Warnings when annotation and explicit kwarg differ** — could be noisy; stay silent.

## Success criteria

1. Handler with `-> Item:` and no `response_model=` routes through msgspec coercion using `Item` at response time.
2. Explicit `response_model=X` always wins.
3. `-> Response` / `-> None` / `-> str` do not trigger inference (zero regression).
4. OpenAPI `components.schemas` includes the inferred type.
5. `gen-client` (Tier 3a) sees the inferred schema.
6. All existing tests stay green; `tests/unit/test_auto_response_model.py` adds 10+ new tests.
7. Ruff + mkdocs strict clean.

## Files touched

- `src/hawkapi/routing/router.py` — `_infer_response_model` helper + one-line call in `add_route`.
- `tests/unit/test_auto_response_model.py` — new.
- `CHANGELOG.md` — one bullet.

## Rollback

Remove the helper + the one-line call; delete the test file. No existing behavior relies on auto-inference.
