---
phase: 17-namespace
plan: 03
subsystem: repl
tags: [get_type_hints, sys.modules, annotation-resolution, types.ModuleType]

# Dependency graph
requires:
  - phase: 17-01
    provides: "NsInspector and seed() with classify_fields integration"
  - phase: 17-02
    provides: "Shell namespace wiring and async_exec integration"
provides:
  - "<cortex> module registered in sys.modules for REPL annotation resolution"
  - "REPL-defined Node subclasses work with ns(), graph creation, lm.fill, compiler"
affects: [repl, resolver, graph, lm, compiler]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sys.modules registration for synthetic module annotation resolution"
    - "namespace.__name__ = '<cortex>' for correct __module__ on REPL-defined classes"

key-files:
  created: []
  modified:
    - bae/repl/exec.py
    - tests/repl/test_namespace.py

key-decisions:
  - "Register <cortex> in sys.modules rather than threading globalns through resolver/lm/compiler"
  - "Set __name__='<cortex>' via setdefault so classes get correct __module__ from FunctionType globals"

patterns-established:
  - "_ensure_cortex_module: sync REPL namespace into sys.modules before compile()"

# Metrics
duration: 2min
completed: 2026-02-14
---

# Phase 17 Plan 03: Gap Closure Summary

**Register `<cortex>` as a sys.modules entry so get_type_hints resolves Annotated/Dep/Recall on REPL-defined Node subclasses**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-14T01:12:52Z
- **Completed:** 2026-02-14T01:15:11Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `_ensure_cortex_module()` registers `<cortex>` in sys.modules with REPL namespace contents
- All `get_type_hints()` call sites across bae (resolver, graph, lm, compiler) resolve correctly for REPL-defined classes -- zero production code changes
- `ns(REPLDefinedNodeClass)` displays field info (name, kind, markers) without NameError
- 115/115 REPL tests pass (114 existing + 1 new)

## Task Commits

Each task was committed atomically:

1. **Task 1: Register cortex module in sys.modules** - `4042754` (feat)
2. **Task 2: Add test proving ns() works with REPL-simulated Node subclass** - `acd09e9` (test)

## Files Created/Modified
- `bae/repl/exec.py` - Added `_ensure_cortex_module()` function, called before `compile()` in `async_exec()`
- `tests/repl/test_namespace.py` - Added `test_inspect_repl_defined_node_class` async test

## Decisions Made
- **Option 3 (sys.modules registration) over Option 2 (threading globalns):** Complete fix with zero production code changes. All 10+ get_type_hints call sites across resolver.py, lm.py, compiler.py, graph.py resolve correctly without modification.
- **`setdefault('__name__', '<cortex>')` in namespace:** Python's `type()` metaclass reads `globals()['__name__']` to set `__module__` on new classes. Without this, classes defined via `FunctionType(compiled, namespace)` get `__module__='builtins'` instead of `'<cortex>'`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Set __name__='<cortex>' in namespace for correct __module__**
- **Found during:** Task 2 (test_inspect_repl_defined_node_class)
- **Issue:** Classes defined via `types.FunctionType(compiled, namespace)` get `__module__` from `namespace['__name__']`, not from `compile()`'s filename argument. Without `__name__` in the namespace, classes got `__module__='builtins'` instead of `'<cortex>'`, so the sys.modules registration had no effect.
- **Fix:** Added `namespace.setdefault('__name__', '<cortex>')` in `_ensure_cortex_module()` before module registration.
- **Files modified:** `bae/repl/exec.py`
- **Verification:** Test asserts `test_cls.__module__ == "<cortex>"` and ns() output contains field info.
- **Committed in:** `acd09e9` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential for correctness -- without __name__, the module registration would be ineffective. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 17 (Namespace) fully complete including gap closure
- All UAT criteria satisfied: ns() works with REPL-defined Node subclasses
- Ready for Phase 18

## Self-Check: PASSED

All files exist, all commits verified, all functions present.

---
*Phase: 17-namespace*
*Completed: 2026-02-14*
