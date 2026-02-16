---
phase: 32-source-resourcespace
plan: 05
subsystem: repl
tags: [navigation, resourcespace, tools, namespace, stack]

requires:
  - phase: 32-04
    provides: "Subresource classes with supported_tools() and children()"
provides:
  - "Stack-replacing navigation preventing breadcrumb accumulation"
  - "Resourcespace.tools() protocol method returning callable dict"
  - "Namespace injection of tool callables on navigate"
  - "Python-callable syntax in all error messages (no @ prefix)"
affects: [repl, ai-tools]

tech-stack:
  added: []
  patterns:
    - "tools() protocol method on Resourcespace for namespace injection"
    - "Stack divergence-point replacement for sibling navigation"
    - "_put_tools idempotent clear-then-update pattern"

key-files:
  created: []
  modified:
    - bae/repl/resource.py
    - bae/repl/source.py
    - bae/repl/shell.py
    - tests/test_resource.py
    - tests/test_source.py

key-decisions:
  - "Stack replacement uses identity comparison (is) to find common prefix"
  - "tools() returns dict of bound methods, not names -- callables ready for namespace"
  - "_TOOL_NAMES frozenset as single source of truth for cleanup on navigate"

patterns-established:
  - "Resourcespace.tools() returns dict[str, Callable] for namespace injection"
  - "ResourceRegistry._put_tools() idempotent: clear all tool names then update"

duration: 4min
completed: 2026-02-16
---

# Phase 32 Plan 05: Gap Closure Summary

**Stack-replacing navigation with tools() protocol injecting callables into REPL namespace**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-16T17:06:31Z
- **Completed:** 2026-02-16T17:11:07Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Navigation stack replaces from divergence point -- sibling nav (source.config -> source.deps) produces clean breadcrumb
- Resourcespace protocol gains tools() method returning dict of callables, injected into namespace on navigate
- All error messages and nav tree use Python-callable syntax (source() not @source())
- Tool injection is idempotent: clear all tool names then update with current resource's dict

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix navigation stack replacement and error message syntax** - `e9e34f5` (fix)
2. **Task 2: Add tools() to Resourcespace protocol and inject on navigate** - `2ae0c02` (feat)

## Files Created/Modified
- `bae/repl/resource.py` - Stack replacement logic, tools() protocol, _put_tools(), _TOOL_NAMES, @ removal
- `bae/repl/source.py` - tools() on all 5 resource classes, @ removal in enter()
- `bae/repl/shell.py` - Pass namespace to ResourceRegistry
- `tests/test_resource.py` - 7 new tests (stack replacement, @ removal, tool injection)
- `tests/test_source.py` - 5 new tests (tools() on each resource class)

## Decisions Made
- Stack replacement uses identity comparison (is) to find longest common prefix between current stack and new chain
- tools() returns bound methods directly -- callables ready for namespace use
- _TOOL_NAMES frozenset as single source of truth for which names to clear on navigate/homespace

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed dangling `resolved` variable reference**
- **Found during:** Task 1
- **Issue:** After refactoring navigate() to use chain-based logic, `resolved` variable was referenced but no longer defined
- **Fix:** Changed `self._entry_display(resolved)` to `self._entry_display(chain[-1])`
- **Files modified:** bae/repl/resource.py
- **Verification:** All tests pass
- **Committed in:** e9e34f5 (Task 1 commit)

**2. [Rule 1 - Bug] Updated test for new stack replacement behavior**
- **Found during:** Task 1
- **Issue:** test_back_pops_to_previous assumed stack accumulates across root navigations (old behavior)
- **Fix:** Changed test to use dotted navigation (source.meta) where back() returns to parent
- **Files modified:** tests/test_resource.py
- **Verification:** Test passes with correct semantics
- **Committed in:** e9e34f5 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both UAT-blocking gaps are resolved
- Navigation breadcrumb shows minimum path
- Tool callables available in PY mode namespace
- Ready for UAT re-test

---
*Phase: 32-source-resourcespace*
*Completed: 2026-02-16*
