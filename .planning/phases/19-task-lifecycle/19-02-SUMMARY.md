---
phase: 19-task-lifecycle
plan: 02
subsystem: repl
tags: [prompt-toolkit, asyncio, task-tracking, interrupt-handler, kill-menu, toolbar, subprocess-cleanup]

requires:
  - phase: 19-task-lifecycle
    plan: 01
    provides: ToolbarConfig class with widget factories
  - phase: 18-ai-agent
    provides: AI class with subprocess execution, shell NL wiring
  - phase: 14-repl-core
    provides: CortexShell with _build_key_bindings, dispatch_bash, Mode enum
provides:
  - Task tracking via _track_task() with auto-cleanup done callbacks
  - Ctrl-C interrupt handler: exit (idle), kill menu (single), kill all (double)
  - _dispatch() method replacing inline mode routing in run()
  - CancelledError subprocess cleanup in AI.__call__ and dispatch_bash
  - ToolbarConfig integration with built-in mode/tasks/cwd widgets
  - toolbar object in namespace for user customization from PY mode
affects: [repl-ux, future-task-management]

tech-stack:
  added: []
  patterns: [tracked-task-set, done-callback-cleanup, double-press-threshold, coroutine-kill-menu]

key-files:
  created:
    - tests/repl/test_task_lifecycle.py
  modified:
    - bae/repl/shell.py
    - bae/repl/ai.py
    - bae/repl/bash.py

key-decisions:
  - "PY mode NOT tracked (synchronous-ish exec, can't cancel tight loops) -- only NL/GRAPH/BASH tracked"
  - "_dispatch() extracted from run() to isolate mode routing from REPL loop"
  - "checkboxlist_dialog imported locally in _show_kill_menu to avoid module-level prompt_toolkit shortcut import"
  - "time.monotonic for double-press detection (not time.time) -- immune to clock adjustments"

patterns-established:
  - "Task tracking: _track_task wraps coroutine, adds to set, done_callback discards -- zero manual cleanup"
  - "Interrupt routing: key binding checks shell.tasks emptiness to decide exit vs menu vs kill-all"
  - "Subprocess cleanup: except CancelledError -> kill() -> wait() -> raise -- prevents orphan processes"

duration: 4min
completed: 2026-02-13
---

# Phase 19 Plan 02: Task Lifecycle Wiring Summary

**Task tracking with Ctrl-C kill menu, double-press kill-all, subprocess cleanup, and ToolbarConfig integration into CortexShell**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-14T03:01:48Z
- **Completed:** 2026-02-14T03:06:03Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- _track_task() method with done_callback auto-cleanup for NL, GRAPH, and BASH modes
- Ctrl-C interrupt handler: exits REPL when idle (REPL-12 preserved), opens kill menu on single press with tasks, cancels all on double press within 0.4s
- CancelledError subprocess cleanup in AI.__call__ and dispatch_bash -- kills process, awaits wait(), re-raises
- ToolbarConfig wired into shell with mode/tasks/cwd built-in widgets, refresh_interval=1.0, toolbar in namespace

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire task tracking, interrupt handler, toolbar, and subprocess cleanup** - `8dc8399` (feat)
2. **Task 2: Unit tests for task lifecycle and interrupt routing** - `ab83e92` (test)

## Files Created/Modified
- `bae/repl/shell.py` - _track_task, _dispatch, Ctrl-C handler with kill menu, ToolbarConfig integration
- `bae/repl/ai.py` - CancelledError subprocess cleanup in AI.__call__
- `bae/repl/bash.py` - CancelledError subprocess cleanup in dispatch_bash
- `tests/repl/test_task_lifecycle.py` - 13 tests: track task, interrupt routing, subprocess cleanup, toolbar, kill menu

## Decisions Made
- PY mode not tracked -- synchronous exec can't be cancelled, only NL/GRAPH/BASH get tracked tasks
- Extracted _dispatch() from run() to keep REPL loop clean and mode routing testable
- checkboxlist_dialog imported locally in _show_kill_menu (not at module level) to avoid circular import risk
- time.monotonic for double-press detection -- monotonic clock immune to system clock adjustments

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 19 complete: ToolbarConfig TDD'd (plan 01) and fully wired into CortexShell (plan 02)
- REPL-06 (configurable toolbar), REPL-10 (kill menu), REPL-11 (double Ctrl-C kill all) all implemented
- Task lifecycle foundation ready for future enhancements (task priorities, named groups, etc.)

---
*Phase: 19-task-lifecycle*
*Completed: 2026-02-13*

## Self-Check: PASSED

- [x] bae/repl/shell.py exists
- [x] bae/repl/ai.py exists
- [x] bae/repl/bash.py exists
- [x] tests/repl/test_task_lifecycle.py exists
- [x] 19-02-SUMMARY.md exists
- [x] Commit 8dc8399 exists (feat: task tracking + interrupt + toolbar + subprocess)
- [x] Commit ab83e92 exists (test: task lifecycle tests)
- [x] All 172 repl tests pass (159 existing + 13 new)
