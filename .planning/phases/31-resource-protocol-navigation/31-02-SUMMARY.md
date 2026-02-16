---
phase: 31-resource-protocol-navigation
plan: 02
subsystem: repl
tags: [toolrouter, dispatch, pruning, resourcespace, homespace]

# Dependency graph
requires:
  - phase: 31-01
    provides: "Resourcespace protocol, ResourceRegistry, ResourceError, format_unsupported_error"
provides:
  - "ToolRouter with dispatch routing to current resource or homespace filesystem"
  - "Structure-first pruning at ~2000 chars with heading/table preservation"
  - "Homespace passthrough to _exec_* filesystem functions"
affects: [31-03, 32, 33]

# Tech tracking
tech-stack:
  added: []
  patterns: [ToolRouter dispatch, structure-first pruning, homespace fallback]

key-files:
  created:
    - bae/repl/tools.py
    - tests/test_tools_router.py
  modified:
    - bae/repl/resource.py

key-decisions:
  - "ResourceError promoted from dataclass to Exception subclass for proper raise/except semantics"
  - "Pruning keeps all structural lines (headings, tables, separators) and fills remaining budget with content"
  - "read('') at root lists registered resourcespaces instead of filesystem read"

patterns-established:
  - "ToolRouter dispatch: check registry.current, route to resource method or homespace _exec_*"
  - "Structure-first pruning: structural lines always kept, content lines trimmed to budget, [pruned:] indicator"

# Metrics
duration: 2min
completed: 2026-02-16
---

# Phase 31 Plan 02: ToolRouter Summary

**ToolRouter dispatching tool calls to current resource with homespace filesystem fallback and structure-first pruning at ~2000 chars**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-16T14:31:12Z
- **Completed:** 2026-02-16T14:33:30Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- ToolRouter dispatches read/write/edit/glob/grep to current resource when navigated in
- Falls through to filesystem _exec_* functions at homespace root
- read("") at root lists registered resourcespaces with descriptions
- Structure-first pruning preserves headings/tables, trims content to ~2000 chars with [pruned:] indicator
- Error output (ResourceError) bypasses pruning entirely

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Tests for ToolRouter dispatch, pruning, and error handling** - `1fd80b2` (test)
2. **Task 2: GREEN -- Implement ToolRouter with dispatch, pruning, and homespace fallback** - `31bda2b` (feat)

## Files Created/Modified
- `bae/repl/tools.py` - ToolRouter class with dispatch, _prune, homespace fallback, TOKEN_CAP/CHAR_CAP constants
- `tests/test_tools_router.py` - 19 tests covering dispatch routing, pruning, error handling, constants
- `bae/repl/resource.py` - ResourceError promoted from dataclass to Exception subclass

## Decisions Made
- ResourceError promoted from dataclass to Exception subclass so resource methods can raise/except it properly
- Pruning algorithm: keep all structural lines (headings, tables, separators, blank lines), fill remaining char budget with content lines from top, always include last content line
- read("") at root returns a listing of registered resourcespaces rather than attempting a filesystem read

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ResourceError not raisable as exception**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** ResourceError was a dataclass, not an Exception subclass -- `raise ResourceError(...)` fails with TypeError
- **Fix:** Promoted to `class ResourceError(Exception)` with same message/hints interface
- **Files modified:** bae/repl/resource.py
- **Verification:** All 699 tests pass including existing test_resource.py
- **Committed in:** 31bda2b (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for ResourceError raise/except semantics. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- ToolRouter ready for plan 03 (integration with shell/ai eval loop)
- All 699 tests pass plus 5 skipped

---
*Phase: 31-resource-protocol-navigation*
*Completed: 2026-02-16*
