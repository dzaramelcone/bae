---
phase: 07-integration
plan: 03
subsystem: testing
tags: [pytest, mock-lm, v2-api, choose_type, fill, incant-removal]

# Dependency graph
requires:
  - phase: 07-integration-02
    provides: v2 Graph.run() with choose_type/fill routing
provides:
  - All test files migrated to v2 MockLM (choose_type/fill)
  - incant removed from pyproject.toml dependencies
  - 300 tests passing with 0 failures
affects: [07-integration-04, 08-cleanup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MockLM implements choose_type/fill for ellipsis-body nodes, keeps make/decide stubs for custom __call__ nodes"
    - "v2 test assertions check choose_type_calls and fill_calls instead of decide_calls and make_calls"

key-files:
  created: []
  modified:
    - tests/test_graph.py
    - tests/test_auto_routing.py
    - tests/test_integration_dspy.py
    - tests/test_integration.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "MockLMs keep v1 make/decide as stubs for custom __call__ nodes that invoke them directly"
  - "v1 incant tests (TestBindDepValueFlow, TestExternalDepInjection) deleted entirely, not ported"
  - "test_integration.py max_steps -> max_iters as deviation fix"

patterns-established:
  - "v2 MockLM pattern: choose_type returns type from sequence, fill returns node from sequence (index advances on fill only)"

# Metrics
duration: 5min
completed: 2026-02-08
---

# Phase 7 Plan 03: Test Migration to v2 Summary

**Migrated 13 failing v1 tests to v2 MockLM pattern (choose_type/fill), removed incant dependency, 300 tests green**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-02-08T03:05:57Z
- **Completed:** 2026-02-08T03:12:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- All 13 previously-failing tests now pass with v2 MockLM pattern
- incant fully removed from dependencies (pyproject.toml + uv.lock)
- v1 incant-specific test classes deleted (Bind/Dep __call__ param injection no longer exists)
- Full test suite: 300 passed, 5 skipped, 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Update test_graph.py and test_auto_routing.py for v2** - `778d44e` (fix)
2. **Task 2: Update test_integration_dspy.py + remove incant from pyproject.toml** - `c62ffd8` (fix)

## Files Created/Modified
- `tests/test_graph.py` - MockLM gets choose_type/fill stubs, test_run_max_steps renamed to test_run_max_iters with BaeError
- `tests/test_auto_routing.py` - MockLM rewritten with v2 API, assertions check choose_type_calls/fill_calls
- `tests/test_integration_dspy.py` - Deleted v1 incant classes/tests, MockLM rewritten, assertions migrated
- `tests/test_integration.py` - max_steps -> max_iters (deviation fix)
- `pyproject.toml` - Removed incant>=1.0 from dependencies
- `uv.lock` - Updated to reflect incant removal

## Decisions Made
- **MockLMs keep v1 make/decide as stubs:** Custom __call__ nodes (e.g., StartCustom) still call `lm.make()` and `lm.decide()` internally from their bodies. The v2 loop invokes these as `current(lm)` for custom strategy, so the mock must implement both APIs.
- **v1 incant tests deleted, not ported:** TestBindDepValueFlow and TestExternalDepInjection tested incant-based __call__ parameter injection (Dep as __call__ param). v2 uses Dep as node fields resolved via resolve_fields(). These are fundamentally different mechanisms; test_dep_injection.py (from 07-02) already covers v2 dep resolution.
- **Responses dict MockLM pattern for test_integration_dspy.py:** The responses dict pattern (type → node mapping) works naturally with v2 choose_type (pick type from dict keys) and fill (return dict value for type).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed max_steps in test_integration.py**
- **Found during:** Task 2 (full test suite verification)
- **Issue:** test_integration.py::TestClaudeCLIBackend used `max_steps=` kwarg which no longer exists in v2 Graph.run()
- **Fix:** Changed all `max_steps` to `max_iters` in test_integration.py
- **Files modified:** tests/test_integration.py
- **Verification:** Full test suite passes
- **Committed in:** c62ffd8 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix; test_integration.py wasn't in the plan's file list but was failing for the same reason (max_steps removed in v2). No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 300 tests pass with v2 patterns
- incant fully removed from project
- compiler.py CompiledGraph.run() still passes **deps to graph.run() — Plan 04 will address this
- Ready for Plan 04 (compiler/CLI cleanup)

---
*Phase: 07-integration*
*Completed: 2026-02-08*
