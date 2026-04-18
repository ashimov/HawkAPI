# DX Gap #5 — `hawkapi.status` constants module

**Status:** Approved — ready for implementation
**Date:** 2026-04-18
**Scope:** Smallest of the top-5 DX gaps identified in the 2026-04-18 FastAPI parity audit. Ship a `hawkapi.status` module re-exporting the canonical HTTP and WebSocket status-code constants so users can write `status.HTTP_201_CREATED` instead of `201`.

**Audit:** [docs/audits/2026-04-18-dx-vs-fastapi.md](../audits/2026-04-18-dx-vs-fastapi.md) (Gap #5)

---

## Goal

`from hawkapi import status` works the same as `from fastapi import status`. Eliminates a paper-cut that shows up in every FastAPI tutorial the user has ever read.

## What ships

1. **New: `src/hawkapi/status.py`** — a pure-constants module.
   - HTTP status codes as `HTTP_<code>_<REASON_PHRASE>` integers.
   - Values derived programmatically from Python's `http.HTTPStatus` enum so the list never drifts from stdlib.
   - Names match Starlette's `starlette.status` namespace exactly (this is the convention FastAPI users know). For status codes that Python's enum uses a slightly different phrase for, we follow Starlette's naming verbatim (for example `HTTP_418_IM_A_TEAPOT` not `HTTP_418_IM_A_TEAPOT_TEAPOT`).
   - WebSocket close codes as `WS_<code>_<REASON>` integers, matching Starlette:
     ```
     WS_1000_NORMAL_CLOSURE = 1000
     WS_1001_GOING_AWAY = 1001
     WS_1002_PROTOCOL_ERROR = 1002
     WS_1003_UNSUPPORTED_DATA = 1003
     WS_1005_NO_STATUS_RCVD = 1005
     WS_1006_ABNORMAL_CLOSURE = 1006
     WS_1007_INVALID_FRAME_PAYLOAD_DATA = 1007
     WS_1008_POLICY_VIOLATION = 1008
     WS_1009_MESSAGE_TOO_BIG = 1009
     WS_1010_MANDATORY_EXT = 1010
     WS_1011_INTERNAL_ERROR = 1011
     WS_1012_SERVICE_RESTART = 1012
     WS_1013_TRY_AGAIN_LATER = 1013
     WS_1014_BAD_GATEWAY = 1014
     WS_1015_TLS_HANDSHAKE = 1015
     ```
   - `__all__` lists every exported name so `from hawkapi.status import *` works cleanly.

2. **Modify: `src/hawkapi/__init__.py`** — add `from hawkapi import status` so `hawkapi.status` is a real attribute of the top-level package. (Sub-module imports don't shadow anything; there's no existing `status` attribute.)

3. **New: `tests/unit/test_status.py`** — small sanity test:
   - Imports succeed via both `from hawkapi import status` and `from hawkapi.status import HTTP_200_OK`.
   - A handful of integer values: `HTTP_200_OK == 200`, `HTTP_201_CREATED == 201`, `HTTP_404_NOT_FOUND == 404`, `HTTP_500_INTERNAL_SERVER_ERROR == 500`.
   - At least one WebSocket value: `WS_1000_NORMAL_CLOSURE == 1000`.
   - `status.__all__` lists every public name.

4. **Modify: `CHANGELOG.md`** — one-line bullet under `[Unreleased] ### Added`:
   ```
   - `hawkapi.status` module — HTTP and WebSocket status-code constants (FastAPI parity)
   ```

## Derivation approach

```python
# src/hawkapi/status.py
"""HTTP and WebSocket status-code constants.

Usage:
    from hawkapi import status
    @app.post("/items", status_code=status.HTTP_201_CREATED)

Names follow Starlette's ``starlette.status`` namespace so that code
migrated from FastAPI keeps working without edits. Integer values come
from the stdlib ``http.HTTPStatus`` enum (for HTTP codes) and from
RFC 6455 section 7.4 (for WebSocket close codes).
"""
from __future__ import annotations

from http import HTTPStatus as _HTTPStatus


def _http_name(code: _HTTPStatus) -> str:
    return f"HTTP_{code.value}_{code.name}"


# Starlette uses slightly different names for a handful of codes
# where Python's ``http.HTTPStatus`` was renamed to match RFC 9110.
# Keep the Starlette names so FastAPI migrators have zero friction.
_STARLETTE_OVERRIDES: dict[int, str] = {
    413: "HTTP_413_REQUEST_ENTITY_TOO_LARGE",        # stdlib: CONTENT_TOO_LARGE
    414: "HTTP_414_REQUEST_URI_TOO_LONG",            # stdlib: URI_TOO_LONG
    416: "HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE", # stdlib: RANGE_NOT_SATISFIABLE
}

for _code in _HTTPStatus:
    globals()[_STARLETTE_OVERRIDES.get(_code.value, _http_name(_code))] = _code.value

del _code

# WebSocket close codes (RFC 6455 + common extensions).
WS_1000_NORMAL_CLOSURE = 1000
WS_1001_GOING_AWAY = 1001
# ... etc
```

Then `__all__` is built by listing every module-level name that starts with `HTTP_` or `WS_`.

## Out of scope

- Any retrofit of existing code where integer status codes are hardcoded. Separate cleanup, not urgent.
- Deprecation messages ("prefer status.HTTP_* over integers"). Users can opt in at their pace.
- Any WebSocket close codes beyond RFC 6455's 1000–1015 range. Private/application ranges (3000–3999, 4000–4999) are intentionally omitted — they're application-specific.

## Success criteria

1. `from hawkapi import status` works and `status.HTTP_201_CREATED == 201`.
2. `from hawkapi.status import HTTP_200_OK` works.
3. All HTTP codes from `http.HTTPStatus` are present, using Starlette's three-name-override for 413/414/416.
4. All 15 WebSocket close codes (1000–1015, skipping 1004 which is reserved) are present.
5. Unit tests + ruff + full unit suite all green; no regressions.

## Tasks (inline — skipping a separate plan doc because scope is XS)

1. Write `tests/unit/test_status.py` with expected values (red).
2. Create `src/hawkapi/status.py` with the generation logic.
3. Add `from hawkapi import status` to `src/hawkapi/__init__.py`.
4. Verify tests green; ruff + format clean.
5. CHANGELOG entry.
6. Single commit per logical step, or one squashed commit — implementer's call.

## Rollback

New module + one new import line + one new test file + one CHANGELOG line. Fully reversible by deleting the three added files and reverting the `__init__.py` / `CHANGELOG.md` hunks.
