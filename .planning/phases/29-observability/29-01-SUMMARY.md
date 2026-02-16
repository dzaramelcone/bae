---
phase: 29-observability
plan: 01
subsystem: engine
tags: [observability, output-policy, dep-timing, rss, lifecycle-events]

# Dependency graph
requires:
  - phase: 28-input-gates
    provides: "Gate hook pattern (GATE_HOOK_KEY), engine _execute/_wrap_coro lifecycle"
provides:
  - "OutputPolicy enum for per-graph verbosity control"
  - "DEP_TIMING_KEY sentinel and timing hook in resolver"
  - "GraphRun.dep_timings, rss_delta_bytes, policy fields"
  - "Structured lifecycle event emission via notify(content, meta)"
affects: [29-02, 29-03, graph-commands, views]

# Tech tracking
tech-stack:
  added: [resource, sys]
  patterns: [dep-cache-sentinel-for-timing, output-policy-gating, structured-notify]

key-files:
  created: []
  modified:
    - bae/repl/engine.py
    - bae/resolver.py
    - bae/repl/graph_commands.py
    - tests/repl/test_engine.py

key-decisions:
  - "DEP_TIMING_KEY as dep_cache sentinel, matching GATE_HOOK_KEY pattern"
  - "notify signature evolved to (content, meta=None) -- backward compatible"
  - "RSS via resource.getrusage high-water mark, not tracemalloc (zero overhead)"
  - "OutputPolicy on GraphRun, set at submit time via policy kwarg"

patterns-established:
  - "dep_cache sentinel pattern: inject hook callbacks via sentinel keys"
  - "Structured notify: content string + metadata dict for typed event routing"
  - "OutputPolicy gating: should_emit(event) checked before notify call"

# Metrics
duration: 4min
completed: 2026-02-15
---

# Phase 29 Plan 01: Engine Instrumentation Summary

**OutputPolicy enum with 4 verbosity levels, per-dep timing hooks in resolver, RSS measurement around graph execution, and structured lifecycle event emission through notify callback**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-16T00:15:31Z
- **Completed:** 2026-02-16T00:19:33Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- OutputPolicy enum (VERBOSE/NORMAL/QUIET/SILENT) gates event emission per graph run
- DEP_TIMING_KEY sentinel in resolver captures per-dep wall-clock durations via timed gather wrapper
- GraphRun extended with dep_timings, rss_delta_bytes, and policy fields
- Engine _execute and _wrap_coro emit structured start/complete/fail events with typed metadata
- 48 engine tests passing including 4 new observability tests

## Task Commits

Each task was committed atomically:

1. **Task 1: OutputPolicy enum + dep timing hook + RSS + GraphRun extensions** - `74129c3` (feat)
2. **Task 2: Update tests for engine instrumentation** - `d6f2746` (test)

## Files Created/Modified
- `bae/resolver.py` - Added DEP_TIMING_KEY sentinel and timed gather wrapper in resolve_fields
- `bae/repl/engine.py` - OutputPolicy enum, GraphRun extensions, _get_rss_bytes helper, structured event emission in _execute/_wrap_coro
- `bae/repl/graph_commands.py` - Updated _make_notify to accept 2-arg notify signature
- `tests/repl/test_engine.py` - Added OutputPolicy, dep timing, RSS delta, and notify metadata tests

## Decisions Made
- DEP_TIMING_KEY follows the established GATE_HOOK_KEY sentinel pattern in dep_cache
- notify signature changed from (msg: str) to (content: str, meta: dict | None = None) -- backward compatible since existing callers only use positional string
- RSS measurement uses resource.getrusage (zero overhead) rather than tracemalloc (10% CPU overhead)
- OutputPolicy stored on GraphRun and set at submit time via policy kwarg

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed _make_notify in graph_commands.py for 2-arg notify**
- **Found during:** Task 2 (full test suite verification)
- **Issue:** The notify callback in `_make_notify` accepted only 1 positional arg, but engine now calls `notify(content, meta)` with 2 args
- **Fix:** Updated `_make_notify` closure to accept `(content, meta=None)` and pass metadata through to router.write
- **Files modified:** bae/repl/graph_commands.py
- **Verification:** Full test suite (672 passed, 5 skipped)
- **Committed in:** d6f2746 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for backward compatibility of the notify signature change. No scope creep.

## Issues Encountered
- Forward reference resolution failure when defining DepStart inside test function -- moved to module level (standard Python annotation behavior with `from __future__ import annotations`)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Engine instrumentation layer complete: Plans 02 and 03 can consume OutputPolicy, dep_timings, rss_delta_bytes, and structured notify events
- All lifecycle events flow through the notify callback with typed metadata for view rendering
- No blockers

## Self-Check: PASSED

All 4 files verified present. Both commit hashes (74129c3, d6f2746) confirmed in git log.

---
*Phase: 29-observability*
*Completed: 2026-02-15*
