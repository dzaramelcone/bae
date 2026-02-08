# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-07)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** Phase 5 — Markers & Resolver

## Current Position

Phase: 5 of 8 (Markers & Resolver)
Plan: 3 of 4 in current phase
Status: In progress
Last activity: 2026-02-08 — Completed 05-03-PLAN.md

Progress: [############........] 62% (16/26 plans complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 16 (13 v1.0 + 3 v2.0)
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Signature Generation | 1 | — | — |
| 1.1 Deps & Signature Extension | 1 | — | — |
| 2. DSPy Integration | 5 | — | — |
| 3. Optimization | 4 | — | — |
| 4. Production Runtime | 2 | — | — |
| 5. Markers & Resolver | 3/4 | ~20min | ~7min |

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
v2 design decisions documented in PROJECT.md v2 Design Decisions section.

Key v2 decisions affecting Phase 5:
- Use `model_construct()` for internal node creation (bypass Pydantic validation for deferred field population)
- `graphlib.TopologicalSorter` for dep chain resolution and cycle detection
- Dep on start node is allowed (auto-resolved); Recall on start node is an error
- Per-run dep caching (same dep function + args = cached result within one graph run)
- Dep.fn is first positional field so `Dep(callable)` works without keyword; v1 compat preserved via `description` kwarg
- classify_fields() skips "return" key from get_type_hints
- build_dep_dag uses id(fn) for visited set deduplication
- validate_node_deps calls build_dep_dag internally for cycle detection
- Only first marker per field processed in validation (consistent with classify_fields)
- recall_from_trace uses issubclass(field_type, target_type) direction for MRO matching
- recall_from_trace skips Dep and Recall annotated fields (infrastructure, not LLM-filled)

### Pending Todos

None.

### Blockers/Concerns

- **Claude CLI session noise**: Optimizer runs create many boring test sessions that drown out real sessions in Claude CLI history. When using ClaudeCLIBackend for optimization, set the "don't save session to disk" flag to avoid polluting session history.

## Session Continuity

Last session: 2026-02-08
Stopped at: Completed 05-03-PLAN.md
Resume file: None
