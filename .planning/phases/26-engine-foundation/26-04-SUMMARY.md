---
phase: 26-engine-foundation
plan: 04
subsystem: repl
tags: [engine, graph-execution, error-handling, background-tasks]

# Dependency graph
requires:
  - phase: 26-02
    provides: "GraphRegistry, TimingLM, engine submit pipeline"
provides:
  - "GraphRun.error field for diagnosable failures"
  - "GRAPH mode error surfacing via [graph] channel done callbacks"
  - "Correct kwarg handling -- no spurious text= pass-through"
affects: [27-graph-mode, 28-input-gates]

# Tech tracking
tech-stack:
  added: []
  patterns: ["asyncio.Task done callbacks for background error surfacing"]

key-files:
  created: []
  modified:
    - bae/repl/engine.py
    - bae/repl/shell.py
    - tests/repl/test_engine.py

key-decisions:
  - "GRAPH mode submits with no extra kwargs -- Phase 27 adds run graph(field=val) syntax"
  - "Error surfacing via Task.add_done_callback reading run.error set before re-raise"

patterns-established:
  - "Done callback pattern: register callback on tm task to surface background results through channel"

# Metrics
duration: 1min
completed: 2026-02-15
---

# Phase 26 Plan 04: Graph Error Pipeline Summary

**GraphRun stores exceptions as error strings, GRAPH mode surfaces them via [graph] channel done callbacks, and _run_graph stops passing wrong kwargs to arun**

## Performance

- **Duration:** 1 min
- **Started:** 2026-02-15T15:27:50Z
- **Completed:** 2026-02-15T15:29:11Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- GraphRun.error captures "ExceptionType: message" on failure, empty string on success
- Removed root cause of all graph failures: `text=text` pass-through from _run_graph to engine.submit
- Background graph task completion/failure/cancellation now visible through [graph] channel via done callbacks

## Task Commits

Each task was committed atomically:

1. **Task 1: GraphRun error field and exception storage** - `62f9ccf` (feat)
2. **Task 2: GRAPH mode error surfacing and kwarg fix** - `3f21f52` (fix)

## Files Created/Modified
- `bae/repl/engine.py` - Added error field to GraphRun, capture exception in _execute except block
- `bae/repl/shell.py` - Removed text=text kwargs, added done callback for error surfacing
- `tests/repl/test_engine.py` - Two new tests: failed_run_stores_error, successful_run_has_no_error

## Decisions Made
- GRAPH mode submits with no extra kwargs. Graphs with required start-node fields will fail with a clear TypeError stored in run.error. Phase 27 adds `run graph(field=val)` syntax for field injection.
- Error surfacing uses asyncio.Task.add_done_callback reading run.error (set by engine._execute before re-raise). This avoids needing to restructure the TaskManager.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Graph error pipeline complete -- failures are now diagnosable
- Graphs with no required start-node fields run to completion with timing data
- Graphs requiring input fields fail with clear TypeError -- Phase 27 will add field injection syntax
- Ready to close UAT gap "Graphs run to completion with timing data captured"

## Self-Check: PASSED

All files exist, all commits verified, all key content present.

---
*Phase: 26-engine-foundation*
*Completed: 2026-02-15*
