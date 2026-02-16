---
phase: 31-resource-protocol-navigation
plan: 03
subsystem: repl
tags: [integration, toolrouter, resourceregistry, shell, ai-agent, toolbar]

# Dependency graph
requires:
  - phase: 31-01
    provides: "Resourcespace protocol, ResourceRegistry, ResourceHandle"
  - phase: 31-02
    provides: "ToolRouter dispatch with pruning and homespace fallback"
provides:
  - "AI eval loop dispatching tool calls through ToolRouter"
  - "CortexShell with ResourceRegistry, ToolRouter, and navigation callables"
  - "Resource location injection into every AI prompt"
  - "Toolbar location widget showing breadcrumb when navigated in"
  - "AI prompt with resource navigation instructions"
affects: [32, 33, 34, 35, 36]

# Tech tracking
tech-stack:
  added: []
  patterns: [ToolRouter integration in eval loop, resource location injection, navigation callables in namespace]

key-files:
  created: []
  modified:
    - bae/repl/ai.py
    - bae/repl/shell.py
    - bae/repl/toolbar.py
    - bae/repl/ai_prompt.md

key-decisions:
  - "homespace/back are lambdas wrapping registry methods, not ResourceHandles (ResourceHandle.navigate would fail for these)"
  - "Resource location injected via _with_location into every _send call per Pitfall 1 from research"
  - "ResourceHandle instances and navigation names excluded from _build_context namespace dump"

patterns-established:
  - "Tool dispatch routing: run_tool_calls(text, router=) dispatches through ToolRouter when provided"
  - "Location injection: _with_location prepends [Location: breadcrumb] to every AI prompt"
  - "Navigation callables: homespace() and back() as namespace lambdas"

# Metrics
duration: 4min
completed: 2026-02-16
---

# Phase 31 Plan 03: Shell Integration Summary

**ToolRouter wired into AI eval loop with resource location injection, CortexShell creating registry/router and seeding navigation callables into namespace**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-16T14:35:05Z
- **Completed:** 2026-02-16T14:39:07Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- run_tool_calls routes through ToolRouter when router provided, 100% backward compatible
- CortexShell creates ResourceRegistry and ToolRouter, passes both to AI sessions
- homespace() and back() available as top-level namespace callables
- AI prompt includes resource navigation instructions
- Toolbar shows breadcrumb location when navigated into a resource
- Resource handles excluded from _build_context namespace dump

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire ToolRouter into run_tool_calls and update AI context** - `4ccffa9` (feat)
2. **Task 2: Create ResourceRegistry in CortexShell and seed namespace** - `71db311` (feat)

## Files Created/Modified
- `bae/repl/ai.py` - run_tool_calls with router dispatch, AI with tool_router/registry params, _with_location, _build_context skip list
- `bae/repl/shell.py` - ResourceRegistry/ToolRouter creation, namespace seeding, toolbar location widget
- `bae/repl/toolbar.py` - make_location_widget showing breadcrumb when navigated in
- `bae/repl/ai_prompt.md` - Resources section with navigation instructions

## Decisions Made
- homespace/back implemented as lambdas wrapping registry.homespace()/registry.back() rather than ResourceHandles, since ResourceHandle.__call__ routes to registry.navigate() which would fail for these navigation commands
- Resource location injected into every _send call via _with_location helper, not just initial _build_context, per Pitfall 1 from research
- ResourceHandle instances excluded from namespace dump via isinstance check in addition to name-based _SKIP set

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] homespace/back as lambdas instead of ResourceHandles**
- **Found during:** Task 2
- **Issue:** Plan specified `ResourceHandle("homespace", registry)` and `ResourceHandle("back", registry)`, but ResourceHandle.__call__ calls registry.navigate(name) which looks up a resourcespace by name -- no resourcespace named "homespace" or "back" exists
- **Fix:** Used `lambda: registry.homespace()` and `lambda: registry.back()` which call the correct registry methods
- **Files modified:** bae/repl/shell.py
- **Verification:** 699 tests pass
- **Committed in:** 71db311 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for correct navigation behavior. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Full resource protocol stack integrated: Protocol -> Registry -> ToolRouter -> AI -> Shell
- Ready for Phase 32+ to register concrete resourcespaces (source, tasks, etc.)
- All 699 tests pass plus 5 skipped

---
*Phase: 31-resource-protocol-navigation*
*Completed: 2026-02-16*
