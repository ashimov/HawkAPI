# DX audit vs FastAPI — design spec

**Status:** Draft — awaiting user review
**Date:** 2026-04-18
**Scope:** Research-only document. No code changes. Output is a single markdown file comparing HawkAPI's developer-experience surface against FastAPI, with prioritized gaps.

---

## Goal

Produce a fact-based picture of where HawkAPI matches, lags, or exceeds FastAPI on feature-level DX, so the next wave of implementation work (closing DX-parity gaps, then adding differentiators) is driven by evidence rather than intuition.

## Deliverable

A single file: `docs/audits/2026-04-18-dx-vs-fastapi.md`.

### Structure

1. **Executive summary** (~2 paragraphs) — top-level findings, the five gaps that matter most.
2. **Feature-parity matrix** — tables grouped by topic:
   - Routing & path operations
   - Parameters: path / query / header / cookie / body
   - Forms & file uploads
   - Dependency injection
   - Security (OAuth2, APIKey, HTTPBasic, scopes)
   - Response handling (response_model, status codes, content types)
   - OpenAPI customization
   - Middleware & exception handlers
   - Testing utilities
   - Background tasks & lifespan events
   - WebSockets
   - Static files & templates
   - Routers & sub-apps
   
   Each row: `FastAPI feature | HawkAPI equivalent (with file/module) | Status | Notes`. Status is one of ✅ full, ⚠️ partial, ❌ missing.
3. **Top-5 gaps** — the subset of the matrix with the highest `user impact × effort` payoff. Each item gets severity (critical / important / minor), effort estimate (S / M / L), and enough detail to start a spec without redoing the research.
4. **Where HawkAPI already exceeds FastAPI** — brief list (versioning, permissions, observability, bulkhead, free-threaded wheels, migrate codemod, etc.). Avoids tunnel-vision on the gaps.

## Method

- Walk the FastAPI tutorial (`fastapi.tiangolo.com/tutorial/`) section by section — ~20 pages.
- For each feature, search `src/hawkapi/` for the equivalent with `Grep` / `Read`; note the file path.
- Record status honestly: ✅ only when the behavior is first-class, not when it "can be done manually."
- For `⚠️ partial` and `❌ missing`, write one sentence on what would be needed.
- Pick the top-5 by user impact (how often the feature gets used in FastAPI tutorials and real code) weighted by effort (prefer lower-effort wins first).

## Out of scope

- No source-code changes. This PR ships exactly one new markdown file.
- No performance benchmarks (separate follow-up project).
- No comparison with Litestar / BlackSheep / Starlette / Sanic. FastAPI is the reference because it sets the DX bar users expect.
- No speculation about features FastAPI might add; audit is a snapshot.
- No mock code or "proof of concept" implementations of missing features. Those get their own spec cycles later.

## Success criteria

1. Every subsection of the FastAPI tutorial is represented in the matrix.
2. Every row points to a specific HawkAPI file/module (or an explicit "missing").
3. The top-5 gaps list is concrete enough to drive follow-up specs without re-research — no "TBD" entries.
4. The document is committable: mkdocs `--strict` build stays clean (the file lives under `docs/` but not in `mkdocs.yml` nav — it's a working doc, not end-user docs).

## Follow-ups (not this project)

After the audit lands, each top-5 gap becomes an independent sub-project with its own design spec + plan. The audit document itself is not expected to change except corrections.
