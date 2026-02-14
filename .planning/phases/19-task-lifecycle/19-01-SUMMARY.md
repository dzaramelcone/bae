---
phase: 19-task-lifecycle
plan: 01
subsystem: repl
tags: [prompt-toolkit, toolbar, widgets, style-tuples]

requires:
  - phase: 14-repl-core
    provides: CortexShell with bottom_toolbar, Mode enum
provides:
  - ToolbarConfig class with add/remove/render/widgets API
  - Built-in widget factories: make_mode_widget, make_tasks_widget, make_cwd_widget
  - ToolbarWidget type alias for widget callables
affects: [19-02, shell-integration, namespace-seeding]

tech-stack:
  added: []
  patterns: [widget-factory-closure, exception-safe-render]

key-files:
  created:
    - bae/repl/toolbar.py
    - tests/repl/test_toolbar.py
  modified: []

key-decisions:
  - "MODE_NAMES values used as-is (uppercase PY/NL/GRAPH/BASH) -- no title-casing in widget"
  - "Widget factories use closures over shell object -- deferred import of MODE_NAMES avoids circular imports"

patterns-established:
  - "Widget factory: function takes shell, returns zero-arg callable producing style tuples"
  - "Exception-safe render: each widget wrapped in try/except, errors shown as [name:err]"

duration: 2min
completed: 2026-02-13
---

# Phase 19 Plan 01: ToolbarConfig Summary

**TDD ToolbarConfig class with named widget registry and three built-in widget factories for mode, task count, and cwd**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-14T02:58:06Z
- **Completed:** 2026-02-14T02:59:49Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- ToolbarConfig class with add/remove/render/widgets/repr API, exception-safe rendering
- Three built-in widget factories: mode name, task count (singular/plural, hidden when zero), cwd (home-relative)
- 15 unit tests covering all ToolbarConfig methods and all three widget factories

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Write failing tests for ToolbarConfig** - `6b30a0b` (test)
2. **Task 2: GREEN -- Implement ToolbarConfig and built-in widgets** - `b111f4d` (feat)

## Files Created/Modified
- `bae/repl/toolbar.py` - ToolbarConfig class + ToolbarWidget type alias + make_mode_widget/make_tasks_widget/make_cwd_widget factories
- `tests/repl/test_toolbar.py` - 15 unit tests: 10 for ToolbarConfig, 5 for built-in widgets

## Decisions Made
- MODE_NAMES values used as-is (uppercase PY/NL/GRAPH/BASH) -- plan suggested "Py" but MODE_NAMES maps to "PY"
- Widget factories use closures over shell object, with deferred MODE_NAMES import to avoid circular imports
- make_cwd_widget takes no arguments (os.getcwd is global state), unlike mode/tasks which need shell reference

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected mode widget expected value**
- **Found during:** Task 1 (test writing)
- **Issue:** Plan specified `" Py "` as expected mode widget output, but MODE_NAMES[Mode.PY] is `"PY"` not `"Py"`
- **Fix:** Used `" PY "` in test expectation to match actual MODE_NAMES data
- **Files modified:** tests/repl/test_toolbar.py
- **Verification:** Test passes with actual MODE_NAMES values
- **Committed in:** 6b30a0b (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Trivial correction aligning test expectation with actual data source. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ToolbarConfig ready for shell integration (plan 02 will wire into CortexShell)
- Widget protocol established: any callable returning list[tuple[str, str]] works
- Shell integration needs: replace static _toolbar() with toolbar.render(), seed namespace with toolbar object

---
*Phase: 19-task-lifecycle*
*Completed: 2026-02-13*

## Self-Check: PASSED

- [x] bae/repl/toolbar.py exists
- [x] tests/repl/test_toolbar.py exists
- [x] 19-01-SUMMARY.md exists
- [x] Commit 6b30a0b exists (test RED)
- [x] Commit b111f4d exists (feat GREEN)
- [x] All 15 tests pass
