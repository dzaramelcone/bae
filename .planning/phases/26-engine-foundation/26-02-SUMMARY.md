---
phase: 26-engine-foundation
plan: 02
subsystem: graph-runtime
tags: [asyncio, engine, timing, lifecycle, task-management]

# Dependency graph
requires:
  - phase: 26-01
    provides: "dep_cache parameter on Graph.arun() for external resource injection"
provides:
  - "GraphRegistry for managed graph execution with lifecycle states"
  - "TimingLM wrapper conforming to LM protocol with per-fill timing"
  - "GraphRun dataclass with RUNNING/DONE/FAILED/CANCELLED states"
  - "Bounded completed-runs archive (deque maxlen=20)"
  - "CortexShell.engine for graph execution from PY and GRAPH modes"
affects: [27-graph-commands, 28-input-gates, 29-observability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TimingLM decorator pattern: wrap LM protocol, record timing, delegate to inner"
    - "Engine submit pattern: registry.submit(graph, tm, lm=lm) returns GraphRun immediately"
    - "dep_cache + lm dual injection: TimingLM passed as both lm and dep_cache[LM_KEY]"

key-files:
  created:
    - bae/repl/engine.py
    - tests/repl/test_engine.py
  modified:
    - bae/repl/shell.py

key-decisions:
  - "TimingLM passed as both lm= and dep_cache[LM_KEY] to arun() -- graph runtime uses lm directly for routing/fill calls, dep_cache only affects resolver"
  - "TimingLM records timing on fill and make (node-producing calls), not on choose_type or decide (routing decisions)"
  - "GRAPH mode dispatch calls await _run_graph() directly instead of wrapping in tm.submit() -- engine handles its own task submission"

patterns-established:
  - "Engine submit: registry.submit(graph, tm, lm=lm, **kwargs) -> GraphRun"
  - "TimingLM wrapping: TimingLM(inner_lm, run) conforms to LM protocol"

# Metrics
duration: 5min
completed: 2026-02-15
---

# Phase 26 Plan 02: Cortex Engine Summary

**GraphRegistry with TimingLM wrapper for managed graph execution, lifecycle tracking, and per-node timing inside cortex**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T14:29:45Z
- **Completed:** 2026-02-15T14:35:33Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- GraphRegistry tracks graph runs by ID with RUNNING/DONE/FAILED/CANCELLED lifecycle states
- TimingLM wraps any LM backend, recording per-fill/make timing in NodeTiming dataclass, conforms to LM protocol via runtime_checkable
- Completed runs archived in bounded deque (maxlen=20), active runs queryable
- CortexShell integrates engine: GRAPH mode submits via engine, graph tasks appear in Ctrl-C task menu
- 16 tests covering all state transitions, timing recording, protocol conformance, bounded deque

## Task Commits

Each task was committed atomically:

1. **Task 1: Create engine module with GraphRegistry, TimingLM, and lifecycle tracking** - `b1e83ea` (feat)
2. **Task 2: Integrate engine into CortexShell** - `8c4d484` (feat)

## Files Created/Modified
- `bae/repl/engine.py` - GraphState enum, NodeTiming dataclass, GraphRun dataclass, TimingLM wrapper, GraphRegistry class
- `tests/repl/test_engine.py` - 16 tests: states, timing, protocol conformance, registry lifecycle, archiving, bounded deque
- `bae/repl/shell.py` - Added engine import, self.engine init, namespace exposure, _run_graph via engine, removed dispatch double-wrap

## Decisions Made
- TimingLM must be passed as both `lm=timing_lm` and `dep_cache={LM_KEY: timing_lm}` to `arun()` because the graph runtime uses the `lm` parameter directly for routing/fill calls, while dep_cache only affects the resolver cache for dep-annotated fields
- Timing recorded on `fill` and `make` (node-producing calls); `choose_type` and `decide` are routing decisions that don't produce timing events
- GRAPH mode dispatch changed from `tm.submit(_run_graph(...))` to `await _run_graph(text)` because `_run_graph` now internally submits via engine, avoiding double-wrapping

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TimingLM injection: pass as both lm and dep_cache**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Plan specified passing TimingLM only via dep_cache, but graph.arun() uses its local `lm` variable directly for fill/choose_type calls. Without passing `lm=timing_lm`, arun defaulted to ClaudeCLIBackend
- **Fix:** Pass `lm=timing_lm` in addition to `dep_cache={LM_KEY: timing_lm}` to arun()
- **Files modified:** bae/repl/engine.py
- **Verification:** test_run_completes_to_done passes with MockLM
- **Committed in:** b1e83ea (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for correctness. Without it, engine would always try to use ClaudeCLIBackend regardless of provided LM.

## Issues Encountered
- Forward reference resolution for Node subclasses defined inside test methods -- Python 3.14 cannot resolve `def __call__(self) -> SlowEnd: ...` when SlowEnd is a local class. Solved by using module-level MockLM variants (SlowLM, FailingLM) instead of per-test inner classes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- GraphRegistry ready for Phase 27 (graph commands) to build CLI commands on top of
- TimingLM ready for Phase 29 (observability) to surface per-node timing data
- Engine submit pattern ready for Phase 28 (input gates) to inject CortexPrompt via dep_cache
- All 592 tests passing, zero regressions

## Self-Check: PASSED

- FOUND: bae/repl/engine.py
- FOUND: tests/repl/test_engine.py
- FOUND: bae/repl/shell.py
- FOUND: .planning/phases/26-engine-foundation/26-02-SUMMARY.md
- FOUND: commit b1e83ea
- FOUND: commit 8c4d484

---
*Phase: 26-engine-foundation*
*Completed: 2026-02-15*
