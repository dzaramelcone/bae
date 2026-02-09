---
phase: 11-async-core
plan: 02
subsystem: lm-backend
tags: [dspy, async, acall, asyncio, optimized-lm]

# Dependency graph
requires:
  - phase: none
    provides: DSPyBackend and OptimizedLM sync implementations
provides:
  - Async DSPyBackend with native dspy.Predict.acall()
  - Async OptimizedLM.make() using await _call_with_retry()
  - 30 passing async tests for both backends
affects: [11-03, 11-04, graph-runtime]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "predictor.acall(**inputs) for async DSPy calls"
    - "asyncio.sleep() for async retry delays"
    - "AsyncMock for mocking acall in tests"

key-files:
  created: []
  modified:
    - bae/dspy_backend.py
    - bae/optimized_lm.py
    - tests/test_dspy_backend.py
    - tests/test_optimized_lm.py

key-decisions:
  - "Used predictor.acall() instead of asyncio.to_thread(predictor()) for true async"
  - "Kept _get_predictor_for_target and get_stats sync (pure computation, no I/O)"

patterns-established:
  - "AsyncMock for acall: mock_predictor.acall = AsyncMock(return_value=...) pattern for testing async DSPy"
  - "patch.object with new_callable=AsyncMock for patching async methods on instances"

# Metrics
duration: 4min
completed: 2026-02-08
---

# Phase 11 Plan 02: DSPyBackend + OptimizedLM Async Summary

**DSPyBackend and OptimizedLM converted to native async using dspy.Predict.acall(), with asyncio.sleep retry and 30 passing tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-09T00:21:04Z
- **Completed:** 2026-02-09T00:25:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- DSPyBackend.make/decide/choose_type/fill/_call_with_retry are all async def
- All predictor() calls replaced with await predictor.acall()
- time.sleep(1) replaced with await asyncio.sleep(1) in retry logic
- OptimizedLM.make() converted to async with await self._call_with_retry()
- 30/30 tests pass with AsyncMock-based predictor mocking

## Task Commits

Each task was committed atomically:

1. **Task 1: Convert dspy_backend.py and optimized_lm.py to async** - `1b9eb1e` (feat)
2. **Task 2: Migrate test_dspy_backend.py and test_optimized_lm.py to async** - `080cbd4` (test)

## Files Created/Modified
- `bae/dspy_backend.py` - Async DSPyBackend with await predictor.acall() and asyncio.sleep retry
- `bae/optimized_lm.py` - Async OptimizedLM.make() with await self._call_with_retry()
- `tests/test_dspy_backend.py` - 15 async tests for DSPyBackend
- `tests/test_optimized_lm.py` - 15 tests (sync for pure computation, async for backend calls)

## Decisions Made
- Used `predictor.acall()` (DSPy's native async) rather than wrapping sync in asyncio.to_thread
- Pure computation methods (_get_predictor_for_target, get_stats, _build_inputs, _parse_output, _get_return_types) kept sync -- no I/O, no benefit from async

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed duplicate import json**
- **Found during:** Task 1
- **Issue:** dspy_backend.py had `import json` twice (lines 10 and 16)
- **Fix:** Removed the duplicate on line 16
- **Files modified:** bae/dspy_backend.py
- **Verification:** Module imports cleanly
- **Committed in:** 1b9eb1e (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Trivial cleanup, no scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three LM backends (ClaudeCLI, DSPy, OptimizedLM) now have async interfaces
- Ready for Plan 03 (PydanticAI backend async) or Plan 04 (graph runtime async)
- Uncommitted changes to test_fill_protocol.py and test_lm_protocol.py exist from Plan 01 work -- those need to be committed as part of Plan 01

---
*Phase: 11-async-core*
*Completed: 2026-02-08*
