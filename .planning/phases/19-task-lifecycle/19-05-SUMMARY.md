---
phase: 19-task-lifecycle
plan: 05
subsystem: repl
tags: [asyncio, task-manager, task-menu, toolbar, process-groups, ctrl-c, pagination]

requires:
  - phase: 19-task-lifecycle
    plan: 04
    provides: TaskManager class with submit/revoke/revoke_all/active/shutdown API
provides:
  - TaskManager wired into CortexShell as shell.tm
  - Inline task menu in toolbar (Ctrl-C opens, digit cancels, Ctrl-C kills all, Esc dismisses)
  - Left/Right pagination at 5 tasks per page
  - PY async expressions tracked via TaskManager
  - Process groups (start_new_session=True) on ai.py and bash.py subprocesses
  - tm.register_process() called from AI and dispatch_bash
affects: [phase-19-complete, uat-retest]

tech-stack:
  added: []
  patterns: [inline-task-menu-via-toolbar-flag, coroutine-return-for-async-tracking, prompt-toolkit-condition-filtered-keybindings]

key-files:
  created: []
  modified:
    - bae/repl/shell.py
    - bae/repl/ai.py
    - bae/repl/bash.py
    - bae/repl/exec.py
    - bae/repl/toolbar.py
    - tests/repl/test_task_lifecycle.py
    - tests/repl/test_exec.py
    - tests/repl/test_toolbar.py

key-decisions:
  - "Inline task menu replaces checkboxlist_dialog -- simpler UX, no popup, stays in toolbar"
  - "First Ctrl-C opens menu, second kills all -- no timing threshold needed"
  - "async_exec returns unawaited coroutine for async code -- caller tracks via TaskManager"
  - "prompt_toolkit Condition filter gates digit/arrow/esc bindings to task menu mode only"
  - "PY async expressions tracked as mode='py' tasks -- visible in toolbar and cancellable"

patterns-established:
  - "Toolbar mode switching: _task_menu flag toggles between render_task_menu() and toolbar.render()"
  - "Coroutine detection: asyncio.iscoroutine(result) after async_exec to distinguish sync/async PY"
  - "Conditional key bindings: Condition(lambda: shell._task_menu) as filter parameter"

duration: 7min
completed: 2026-02-14
---

# Phase 19 Plan 05: Shell + Toolbar Integration Summary

**Inline task menu in toolbar (Ctrl-C/digit/Esc/arrows), PY async tracking via TaskManager, process group kill via start_new_session=True on all subprocesses**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-14T11:27:31Z
- **Completed:** 2026-02-14T11:35:14Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- shell.tm (TaskManager) replaces shell.tasks (bare set) throughout CortexShell
- Ctrl-C opens numbered task list in toolbar; digit keys (1-5) cancel by position; Ctrl-C again kills all; Esc dismisses
- Left/Right arrow keys paginate when more than 5 tasks running
- PY async expressions (await ...) detected via asyncio.iscoroutine() and tracked as cancellable tasks
- start_new_session=True + tm.register_process() on AI and bash subprocesses
- Removed _show_kill_menu, checkboxlist_dialog, DOUBLE_PRESS_THRESHOLD, and double-press timing logic
- 205 repl tests pass with zero regressions (26 lifecycle + 20 task_manager + 159 existing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Process groups + TaskManager registration** - `2165e69` (feat)
2. **Task 2: Shell + toolbar integration** - `73b99f9` (feat)

## Files Created/Modified
- `bae/repl/shell.py` - TaskManager wiring, task menu state, key bindings, _dispatch PY async tracking
- `bae/repl/ai.py` - start_new_session=True, tm parameter, register_process()
- `bae/repl/bash.py` - start_new_session=True, tm parameter, register_process()
- `bae/repl/exec.py` - Returns unawaited coroutine for async expressions
- `bae/repl/toolbar.py` - render_task_menu(), TASKS_PER_PAGE, updated make_tasks_widget
- `tests/repl/test_task_lifecycle.py` - 26 tests: submit, interrupt, task menu, dispatch, subprocess cleanup, toolbar
- `tests/repl/test_exec.py` - Updated test_await_expr_returns_coroutine for new async_exec behavior
- `tests/repl/test_toolbar.py` - Updated make_tasks_widget tests for shell.tm.active() API

## Decisions Made
- Replaced checkboxlist_dialog popup with inline toolbar task menu -- simpler, no modal dialog, keyboard-driven
- First Ctrl-C opens menu, second kills all -- eliminates timing-based double-press detection entirely
- async_exec returns raw coroutine for async code so caller can track it via TaskManager (not await inline)
- prompt_toolkit Condition filter restricts digit/arrow/esc bindings to task menu mode only
- PY async expressions tracked as mode="py" tasks -- visible in toolbar count and cancellable via menu

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed _get_handler test helper matching multi-key bindings**
- **Found during:** Task 2 (test writing)
- **Issue:** _get_handler("escape") matched insert_newline binding (keys: ["escape", "c-m"]) instead of dismiss_task_menu (keys: ["escape"]) because it checked if any key in the sequence matched
- **Fix:** Updated _get_handler to match bindings where the entire key sequence is exactly [key]
- **Files modified:** tests/repl/test_task_lifecycle.py
- **Committed in:** 73b99f9 (Task 2 commit)

**2. [Rule 1 - Bug] Updated test_await_expr for new coroutine-return behavior**
- **Found during:** Task 2 (regression test run)
- **Issue:** test_exec.py::test_await_expr_returns_value expected awaited value but async_exec now returns unawaited coroutine
- **Fix:** Test now asserts coroutine is returned, awaits it, checks namespace["_"] for result
- **Files modified:** tests/repl/test_exec.py
- **Committed in:** 73b99f9 (Task 2 commit)

**3. [Rule 1 - Bug] Updated test_toolbar tasks widget tests for TaskManager API**
- **Found during:** Task 2 (regression test run)
- **Issue:** test_toolbar.py used shell.tasks (bare set) which no longer exists; make_tasks_widget now uses shell.tm.active()
- **Fix:** Tests mock shell.tm.active() return value instead of shell.tasks
- **Files modified:** tests/repl/test_toolbar.py
- **Committed in:** 73b99f9 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (3 bugs -- test updates for API changes)
**Impact on plan:** All fixes necessary for test correctness after API migration. No scope change.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 19 Task Lifecycle is complete -- all 5 plans executed
- Ready for UAT retest of the 3 issues that prompted gap closure (19-04 + 19-05)
- TaskManager provides full lifecycle tracking: submit, active, revoke, revoke_all, shutdown
- Inline task menu replaces the checkboxlist_dialog with simpler keyboard-driven UX

---
*Phase: 19-task-lifecycle*
*Completed: 2026-02-14*

## Self-Check: PASSED

- [x] bae/repl/shell.py exists
- [x] bae/repl/ai.py exists
- [x] bae/repl/bash.py exists
- [x] bae/repl/exec.py exists
- [x] bae/repl/toolbar.py exists
- [x] tests/repl/test_task_lifecycle.py exists
- [x] tests/repl/test_exec.py exists
- [x] tests/repl/test_toolbar.py exists
- [x] Commit 2165e69 exists (feat: process groups + TaskManager registration)
- [x] Commit 73b99f9 exists (feat: shell + toolbar integration)
- [x] All 205 repl tests pass (26 lifecycle + 20 task_manager + 159 existing)
