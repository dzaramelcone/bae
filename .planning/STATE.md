# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-08)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v3.0 Async Graphs — parallel dep resolution + subgraph composition

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining scope
Last activity: 2026-02-08 — Pivoted v3.0 from evals to async

Progress: [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 0% v3.0

## Performance Metrics

**Velocity:**
- Total plans completed: 34 (13 v1.0 + 21 v2.0)
- v2.0 duration: 2 days (2026-02-07 → 2026-02-08)
- v2.0 commits: 106

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

### Pending Todos

- Update `tests/traces/json_structured_fill_reference.py` — drifted from real backend
- Bump Python requirement to 3.14 stable
- **OTel observability**: Add OpenTelemetry spans with decorators for node ins/outs. Jaeger in Docker for local trace visualization.
- **Replace CLI trace capture with logging**: Standard Python logger for all fill/choose_type ins and outs. Custom Formatter/Handler for dumping to file.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-08
Stopped at: v3.0 pivoted to async — need requirements + roadmap
Branch: main
Resume file: None
