---
phase: quick
plan: 1
subsystem: repl
tags: [mode-removal, cleanup, graph-mode]

requires: []
provides:
  - "Clean Mode enum with 3 modes (NL, PY, BASH)"
  - "Shell dispatch without GRAPH branch"
affects: []

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - bae/repl/modes.py
    - bae/repl/shell.py
    - tests/repl/test_namespace_integration.py
    - tests/repl/test_task_lifecycle.py
  deleted:
    - bae/repl/graph_commands.py
    - tests/repl/test_graph_commands.py

key-decisions:
  - "Inlined notify callback in shell.py rather than importing from deleted graph_commands.py"
  - "Kept _graph_ctx auto-registration for programmatic graph execution in REPL"
  - "Gate routing condition changed from != Mode.NL to in (Mode.PY, Mode.BASH)"

duration: 2min
completed: 2026-02-16
---

# Quick Task 1: Remove GRAPH Mode Summary

**Removed GRAPH mode from Mode enum, shell dispatch, mode cycle, and all associated commands and tests**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-16T01:53:35Z
- **Completed:** 2026-02-16T01:55:31Z
- **Tasks:** 2
- **Files modified:** 4
- **Files deleted:** 2

## Accomplishments
- Removed Mode.GRAPH from enum, colors, names, and cycle (3 modes remain: NL, PY, BASH)
- Deleted graph_commands.py (336 lines) and test_graph_commands.py (643 lines)
- Preserved _graph_ctx auto-registration for programmatic graph execution
- All 641 tests pass with clean output

## Task Commits

1. **Task 1: Remove GRAPH mode from modes.py and shell.py** - `24a08d2` (feat)
2. **Task 2: Remove GRAPH mode tests, fix remaining references** - `44489e8` (test)

## Files Created/Modified
- `bae/repl/modes.py` - Mode enum without GRAPH, 3-mode cycle
- `bae/repl/shell.py` - No GRAPH dispatch branch, inlined notify, no shush_gates
- `bae/repl/graph_commands.py` - DELETED
- `tests/repl/test_graph_commands.py` - DELETED
- `tests/repl/test_namespace_integration.py` - Updated GRAPH mode comments to graph engine
- `tests/repl/test_task_lifecycle.py` - Updated docstring removing GRAPH reference

## Decisions Made
- Inlined the notify callback directly in shell.py __init__ instead of importing _make_notify from the deleted graph_commands.py. The inline version omits shush_gates filtering since that feature is removed with GRAPH mode.
- Kept _graph_ctx.set() in shell __init__ because graph.py reads it for auto-registration when graphs are called programmatically inside the REPL.
- Changed gate routing condition from `self.mode != Mode.NL` to `self.mode in (Mode.PY, Mode.BASH)` for explicit enumeration now that GRAPH is gone.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

---
*Quick task: 1*
*Completed: 2026-02-16*
