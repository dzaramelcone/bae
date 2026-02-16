---
phase: 27-graph-mode
plan: 06
subsystem: repl
tags: [asyncio, subprocess, stdin, inspect, json, timing, graph-mode]

# Dependency graph
requires:
  - phase: 27-04
    provides: "TimingLM node_timings and partial trace support"
  - phase: 27-05
    provides: "ANSI rendering via router.write for graph commands"
provides:
  - "Subprocess stdin isolation preventing REPL input contention"
  - "Reformatted inspect command with inline timing and JSON field display"
affects: [28-input-gates, graph-mode]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "stdin=DEVNULL on subprocess exec to isolate background processes from terminal"
    - "Consumed-index timing lookup to match node_timings to trace by type name"

key-files:
  created: []
  modified:
    - bae/lm.py
    - bae/repl/graph_commands.py
    - tests/repl/test_graph_commands.py

key-decisions:
  - "Name-based timing lookup with consumed-index instead of positional index -- start node has no timing entry"

patterns-established:
  - "Timing-to-trace matching: group timings by node_type, consume in order for duplicate types"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 27 Plan 06: Gap Closure Summary

**Subprocess stdin isolation via DEVNULL and inspect reformatted with inline per-node timing and JSON terminal fields**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T22:00:20Z
- **Completed:** 2026-02-15T22:02:58Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Subprocess stdin no longer inherited by child processes -- REPL input stays responsive during background graph execution
- inspect command merges timing inline with trace nodes instead of a separate section
- Terminal node fields displayed as indented JSON (json.dumps) instead of raw dict repr

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix subprocess stdin inheritance blocking REPL input** - `4d25663` (fix)
2. **Task 2: Reformat inspect with inline timing and JSON fields** - `eb2f6ac` (feat)

## Files Created/Modified
- `bae/lm.py` - Added stdin=asyncio.subprocess.DEVNULL to create_subprocess_exec
- `bae/repl/graph_commands.py` - Rewrote _cmd_inspect with inline timing, JSON fields, import json
- `tests/repl/test_graph_commands.py` - Updated test_inspect_completed_run, added test_inspect_inline_timing

## Decisions Made
- Used name-based timing lookup with consumed-index instead of positional index matching. The start node is constructed from kwargs (not via fill/make), so it has no timing entry. Positional matching would misalign timings with trace nodes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed timing-to-trace index mismatch**
- **Found during:** Task 2 (Reformat inspect command)
- **Issue:** Plan specified index-based matching (`timings[i]` for `trace[i]`), but TimingLM only records fill/make calls. The start node is constructed from kwargs without fill, so `node_timings` has fewer entries than `trace`. Index-based matching misaligned timings.
- **Fix:** Replaced index-based lookup with name-based consumed-index lookup: group timings by `node_type`, consume in order for each trace node with matching type name.
- **Files modified:** bae/repl/graph_commands.py
- **Verification:** test_inspect_inline_timing passes, TEnd shows timing, TStart shows no timing (correct)
- **Committed in:** eb2f6ac (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for correct timing display. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 27 gap closure complete. All UAT issues addressed.
- Graph mode fully usable: background execution doesn't block REPL, inspect shows clean formatted output.
- Ready for Phase 28 (Input Gates).

---
*Phase: 27-graph-mode*
*Completed: 2026-02-15*

## Self-Check: PASSED
