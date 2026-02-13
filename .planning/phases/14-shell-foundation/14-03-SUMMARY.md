---
phase: 14-shell-foundation
plan: 03
subsystem: repl
tags: [ast, async-exec, expression-capture, sentinel, tdd]

# Dependency graph
requires:
  - phase: 14-01
    provides: "async_exec function and CortexShell REPL skeleton"
provides:
  - "Sentinel-guarded expression capture in async_exec"
  - "Regression test suite for async_exec (7 tests)"
affects: [shell-uat, py-mode]

# Tech tracking
tech-stack:
  added: [pytest, pytest-asyncio]
  patterns: [sentinel-guarded-return, ast-rewrite-with-capture-flag]

key-files:
  created:
    - tests/repl/__init__.py
    - tests/repl/test_exec.py
  modified:
    - bae/repl/exec.py

key-decisions:
  - "Local boolean flag instead of namespace injection for expression-capture tracking"

patterns-established:
  - "Sentinel guard: only return captured value when AST rewrite actually occurred"

# Metrics
duration: 2min
completed: 2026-02-13
---

# Phase 14 Plan 03: Expression Capture Fix Summary

**Sentinel-guarded async_exec return prevents for-loop underscore from leaking as spurious output**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-13T21:11:25Z
- **Completed:** 2026-02-13T21:13:30Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Fixed UAT bug: `for _ in range(20): print(_)` no longer prints spurious `19` at the end
- Expression capture (`1 + 1` -> `2`) still works correctly
- 7 regression tests covering expressions, assignments, loops, await, and multiline cases

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Write failing tests** - `ab46eec` (test)
2. **Task 2: GREEN -- Fix async_exec** - `39555ce` (fix)

## Files Created/Modified
- `tests/repl/__init__.py` - Package init for repl test module
- `tests/repl/test_exec.py` - 7 pytest-asyncio tests for async_exec expression capture
- `bae/repl/exec.py` - Sentinel-guarded return: only returns `_` when last statement was an expression

## Decisions Made
- Used local `expr_captured` boolean flag instead of injecting `__expr_captured__` into the namespace. Simpler, no namespace pollution, same correctness -- the parse-time decision is known before execution so no need to communicate it through the AST.

## Deviations from Plan

None - plan executed exactly as written. The implementation is functionally identical to the plan's spec (sentinel guard preventing unconditional `namespace.get('_')`), using a simpler mechanism (local boolean vs namespace injection).

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 14 Shell Foundation is now complete (all 3 plans done)
- async_exec correctly handles expression capture with regression test coverage
- Ready for Phase 15 (Session Store) or subsequent phases

## Self-Check: PASSED

- [x] tests/repl/__init__.py exists
- [x] tests/repl/test_exec.py exists (63 lines)
- [x] bae/repl/exec.py exists with _EXPR_CAPTURED sentinel
- [x] Commit ab46eec (test) verified in git log
- [x] Commit 39555ce (fix) verified in git log
- [x] All 7 tests pass

---
*Phase: 14-shell-foundation*
*Completed: 2026-02-13*
