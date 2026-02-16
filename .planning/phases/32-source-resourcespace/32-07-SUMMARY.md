---
phase: 32-source-resourcespace
plan: 07
subsystem: repl
tags: [resourcespace, navigation, orientation, ai-prompt]

requires:
  - phase: 31-resourcespace-nav
    provides: ResourceRegistry with homespace(), back(), navigation stack
provides:
  - "home() as first-class resource with tools and procedural orientation"
  - "_build_orientation() for AI system prompt content at root"
  - "_home_tools injection for read/glob/grep at home level"
affects: [ai-prompt, resource-navigation]

tech-stack:
  added: []
  patterns:
    - "Orientation builder: procedural string listing resourcespaces and tools"
    - "Home tools: filesystem helpers injected at root via _home_tools dict"

key-files:
  created: []
  modified:
    - bae/repl/resource.py
    - bae/repl/shell.py
    - bae/repl/tools.py
    - bae/repl/ai.py
    - bae/repl/ai_prompt.md
    - tests/test_resource.py
    - tests/test_tools_router.py

key-decisions:
  - "home() returns NavResult wrapping _build_orientation(), not the Rich tree from _root_nav()"
  - "_with_location injects orientation at root so AI gets resourcespace context on every call"
  - "_root_nav() preserved for nav tree rendering; home/back at root use orientation instead"

patterns-established:
  - "Orientation pattern: procedural string built from registry state for AI context"

duration: 3min
completed: 2026-02-16
---

# Phase 32 Plan 07: home() as Procedural Orientation Builder Summary

**Renamed homespace() to home() with procedural orientation string listing resourcespaces and tools, injected into AI system prompt at root**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-16T17:37:46Z
- **Completed:** 2026-02-16T17:40:24Z
- **Tasks:** 1
- **Files modified:** 7

## Accomplishments
- Renamed homespace() to home() across all source and test files
- Added _build_orientation() that procedurally builds AI-readable orientation string
- Wired home-level tools (read/glob/grep) via _home_tools dict on registry
- Updated _with_location to inject orientation at root for every AI call
- Added tests for home tool injection, orientation output, and back-to-root orientation

## Task Commits

Each task was committed atomically:

1. **Task 1: Rename homespace to home and add orientation builder** - `188f602` (feat)

## Files Created/Modified
- `bae/repl/resource.py` - Added _home_tools, _build_orientation(), renamed homespace() to home()
- `bae/repl/shell.py` - Wired home tools from ai.py helpers, renamed namespace binding
- `bae/repl/tools.py` - Renamed _homespace_dispatch to _home_dispatch
- `bae/repl/ai.py` - Updated _with_location to inject orientation at root, renamed in _SKIP
- `bae/repl/ai_prompt.md` - Replaced homespace() with home()
- `tests/test_resource.py` - Renamed tests, added orientation and tool injection tests
- `tests/test_tools_router.py` - Renamed homespace test reference

## Decisions Made
- home() returns NavResult wrapping _build_orientation(), not the Rich tree from _root_nav() -- the orientation string is what the AI sees, the nav tree is for human rendering
- _with_location injects full orientation at root so AI gets resourcespace context on every call, while inside a resource only breadcrumb is needed
- _root_nav() preserved as-is for nav tree rendering; only home/back at root use orientation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 32 gap closure complete (plans 06 and 07)
- home() is a first-class resource with tools, orientation, and AI integration
- Ready for next milestone phases

---
*Phase: 32-source-resourcespace*
*Completed: 2026-02-16*
