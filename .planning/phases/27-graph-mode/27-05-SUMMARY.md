---
phase: 27-graph-mode
plan: 05
subsystem: repl
tags: [rich, ansi, prompt-toolkit, views, graph-commands]

# Dependency graph
requires:
  - phase: 27-02
    provides: "GRAPH mode command dispatcher with Rich table/text rendering"
provides:
  - "ANSI metadata signaling on router.write for Rich-rendered content"
  - "ANSI-aware rendering in UserView, DebugView, AISelfView formatters"
affects: [repl-views, graph-commands]

# Tech tracking
tech-stack:
  added: []
  patterns: ["metadata type=ansi signals formatters to use prompt_toolkit ANSI() wrapper"]

key-files:
  created: []
  modified:
    - bae/repl/graph_commands.py
    - bae/repl/views.py
    - tests/repl/test_graph_commands.py

key-decisions:
  - "ANSI metadata on router.write rather than direct print -- preserves channel visibility and store recording"
  - "Type injection removed from _cmd_run -- graph callables handle param flattening directly"

patterns-established:
  - "metadata type=ansi: content containing ANSI escape codes must signal formatters via metadata to avoid raw escape rendering"

# Metrics
duration: 2min
completed: 2026-02-15
---

# Phase 27 Plan 05: ANSI Rendering Fix Summary

**ANSI metadata signaling on graph commands with ANSI-aware rendering in all three view formatters**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-15T21:27:15Z
- **Completed:** 2026-02-15T21:30:09Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Rich tables from `list` and Rich text from `inspect` now display as formatted output instead of raw escape codes
- All three view formatters (UserView, DebugView, AISelfView) detect ANSI metadata and wrap content with prompt_toolkit ANSI()
- Removed obsolete type injection from _cmd_run (graph callables handle param flattening)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ANSI metadata to router.write calls and remove type injection** - `b7cd52b` (feat)
2. **Task 2: Handle ANSI metadata in all three view formatters** - `9adbaee` (feat)

## Files Created/Modified
- `bae/repl/graph_commands.py` - Added metadata={"type": "ansi"} to _cmd_list and _cmd_inspect; removed _param_types injection block from _cmd_run
- `bae/repl/views.py` - Added ANSI early-return paths in UserView.render, DebugView.render, and AISelfView.render
- `tests/repl/test_graph_commands.py` - Removed type injection test/nodes; added ANSI metadata assertion tests for list and inspect

## Decisions Made
- ANSI metadata on router.write rather than direct print -- preserves channel visibility toggles and store recording architecture
- Type injection removed from _cmd_run -- graph callables handle param flattening directly (was added in 27-03, now unnecessary)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing uncommitted test `TestArunPartialTrace` in `tests/test_graph.py` fails (part of a debug investigation, not related to this plan). All committed tests pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- GRAPH mode ANSI rendering complete -- Rich tables and text display correctly in all view modes
- Phase 27 gap closure fully addressed (param type injection + ls removal + ANSI rendering)

---
*Phase: 27-graph-mode*
*Completed: 2026-02-15*
