# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-08)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v3.0 Async Graphs — parallel dep resolution + subgraph composition

## Current Position

Phase: 11 (Async Core) — 4 plans
Plan: 04 of 4 (11-01, 11-02, 11-03, 11-04 complete)
Status: Phase complete
Last activity: 2026-02-09 — Completed 11-04-PLAN.md (full test suite verification)

Progress: [████████████████████████████████] 100% Phase 11 (4/4 plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 38 (13 v1.0 + 21 v2.0 + 4 v3.0)
- v2.0 duration: 2 days (2026-02-07 → 2026-02-08)
- v2.0 commits: 106
- v3.0 duration: in progress
- v3.0 commits: 7

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table and milestones/v2.0-ROADMAP.md for full decision history.

v3.0 decisions so far:
- Pivoted from evals to async — parallel deps + subgraph composition is more fundamental
- Full async, not threading — correct long-term play, formulaic conversion
- Dep is already fan-out/join primitive — async makes it concurrent
- Eval research preserved in .planning/research/ for v4.0
- System prompt not needed — class name + Field(description) carries the weight
- PydanticAI backend may be removed — LM proxies making backends commodity
- Used predictor.acall() for native async DSPy calls (not asyncio.to_thread)
- Pure computation methods kept sync — no I/O, no benefit from async
- DSPy mock predictors use predictor.acall() (async) not predictor() (sync)
- Node.__call__ is async def — all subclasses must use async def __call__
- resolve_fields() stays sync in Phase 11 (async is Phase 12)
- CLI uses asyncio.run() as sync boundary (Typer doesn't support async)
- Phase 11 async core verified complete — 313/323 tests pass, 0 failures

### Pending Todos

- Update `tests/traces/json_structured_fill_reference.py` — drifted from real backend
- Bump Python requirement to 3.14 stable
- **OTel observability**: Add OpenTelemetry spans with decorators for node ins/outs. Jaeger in Docker for local trace visualization.
- **Replace CLI trace capture with logging**: Standard Python logger for all fill/choose_type ins and outs. Custom Formatter/Handler for dumping to file.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-09
Stopped at: Completed 11-04-PLAN.md (Phase 11 complete)
Branch: 11-async-core
Resume file: None
