---
phase: 29-observability
plan: 02
subsystem: repl
tags: [observability, debug, lifecycle-events, views, output-policy]

# Dependency graph
requires:
  - phase: 29-01
    provides: "OutputPolicy enum, dep_timings, rss_delta_bytes, structured notify(content, meta)"
provides:
  - "debug command: asyncio.format_call_graph for stuck graph diagnosis"
  - "Enhanced inspect with dep timings and RSS delta sections"
  - "Output policy flags (--verbose/--quiet/--silent) on run command"
  - "UserView lifecycle event rendering with [graph:run_id] prefix and color coding"
  - "Notify callback: gate events respect shush, lifecycle always flows through"
affects: [29-03, graph-commands, views]

# Tech tracking
tech-stack:
  added: []
  patterns: [lifecycle-event-rendering, flag-parsing-on-run-command, metadata-type-routing]

key-files:
  created: []
  modified:
    - bae/repl/graph_commands.py
    - bae/repl/views.py
    - bae/repl/engine.py
    - tests/repl/test_graph_commands.py
    - tests/repl/test_views.py

key-decisions:
  - "Notify shush applies only to gate events, not lifecycle -- lifecycle always flows through"
  - "Output policy flags parsed from run arg string via split/remove before eval"
  - "GraphRun.policy set at creation time in submit/submit_coro, not deferred to async task"
  - "Lifecycle events in UserView use color-coded styles: dim=start, green=complete, red=fail, yellow=cancel"

patterns-established:
  - "Flag parsing on GRAPH commands: split, match, remove, rejoin before eval"
  - "Metadata-type routing in views: content_type + channel_name for specialized rendering"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 29 Plan 02: Display Layer Wiring Summary

**Graph lifecycle events rendered in UserView with color-coded [graph:run_id] prefix, debug command for asyncio call graphs, enhanced inspect with dep/RSS data, and output policy flags on run command**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-16T00:22:05Z
- **Completed:** 2026-02-16T00:25:37Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- debug command shows asyncio.format_call_graph for running/waiting graph tasks
- UserView renders lifecycle events with [graph:run_id] prefix and color-coded styles per event type
- inspect command extended with "Dep timings:" section and "RSS delta:" line
- run command parses --verbose/--quiet/--silent flags, passes OutputPolicy to engine
- Notify callback refined: only gate events respect shush mode, lifecycle always flows through
- 81 view/command tests and 687 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Graph commands -- debug, enhanced inspect, output policy, notify update** - `8f21f20` (feat)
2. **Task 2: View rendering for graph lifecycle events + tests** - `f451ea7` (test)

## Files Created/Modified
- `bae/repl/graph_commands.py` - debug command, enhanced inspect, output policy flags, updated notify
- `bae/repl/views.py` - Lifecycle event rendering in UserView with color-coded [graph:run_id] prefix
- `bae/repl/engine.py` - GraphRun.policy set at creation in submit/submit_coro
- `tests/repl/test_graph_commands.py` - TestNotify, TestCmdDebug, TestInspectEnhanced, TestOutputPolicy
- `tests/repl/test_views.py` - Lifecycle event rendering tests for UserView

## Decisions Made
- Notify shush applies only to gate events -- lifecycle events always flow through regardless of shush state
- Output policy flags parsed via simple split/match/remove on the arg string before eval
- GraphRun.policy set at creation time so it's immediately visible (not deferred to background task start)
- Lifecycle event styles in UserView: dim gray for start, green for complete, red for fail, yellow for cancel

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] GraphRun.policy not set at creation time**
- **Found during:** Task 2 (TestOutputPolicy test)
- **Issue:** `submit()` and `submit_coro()` created GraphRun with default NORMAL policy, then passed policy kwarg to the async _execute/_wrap_coro. Policy wasn't set until the background task started, causing test to see NORMAL instead of VERBOSE.
- **Fix:** Pass `policy=policy` to `GraphRun()` constructor in both `submit()` and `submit_coro()`
- **Files modified:** bae/repl/engine.py
- **Verification:** TestOutputPolicy passes, full suite 687 passed
- **Committed in:** f451ea7 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for policy visibility consistency. No scope creep.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Display layer wiring complete: lifecycle events render in all views, debug command available for stuck graphs
- Plan 03 can build on enhanced inspect data and lifecycle event flow for any remaining observability features
- No blockers

## Self-Check: PASSED

All 5 files verified present. Both commit hashes (8f21f20, f451ea7) confirmed in git log.

---
*Phase: 29-observability*
*Completed: 2026-02-15*
