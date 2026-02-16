---
phase: 27-graph-mode
plan: 04
subsystem: graph-runtime
tags: [timeout, trace, error-handling, flattened-params, pydantic]

# Dependency graph
requires:
  - phase: 27-01
    provides: "graph() factory and Graph.arun()"
  - phase: 27-02
    provides: "GRAPH mode commands (inspect, trace)"
  - phase: 27-03
    provides: "_param_types on graph() wrapper"
provides:
  - "120s LM timeout for complex graphs"
  - "Partial trace on all arun() exceptions"
  - "run.result populated on engine failure for inspect/trace"
  - "Flattened graph() callable signatures (no BaseModel construction needed)"
affects: [27-05-PLAN, ootd-example, graph-commands]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Outer try/except for trace attachment on unhandled exceptions"
    - "BaseModel field flattening with _composites closure dict"
    - "Lazy GraphResult import in except blocks"

key-files:
  created: []
  modified:
    - "bae/lm.py"
    - "bae/graph.py"
    - "bae/repl/engine.py"
    - "tests/test_graph.py"
    - "tests/repl/test_engine.py"
    - "tests/repl/test_graph_commands.py"
    - "examples/ootd.py"

key-decisions:
  - "120s timeout generous enough for 6+ node graphs while still protecting against hangs"
  - "Outer try/except around entire while loop (not inside) captures trace across all iterations"
  - "hasattr guard prevents overwriting trace already set by BaeError/DepError"
  - "_composites dict captured by closure for zero-overhead BaseModel reconstruction at call time"
  - "_param_types removed -- flattened params eliminate need for type injection"

patterns-established:
  - "Outer exception wrapper: try/except around arun loop attaches .trace to any unhandled exception"
  - "Flattened callable signatures: graph() flattens BaseModel fields into simple kwargs"

# Metrics
duration: 5min
completed: 2026-02-15
---

# Phase 27 Plan 04: Gap Closure Summary

**120s LM timeout, partial trace on all graph exceptions, and flattened BaseModel params in graph() callable**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T21:27:07Z
- **Completed:** 2026-02-15T21:33:02Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- ClaudeCLIBackend timeout increased from 20s to 120s for reliable complex graph execution
- All exceptions from graph.arun() now carry .trace with partial execution history
- Engine _wrap_coro and _execute extract .trace from exceptions, populating run.result for inspect/trace
- graph() callable flattens BaseModel input fields: users pass `name="Dzara"` instead of `UserInfo(name="Dzara")`
- _param_types removed -- no longer needed with flat signatures

## Task Commits

Each task was committed atomically:

1. **Task 1: Increase LM timeout and attach partial trace** - `35096af` (feat)
2. **Task 2: Extract partial trace from failed coroutine in engine** - `10be0f0` (feat)
3. **Task 3: Flatten BaseModel params in graph() callable** - `4048ede` (feat)

## Files Created/Modified
- `bae/lm.py` - ClaudeCLIBackend timeout 20 -> 120s
- `bae/graph.py` - Outer try/except in arun(), flattened graph() factory with _composites
- `bae/repl/engine.py` - _wrap_coro and _execute extract .trace into run.result on failure
- `tests/test_graph.py` - Partial trace tests, flattened call tests, no _param_types test
- `tests/repl/test_engine.py` - Trace extraction tests for both submit_coro and submit paths
- `tests/repl/test_graph_commands.py` - test_run_flattened_params replaces test_run_injects_param_types
- `examples/ootd.py` - Updated __main__ to use flattened params

## Decisions Made
- 120s timeout: generous for single LM calls in complex graphs while still guarding against hangs
- Outer try/except goes around entire while loop, not inside, to capture full trace history
- hasattr(e, "trace") guard prevents overwriting trace already set by BaeError/DepError
- _composites closure dict for zero-overhead BaseModel reconstruction at call time
- _param_types removed entirely -- flattened signatures make type injection unnecessary

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed broken test_run_injects_param_types test**
- **Found during:** Task 3
- **Issue:** The Plan 03 test `test_run_injects_param_types` was already failing (injection code never wired into _cmd_run). With flattened params, the test is obsolete.
- **Fix:** Replaced with `test_run_flattened_params` that tests the new flat-param API. Also restored linter-removed TInput/TTypedStart node definitions and BaseModel import.
- **Files modified:** tests/repl/test_graph_commands.py
- **Verification:** All 25 graph_commands tests pass
- **Committed in:** 4048ede (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Auto-fix necessary for test correctness. The broken test was preexisting from incomplete Plan 03 wiring. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 05 (UAT update) can remove _param_types injection code from graph_commands.py (already gone, just the test reference)
- inspect/trace commands now work for failed runs without code changes (they already check run.result.trace)
- Full test suite: 641 passed, 5 skipped

---
*Phase: 27-graph-mode*
*Completed: 2026-02-15*
