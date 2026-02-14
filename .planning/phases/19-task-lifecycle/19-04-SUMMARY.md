---
phase: 19-task-lifecycle
plan: 04
subsystem: repl
tags: [asyncio, task-manager, process-groups, lifecycle-tracking, sigkill, sigterm]

requires:
  - phase: 19-task-lifecycle
    plan: 03
    provides: Fire-and-forget dispatch, CancelledError cleanup, _track_task
provides:
  - TaskManager class with submit/register_process/revoke/revoke_all/active/shutdown API
  - TrackedTask dataclass with state machine (RUNNING -> SUCCESS | FAILURE | REVOKED)
  - TaskState enum for lifecycle states
  - Process group kill via os.killpg() with SIGTERM/SIGKILL
affects: [shell-integration, task-menu, toolbar, process-cleanup]

tech-stack:
  added: []
  patterns: [task-registry-with-done-callback, process-group-killpg, auto-incrementing-task-id]

key-files:
  created:
    - bae/repl/tasks.py
    - tests/repl/test_task_manager.py
  modified: []

key-decisions:
  - "asyncio.subprocess.Process for type annotation (not subprocess.Process which does not exist)"
  - "Synchronous revoke() -- no SIGTERM->wait->SIGKILL escalation; graceful wait happens at shutdown() level via gather()"
  - "Process group kill via os.getpgid + os.killpg with ProcessLookupError/OSError fallback"

patterns-established:
  - "TaskManager registry: submit() returns TrackedTask, done callback transitions state automatically"
  - "register_process() from inside running task uses asyncio.current_task() lookup"
  - "revoke() kills process group first, then cancels asyncio.Task -- direct kill, not CancelledError indirection"

duration: 3min
completed: 2026-02-14
---

# Phase 19 Plan 04: TaskManager Summary

**TaskManager with lifecycle-tracked asyncio tasks, auto-incrementing IDs, process group kill via os.killpg(), and done-callback state machine (RUNNING/SUCCESS/FAILURE/REVOKED)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-14T11:22:21Z
- **Completed:** 2026-02-14T11:25:25Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- TaskManager class replaces bare `set[asyncio.Task]` with structured lifecycle tracking
- TrackedTask dataclass associates asyncio.Task with subprocess, state, name, mode, and auto-incrementing ID
- Done callback auto-transitions state: SUCCESS (normal), FAILURE (exception), REVOKED (CancelledError)
- Process group kill via os.killpg() with graceful (SIGTERM) and non-graceful (SIGKILL) modes
- register_process() allows running tasks to associate subprocesses after spawn
- 20 unit tests covering submit, register_process, revoke, revoke_all, active, shutdown

## Task Commits

Each task was committed atomically:

1. **RED: Failing tests for TaskManager** - `3de02ea` (test)
2. **GREEN: TaskManager implementation** - `468a01d` (feat)

_TDD plan: test -> implementation, no refactor needed (code already compact)_

## Files Created/Modified
- `bae/repl/tasks.py` - TaskManager class, TrackedTask dataclass, TaskState enum
- `tests/repl/test_task_manager.py` - 20 tests: submit lifecycle, process association, revoke/revoke_all, active(), shutdown

## Decisions Made
- Used `asyncio.subprocess.Process` for type annotation instead of plan's `subprocess.Process` (which doesn't exist in Python's subprocess module)
- Synchronous revoke() with no SIGTERM->wait->SIGKILL escalation as specified -- graceful wait happens at shutdown() level
- ProcessLookupError/OSError caught at both getpgid and killpg calls for dead-process safety

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed non-existent subprocess.Process import**
- **Found during:** RED (test writing)
- **Issue:** Plan specified `from subprocess import Process` but Python's subprocess module exports `Popen`, not `Process`. The actual type for async subprocesses is `asyncio.subprocess.Process`.
- **Fix:** Used `asyncio.subprocess.Process` for the type annotation in TrackedTask dataclass
- **Files modified:** bae/repl/tasks.py, tests/repl/test_task_manager.py
- **Verification:** Module imports correctly, all tests pass
- **Committed in:** 468a01d (GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Corrected type annotation to match actual Python API. No scope change.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- TaskManager ready for shell integration (plan 19-05)
- shell.tasks (bare set) can be replaced with shell.tm (TaskManager)
- ai.py and bash.py ready for tm parameter + start_new_session=True + register_process()
- Toolbar ready for task menu rendering via tm.active()

---
*Phase: 19-task-lifecycle*
*Completed: 2026-02-14*

## Self-Check: PASSED

- [x] bae/repl/tasks.py exists
- [x] tests/repl/test_task_manager.py exists
- [x] Commit 3de02ea exists (test: failing tests for TaskManager)
- [x] Commit 468a01d exists (feat: TaskManager implementation)
- [x] All 196 repl tests pass (20 task_manager + 176 existing)
