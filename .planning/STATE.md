# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-08)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v3.0 Async Graphs — parallel dep resolution + subgraph composition

## Current Position

Phase: 12 of 12 (Parallel Deps Migration)
Plan: 4 of 4 complete
Status: Phase complete
Last activity: 2026-02-09 — Completed 12-04-PLAN.md (parallel dep resolution tests)

Progress: [████████████████████████████████] 100% v3.0 (Phase 11 done + 12-01..04 complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 42 (13 v1.0 + 21 v2.0 + 8 v3.0)
- v2.0 duration: 2 days (2026-02-07 → 2026-02-08)
- v2.0 commits: 106
- v3.0 duration: in progress
- v3.0 commits: 9

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
- resolve_fields() and resolve_dep() now async with topo-sort gather (Phase 12-01)
- _build_fn_dag() helper added for resolve_dep mini-DAG (kept build_dep_dag unchanged)
- inspect.iscoroutinefunction for runtime sync/async dep callable detection
- Graph.run() is sync (asyncio.run boundary), Graph.arun() is async (Phase 12-02)
- All tests use graph.arun() in async contexts, graph.run() for sync callers
- Module-scope dep functions required for PEP 649 -- get_type_hints resolves in module scope
- Phase 12 complete: 344 tests collected, 334 pass, 10 skip, 0 failures

### Pending Todos

- Update `tests/traces/json_structured_fill_reference.py` — drifted from real backend
- Bump Python requirement to 3.14 stable
- **OTel observability**: Add OpenTelemetry spans with decorators for node ins/outs. Jaeger in Docker for local trace visualization.
- **Replace CLI trace capture with logging**: Standard Python logger for all fill/choose_type ins and outs. Custom Formatter/Handler for dumping to file.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-09
Stopped at: Completed 12-04-PLAN.md (parallel dep resolution tests) -- Phase 12 complete
Branch: 11-async-core
Resume file: None
