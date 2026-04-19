# Tier 3 — OpenAPI client codegen (TS + Python) — design spec

**Status:** Approved — ready for implementation
**Date:** 2026-04-18
**Scope:** Ship `hawkapi gen-client` — a CLI + library that generates zero-runtime-dependency client SDKs (TypeScript + Python) from a HawkAPI app's OpenAPI 3.1 spec.

---

## Goal

```bash
# From live app
hawkapi gen-client python --app myapp.main:app --out ./clients/python/
hawkapi gen-client typescript --app myapp.main:app --out ./clients/ts/

# From exported spec
hawkapi gen-client python --spec openapi.json --out ./clients/python/
```

Generated output:

- **Python** (`client.py`) — msgspec Structs for all schemas, `Client` class with async methods backed by `httpx.AsyncClient`, typed responses, `ApiError` exception.
- **TypeScript** (`client.ts`) — `interface`/`type` declarations for schemas, `Client` class with async methods backed by native `fetch`, typed responses, `ApiError` class.

Both outputs are **single-file**, **zero-dep-at-generation-time** (only the generated file's runtime deps — httpx/msgspec for Python, fetch for TS), pass `mypy --strict` / `tsc --strict`.

## Why this matters

FastAPI users reach for `openapi-generator-cli` (Java/Node dependency) and get bloated clients with poor types and no async. A framework-native `gen-client` eliminates that tool from their pipeline.

## Architecture

Single-input / multi-output pipeline:

```
OpenAPI 3.1 dict ──▶ parser.py (ClientIR) ──┬─▶ python.py   ──▶ client.py
                                             └─▶ typescript.py ──▶ client.ts
```

**`ClientIR`** (intermediate representation) — a small, language-agnostic dataclass tree:

```python
@dataclass(frozen=True, slots=True)
class ClientIR:
    title: str
    version: str
    base_url: str | None
    schemas: tuple[SchemaIR, ...]
    operations: tuple[OperationIR, ...]
```

(Full shape — `OperationIR`, `SchemaIR`, `FieldIR`, `ParamIR` — in `src/hawkapi/openapi/codegen/ir.py`.)

Renderers consume `ClientIR` and emit strings. No jinja2 — pure Python string building keeps the renderer debuggable and the build dependency graph minimal.

## Components

### `src/hawkapi/openapi/codegen/parser.py`

`build_client_ir(spec: dict) -> ClientIR` — reads an OpenAPI 3.1 dict and produces `ClientIR`.

Handles:
- `components.schemas` → `SchemaIR` tree, `$ref` resolution within the spec.
- Each `paths.*.(get|post|put|patch|delete)` → `OperationIR`.
- `servers[0].url` → `base_url` hint (nullable).
- `operationId` → method name (fallback: `METHOD_path_slug` with non-alphanumeric chars replaced by `_`).

### `src/hawkapi/openapi/codegen/python.py`

`generate_python_client(ir: ClientIR) -> str` — produces a single `.py` file string with:

- `ApiError(Exception)` with `status_code` + `detail`.
- `Client` class: ctor `(base_url, *, headers=None, client=None)`; owns `httpx.AsyncClient` if none passed; `aclose()` closes only if owned.
- One method per operation. Path params positional, others keyword-only.
- `response_type` decoded via `msgspec.convert(r.json(), type=T)`; errors raise `ApiError`.
- Body (if present) serialised via `msgspec.json.encode(body)` → `httpx` `content=`.
- `None` for optional query params → skipped from dict.

### `src/hawkapi/openapi/codegen/typescript.py`

`generate_typescript_client(ir: ClientIR) -> str` — produces a single `.ts` file string with:

- `interface` per schema Struct; union types for enums; direct type aliases for arrays/primitives.
- `Client` class: ctor `({ baseUrl, headers?, fetch? })`; uses `globalThis.fetch` if not provided.
- Method names are lowerCamelCase of `operationId`.
- Path/query/header params bundled into one `params?` object.
- Body goes in `body?` (JSON-stringified).
- `ApiError extends Error` with `status` + `detail`.
- TS 4.5+ (no ESM-only features beyond `import type`).

### `src/hawkapi/cli.py` — new `gen-client` subcommand

Parser:

```python
sub = subparsers.add_parser("gen-client")
sub.add_argument("language", choices=["python", "typescript"])
group = sub.add_mutually_exclusive_group(required=True)
group.add_argument("--app", help="module:attr of the HawkAPI instance")
group.add_argument("--spec", help="path to openapi.json")
sub.add_argument("--out", required=True, help="output directory")
```

Dispatcher loads either `generate_openapi(app)` (via `--app`) or `json.load(open(spec))` (via `--spec`), passes to `build_client_ir`, renders, writes `client.py` or `client.ts`, prints output path.

### Tests (`tests/unit/test_codegen.py`)

- `build_client_ir` on a minimal spec → expected IR (deep-eq).
- Python renderer: generate, parse with `ast.parse` (must be valid Python).
- Python renderer: compile + exec into a namespace; instantiate `Client`; monkey-patch a fake `httpx.AsyncClient`; call a method; assert on request shape.
- TS renderer: generate, parse with regex that the file has expected shape (robust across runners).
- CLI: `hawkapi gen-client python --spec fixtures/minimal.json --out ./tmp/` produces a file; re-import succeeds.
- Schema coverage: path param, query param, body (Struct), response (Struct), list response, optional query, enum, nested schemas.

### Docs (`docs/guide/client-codegen.md`)

Brief guide: when to use, CLI invocation, generated client usage examples (Python + TS), regeneration workflow (CI integration suggestion: regen on release).

### Mkdocs nav + CHANGELOG

- `mkdocs.yml`: new `Client codegen` entry in Guide (after Benchmarks).
- `CHANGELOG.md`: one `[Unreleased] ### Added` bullet.

## Out of scope

- **Multi-file package output** (`setup.py`, `package.json`, README). v2.
- **Go / Rust / Java clients.** v2 (would need a more generic IR + jinja2 templates).
- **OAuth2 auto-injection**, cookie-auth, CSRF dance — user passes `headers` / cookies to the Client ctor.
- **Streaming responses**, **WebSocket endpoints** — OpenAPI doesn't describe them well.
- **Pagination helpers** (auto-iterating over `Page[T]`). v2.
- **Versioning — regenerate on schema change detection** (would need a content hash + warning). v2.
- **Pydantic support** in generated Python client — msgspec-only for v1.

## Success criteria

1. `hawkapi gen-client python --app demo:app --out py_client/` creates a working `client.py`.
2. `hawkapi gen-client typescript --app demo:app --out ts_client/` creates a working `client.ts`.
3. Generated Python client parses cleanly with `ast.parse`.
4. Generated TS client matches the expected shape (smoke-regex tests).
5. Unit-tests: 10+ cases covering ref-resolution, every operation shape, and both renderers.
6. `docs/guide/client-codegen.md` in nav; mkdocs strict build clean.

## Files touched

- `src/hawkapi/openapi/codegen/__init__.py` — public API
- `src/hawkapi/openapi/codegen/ir.py` — dataclasses (ClientIR, OperationIR, SchemaIR, FieldIR, ParamIR)
- `src/hawkapi/openapi/codegen/parser.py` — OpenAPI → `ClientIR`
- `src/hawkapi/openapi/codegen/python.py` — renderer
- `src/hawkapi/openapi/codegen/typescript.py` — renderer
- `src/hawkapi/cli.py` — `gen-client` subcommand + dispatcher
- `tests/unit/test_codegen.py` — new
- `docs/guide/client-codegen.md` — new
- `mkdocs.yml` — nav entry
- `CHANGELOG.md` — bullet

## Rollback

New module tree + new CLI subcommand + new docs. No existing code paths change. Revert is squash-safe: delete `codegen/`, remove the CLI subcommand branch, revert docs/changelog diffs.
