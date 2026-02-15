---
phase: 26-engine-foundation
plan: 01
subsystem: graph-runtime
tags: [asyncio, dep-injection, subprocess, cancellation]

# Dependency graph
requires: []
provides:
  - "dep_cache parameter on Graph.arun() for external resource injection"
  - "asyncio.sleep(0) event loop yield in graph iteration loop"
  - "CancelledError subprocess cleanup in _run_cli_json"
affects: [26-02, 27-graph-commands, 28-input-gates]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "dep_cache pre-seeding bypasses dep function calls via resolver cache"
    - "Event loop yield at top of iteration loop prevents starvation"

key-files:
  created: []
  modified:
    - bae/graph.py
    - bae/lm.py
    - tests/test_graph.py

key-decisions:
  - "Renamed internal dep_cache variable to cache to avoid parameter shadowing"
  - "dep_cache merged after LM_KEY so callers can override LM if needed"
  - "CancelledError handled separately from TimeoutError for clarity"
  - "await process.wait() added after process.kill() for both error paths"

patterns-established:
  - "dep_cache injection: Graph.arun(dep_cache={fn: val}) pre-seeds resolver cache"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 26 Plan 01: Graph Runtime Injection Summary

**dep_cache parameter on Graph.arun() for external resource injection, asyncio.sleep(0) event loop yield, and CancelledError subprocess cleanup**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T14:24:04Z
- **Completed:** 2026-02-15T14:27:09Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Graph.arun() accepts dep_cache kwarg that pre-seeds the resolver cache, bypassing dep function calls for pre-seeded entries
- asyncio.sleep(0) at top of graph iteration loop yields to event loop on every iteration, preventing starvation during concurrent execution
- CancelledError in _run_cli_json kills subprocess and awaits cleanup, preventing orphaned Claude CLI processes on task cancellation
- Added await process.wait() after process.kill() in TimeoutError path too (was missing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dep_cache parameter and event loop yield** - `6c234a9` (feat)

## Files Created/Modified
- `bae/graph.py` - Added dep_cache keyword-only param to arun(), renamed internal variable to cache, added asyncio.sleep(0) yield
- `bae/lm.py` - Added CancelledError handling and await process.wait() in _run_cli_json
- `tests/test_graph.py` - Added 4 tests: dep_cache seeds resolver, default backward compat, no LM shadow, event loop yield

## Decisions Made
- Renamed internal `dep_cache` local variable to `cache` to avoid shadowing the new parameter name
- dep_cache is merged after LM_KEY initialization so the LM is always set first, but callers could theoretically override it
- CancelledError gets its own except clause (not combined with TimeoutError) because it re-raises directly rather than wrapping in RuntimeError

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- dep_cache parameter ready for Plan 02 (cortex engine) to inject TimingLM and external resources
- Event loop yield ensures concurrent graph runs won't starve the REPL
- Subprocess cleanup prevents orphans when graphs are cancelled via TaskManager

## Self-Check: PASSED

- FOUND: bae/graph.py
- FOUND: bae/lm.py
- FOUND: tests/test_graph.py
- FOUND: .planning/phases/26-engine-foundation/26-01-SUMMARY.md
- FOUND: commit 6c234a9

---
*Phase: 26-engine-foundation*
*Completed: 2026-02-15*
