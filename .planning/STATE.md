# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-07)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** ALL PHASES COMPLETE

## Current Position

Phase: 8 of 8 (Cleanup & Migration) — COMPLETE
Plan: 04 of 04 complete
Status: Complete
Last activity: 2026-02-08 — Completed 08-04-PLAN.md (phase gate: fix CompiledGraph.run(), full suite, E2E validation)

Progress: [##############################] 100% (30/30 plans complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 30 (13 v1.0 + 17 v2.0)
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
| 5. Markers & Resolver | 4/4 | ~25min | ~6min |
| 6. Node & LM Protocol | 5/5 | ~40min | ~8min |
| 7. Integration | 4/4 | ~20min | ~5min |
| 8. Cleanup & Migration | 4/4 | ~11min | ~3min |

*All phases complete*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
v2 design decisions documented in PROJECT.md v2 Design Decisions section.

Key v2 decisions affecting Phase 5:
- Use `model_construct()` for internal node creation (bypass Pydantic validation for deferred field population)
- `graphlib.TopologicalSorter` for dep chain resolution and cycle detection
- Dep on start node is allowed (auto-resolved); Recall on start node is an error
- Per-run dep caching (same dep function + args = cached result within one graph run)
- Dep.fn is first positional field so `Dep(callable)` works without keyword (description kwarg removed in Phase 8)
- classify_fields() skips "return" key from get_type_hints
- build_dep_dag uses id(fn) for visited set deduplication
- validate_node_deps calls build_dep_dag internally for cycle detection
- Only first marker per field processed in validation (consistent with classify_fields)
- recall_from_trace uses issubclass(field_type, target_type) direction for MRO matching
- recall_from_trace skips Dep and Recall annotated fields (infrastructure, not LLM-filled)
- resolve_dep cache keyed by callable identity (fn object), not function name
- Dep function exceptions propagate raw (no BaeError wrapping)
- resolve_fields returns only Dep and Recall field values, not plain fields

Key v2 decisions from Phase 6:
- NodeConfig is standalone TypedDict (not extending Pydantic ConfigDict)
- _wants_lm checks for 'lm' parameter in __call__ signature
- node_to_signature uses classify_fields from resolver (not Context markers)
- is_start parameter controls plain field direction (InputField vs OutputField)
- choose_type/fill take context dict, not node instance (decoupled from v1)
- Single-type lists skip LLM call entirely (optimization on all backends)
- DSPyBackend.fill uses model_construct to merge context + LM output

Key v2 decisions from Phase 7:
- _get_base_type kept in graph.py (compiler.py imports it, not incant-specific)
- recall_from_trace skips Dep fields; tests use bridge node pattern for Recall
- max_iters=0 means infinite (falsy check skips iteration guard)
- Terminal nodes appended to trace before loop exit
- Graph.run() no longer accepts **kwargs (external dep injection removed)
- MockLMs keep v1 make/decide as stubs for custom __call__ nodes that invoke them
- v1 incant tests deleted (not ported) — v2 dep resolution covered by test_dep_injection.py
- incant removed from pyproject.toml dependencies

Key decisions from Phase 8:
- _build_inputs collects all node model_fields (not just Context-annotated) — correct v2 behavior
- v1 make/decide kept on LM Protocol for custom __call__ escape-hatch nodes (docstring updated)
- Dep.description removed — Dep(callable) is the only constructor form
- E2E tests gated behind --run-e2e flag to avoid CI failures without API keys
- Structural validation sufficient for phase gate when no LLM key available

### Pending Todos

None.

### Blockers/Concerns

- **Claude CLI session noise**: Optimizer runs create many boring test sessions that drown out real sessions in Claude CLI history. When using ClaudeCLIBackend for optimization, set the "don't save session to disk" flag to avoid polluting session history.

## Session Continuity

Last session: 2026-02-08
Stopped at: Completed 08-04-PLAN.md — ALL PHASES COMPLETE (30/30 plans)
Resume file: None
