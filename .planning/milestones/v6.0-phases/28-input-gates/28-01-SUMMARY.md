---
phase: 28-input-gates
plan: 01
subsystem: markers, resolver, engine
tags: [gate, asyncio-future, input-gate, annotation-marker, graph-state]

# Dependency graph
requires:
  - phase: 26-engine-foundation
    provides: GraphRegistry, GraphState, GraphRun, TimingLM
  - phase: 27-graph-mode
    provides: Graph mode commands, engine lifecycle
provides:
  - Gate marker in bae/markers.py (fourth field marker)
  - Gate classification in classify_fields ("gate" category)
  - LM plain model exclusion for gate fields
  - InputGate dataclass with Future and schema_display
  - GraphState.WAITING for suspended graphs
  - Gate registry on GraphRegistry (create/resolve/query/cancel)
affects: [28-02-PLAN, 28-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Gate marker follows Dep/Recall/Effect frozen dataclass pattern"
    - "InputGate wraps asyncio.Future with schema metadata"
    - "Gate registry on GraphRegistry with monotonic counter IDs"

key-files:
  created: []
  modified:
    - bae/markers.py
    - bae/resolver.py
    - bae/__init__.py
    - bae/repl/engine.py
    - tests/test_resolver.py
    - tests/repl/test_engine.py

key-decisions:
  - "Gate marker is frozen dataclass with description field, matching Dep/Recall/Effect pattern"
  - "Gate fields classified as 'gate' -- automatically excluded from LM plain model by existing equality check"
  - "InputGate uses asyncio.get_event_loop().create_future() as default_factory"
  - "Gate IDs use run_id.counter format (e.g. g1.0) with monotonic counter"
  - "cancel_gates called in both _execute and _wrap_coro CancelledError handlers"

patterns-established:
  - "Gate: fourth field annotation marker alongside Dep, Recall, Effect"
  - "InputGate: runtime Future wrapper created by engine, not by marker"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 28 Plan 01: Gate Marker and InputGate Infrastructure Summary

**Gate annotation marker with resolver classification, LM exclusion, InputGate Future wrapper, WAITING state, and gate registry lifecycle on GraphRegistry**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T22:47:09Z
- **Completed:** 2026-02-15T22:50:38Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Gate marker integrated into bae's annotation system as fourth field marker
- Resolver classifies gate fields and excludes them from LM filling and trace recall
- InputGate dataclass wraps asyncio.Future with schema metadata for human input prompts
- GraphState.WAITING added for graphs suspended at input gates
- Full gate lifecycle on GraphRegistry: create, resolve, query, filter by run, cancel with cleanup

## Task Commits

Each task was committed atomically:

1. **Task 1: Gate marker with resolver and LM integration** - `8ddc227` (feat)
2. **Task 2: InputGate dataclass with WAITING state and gate registry** - `676fbae` (feat)

## Files Created/Modified
- `bae/markers.py` - Added Gate frozen dataclass with description field
- `bae/resolver.py` - Gate classification in classify_fields, skip in recall_from_trace
- `bae/__init__.py` - Gate export added to public API
- `bae/repl/engine.py` - InputGate, WAITING state, gate registry methods, cancel on CancelledError
- `tests/test_resolver.py` - 4 tests for gate classification, plain model exclusion, recall skip, coexistence
- `tests/repl/test_engine.py` - 9 tests for gate creation, resolution, counting, filtering, cancel, display, WAITING state

## Decisions Made
- Gate marker follows exact Dep/Recall/Effect frozen dataclass pattern -- description is the only field
- classify_fields returns "gate" (not reusing "dep") so gate fields have distinct identity
- LM exclusion required zero code changes in lm.py -- existing `== "plain"` check naturally excludes "gate"
- recall_from_trace skips gate fields alongside dep/recall (infrastructure, not LLM-filled)
- InputGate uses default_factory with get_event_loop() -- tests made async for Python 3.14 compat
- Gate IDs use `{run_id}.{counter}` format for unambiguous cross-run identification
- cancel_gates added to both _execute and _wrap_coro CancelledError paths for completeness

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Made schema_display tests async for Python 3.14 compatibility**
- **Found during:** Task 2 (test execution)
- **Issue:** Sync tests calling `asyncio.get_event_loop().create_future()` fail on Python 3.14 with "no current event loop in thread" since get_event_loop no longer auto-creates loops in non-async contexts
- **Fix:** Changed test_schema_display_with_description and test_schema_display_without_description from sync to async, letting pytest-asyncio provide the event loop. Removed explicit future= kwarg (default_factory handles it in async context).
- **Files modified:** tests/repl/test_engine.py
- **Verification:** All 36 engine tests pass
- **Committed in:** 676fbae (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test adaptation for Python 3.14 event loop policy. No scope change.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Gate marker and InputGate infrastructure ready for Plan 02 (engine interception of gate fields during resolve_fields)
- Plan 03 (shell integration) can use gate registry methods for the `input` command and toolbar badge
- classify_fields "gate" category ready for resolve_fields gate handling in Plan 02

---
*Phase: 28-input-gates*
*Completed: 2026-02-15*
