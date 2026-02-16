---
phase: 26-engine-foundation
plan: 03
subsystem: runtime
tags: [graph, subprocess, defensive-coding, sigint]

requires:
  - phase: 26-01
    provides: "Graph class, ClaudeCLIBackend._run_cli_json"
provides:
  - "Runtime isinstance guard preventing cryptic unhashable-type errors"
  - "Process group isolation for Claude CLI subprocesses (Ctrl-C safe)"
affects: [28-input-gates, repl]

tech-stack:
  added: []
  patterns:
    - "Guard pattern: validate class-vs-instance at API boundary before internal use"
    - "start_new_session=True on all subprocesses for SIGINT isolation"

key-files:
  created: []
  modified:
    - bae/graph.py
    - bae/lm.py
    - tests/test_graph.py

key-decisions:
  - "isinstance(start, type) guard placed before self.start assignment so _discover() never sees an instance"
  - "Error message includes both diagnosis and fix suggestion (Use Graph(start=X) instead of Graph(start=X(...)))"

patterns-established:
  - "All asyncio.create_subprocess_exec calls use start_new_session=True"

duration: 1min
completed: 2026-02-15
---

# Phase 26 Plan 03: UAT Gap Closure Summary

**Graph.__init__ instance guard with actionable TypeError, and subprocess SIGINT isolation via start_new_session**

## Performance

- **Duration:** 1 min
- **Started:** 2026-02-15T15:27:47Z
- **Completed:** 2026-02-15T15:28:45Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Graph(start=SomeNode()) now raises TypeError with message telling user to pass the class
- ClaudeCLIBackend._run_cli_json subprocess isolated in own session -- Ctrl-C no longer kills REPL
- All 596 tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Graph instance guard and subprocess isolation** - `06c33eb` (fix)

## Files Created/Modified
- `bae/graph.py` - Added isinstance guard at top of Graph.__init__ before _discover()
- `bae/lm.py` - Added start_new_session=True to create_subprocess_exec in _run_cli_json
- `tests/test_graph.py` - Two tests: rejects instance, error message suggests fix

## Decisions Made
- Guard uses `isinstance(start, type)` rather than checking for Node subclass -- catches all non-class values
- Error message includes both the problem ("got an instance of X") and the fix ("Use Graph(start=X)")
- Two separate tests: one for the rejection, one for the fix suggestion in the message

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Both UAT gaps from 26-03 closed
- Plan 26-04 (remaining UAT gap closure) is the final plan in Phase 26
- All subprocess calls now use start_new_session=True consistently

## Self-Check: PASSED

All files exist, commit 06c33eb verified, isinstance guard and start_new_session present in source.

---
*Phase: 26-engine-foundation*
*Completed: 2026-02-15*
