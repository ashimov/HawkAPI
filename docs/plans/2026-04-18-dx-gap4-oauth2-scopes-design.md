# DX Gap #4 — OAuth2 scopes enforcement + OpenAPI reflection

**Status:** Approved — ready for implementation
**Date:** 2026-04-18
**Scope:** Last remaining of the top-5 DX gaps. Add first-class OAuth2 scope support: `Security(dep, scopes=[...])` marker, `SecurityScopes` injected context, per-route scope aggregation, and OpenAPI `security` reflection.

**Audit:** [docs/audits/2026-04-18-dx-vs-fastapi.md](../audits/2026-04-18-dx-vs-fastapi.md) (Gap #4)

---

## Goal

```python
from hawkapi import Depends, Security, HawkAPI, HTTPException
from hawkapi.security import OAuth2PasswordBearer, SecurityScopes

oauth2 = OAuth2PasswordBearer(
    token_url="/auth/token",
    scopes={"read:items": "Read items", "admin": "Admin"},
)

async def current_user(
    security_scopes: SecurityScopes,
    token: str = Depends(oauth2),
) -> User:
    user = decode(token)
    for required in security_scopes.scopes:
        if required not in user.scopes:
            raise HTTPException(403, "Insufficient scope")
    return user

@app.get(
    "/items",
    dependencies=[Security(current_user, scopes=["read:items"])],
)
async def list_items(): ...
```

Everything a FastAPI user types for scope-aware auth works unchanged.

## Semantics

1. **`Security(dependency, *, scopes=[])`** subclasses `Depends` — any code that accepts `Depends` also accepts `Security`.
2. **`SecurityScopes`** is a plain dataclass `{scopes: tuple[str, ...], scope_str: str}` injected by the framework at request time. Callables receive it by naming a param annotated `SecurityScopes`.
3. **Per-route aggregation**: every `Security().scopes` in `dependencies=[...]` and in the handler signature merges into one `required_scopes` set for that route.
4. **No auto-enforcement**: the framework **does not** check whether the token carries the required scopes. The user's callable does that (matching FastAPI). The framework only makes the required list available and reflects it in OpenAPI.
5. **OpenAPI reflection**: routes with required scopes emit `security: [{scheme_name: [required_scopes...]}]`. If multiple security schemes are detected, the scopes attach to the first one (documented limitation — multi-scheme scope routing is follow-up).
6. **Zero regression** for existing `OAuth2PasswordBearer()` usage that doesn't pass `scopes=`.

## Implementation

### `src/hawkapi/security/scopes.py` (new)

```python
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any
from hawkapi.di.depends import Depends


class Security(Depends):
    """Like ``Depends`` but also carries a required-scope list."""

    __slots__ = ("scopes",)

    def __init__(
        self,
        dependency: Any = None,
        *,
        scopes: Sequence[str] | None = None,
    ) -> None:
        super().__init__(dependency=dependency)
        self.scopes: list[str] = list(scopes) if scopes else []


@dataclass(frozen=True, slots=True)
class SecurityScopes:
    """Container for scopes required by the current route.

    Framework-injected into any callable whose signature declares a param
    annotated ``SecurityScopes``. The user inspects ``.scopes`` inside the
    callable and decides whether to reject the request.
    """

    scopes: tuple[str, ...] = ()

    @property
    def scope_str(self) -> str:
        """Space-separated scope list — formatted for the OAuth2 spec."""
        return " ".join(self.scopes)
```

### `src/hawkapi/security/oauth2.py`

Extend `OAuth2PasswordBearer.__init__` to accept `scopes: dict[str, str] | None = None` and reflect it in `openapi_scheme.flows.password.scopes`.

### `src/hawkapi/security/__init__.py` and `src/hawkapi/__init__.py`

Re-export `Security`, `SecurityScopes`.

### `src/hawkapi/di/param_plan.py`

- New `ParamSource.SECURITY_SCOPES`.
- In `_build_dep_callable_plan`, detect `SecurityScopes`-annotated params and emit `ParamSpec(source=ParamSource.SECURITY_SCOPES)`.
- New helper `collect_route_scopes(deps, handler)` walks deps + handler signature, collects all `Security().scopes` into a sorted deduplicated tuple.

### `src/hawkapi/routing/route.py`

Add field `required_scopes: tuple[str, ...] = ()`.

### `src/hawkapi/routing/router.py`

At `add_route` time, call `collect_route_scopes` on the merged deps + handler; store result on `Route.required_scopes`.

### `src/hawkapi/di/resolver.py`

Change `_execute_dep_plan` signature to accept an optional `security_scopes: SecurityScopes | None = None`. When a `ParamSpec` has `source == SECURITY_SCOPES`, inject the passed-in `security_scopes` (or an empty `SecurityScopes()` if None).

### `src/hawkapi/app.py`

Construct `SecurityScopes(scopes=route.required_scopes)` once per request; pass to every `_execute_dep_plan` call (side-effect deps + main handler plan resolution).

### `src/hawkapi/openapi/schema.py`

- When building `operation.security`: if `route.required_scopes` is non-empty AND at least one security scheme was detected, populate the first scheme's scope list with `route.required_scopes`.
- Ensure `OAuth2PasswordBearer.openapi_scheme` already propagates the user-supplied `scopes` dict into `components.securitySchemes.OAuth2PasswordBearer.flows.password.scopes`.

### Tests (`tests/unit/test_oauth2_scopes.py`)

- `OAuth2PasswordBearer(scopes={...})` reflects in OpenAPI `components.securitySchemes`.
- `Security(fn, scopes=[...])` adds required scopes to the route.
- `SecurityScopes` param injected with correct list when the dep is invoked.
- Multiple `Security()` on one route → scopes aggregated, deduplicated.
- OpenAPI operation.security emits required scopes under the scheme name.
- Existing `OAuth2PasswordBearer()` without scopes still works (no regression).
- `security_scopes.scope_str` returns space-separated string.

### CHANGELOG

One `[Unreleased] ### Added` bullet.

## Out of scope

- **Auto-enforcement of scopes** — user writes the scope check inside their callable. Matches FastAPI.
- **Multi-scheme scope routing** — if a route uses two different `SecurityScheme` instances, scopes go to the first. Follow-up if a real user asks.
- **`OAuth2AuthorizationCodeBearer` / `OAuth2ClientCredentials`** flows — only Password flow here.
- **`OAuth2PasswordRequestForm`** helper — second-tier item, separate spec if prioritized.

## Success criteria

1. `OAuth2PasswordBearer(..., scopes={...})` reflects in OpenAPI document.
2. `Security(fn, scopes=["x"])` stores scope on the route; OpenAPI operation reflects it.
3. `SecurityScopes` param properly injected.
4. Aggregation: multiple Security() → combined scopes, deduplicated.
5. No regressions in existing OAuth2PasswordBearer tests.
6. Full unit suite + lint + format stay clean.

## Files touched

- `src/hawkapi/security/scopes.py` (new)
- `src/hawkapi/security/oauth2.py` (`scopes` kwarg + openapi reflect)
- `src/hawkapi/security/__init__.py` (re-export)
- `src/hawkapi/__init__.py` (re-export)
- `src/hawkapi/di/param_plan.py` (new ParamSource + collect helper)
- `src/hawkapi/di/resolver.py` (SecurityScopes injection)
- `src/hawkapi/routing/route.py` (+required_scopes field)
- `src/hawkapi/routing/router.py` (+aggregation in add_route)
- `src/hawkapi/app.py` (pass SecurityScopes into dep execution)
- `src/hawkapi/openapi/schema.py` (scope reflection on operation.security)
- `tests/unit/test_oauth2_scopes.py` (new)
- `CHANGELOG.md` (+1 line)

## Rollback

New public API (`Security`, `SecurityScopes`) + additive kwargs on existing classes. No existing behavior changes when scopes are unused. Revert is squash-safe.
