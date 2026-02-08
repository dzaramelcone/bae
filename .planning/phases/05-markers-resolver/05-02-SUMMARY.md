---
phase: 05-markers-resolver
plan: 02
subsystem: resolver
tags: [graphlib, TopologicalSorter, CycleError, dep-dag, type-validation, tdd]

# Dependency graph
requires:
  - phase: 05-markers-resolver
    provides: "Dep/Recall markers, classify_fields"
provides:
  - "build_dep_dag() for topological dep ordering"
  - "validate_node_deps() for build-time dep validation"
  - "_callable_name() helper for human-readable function names"
affects: [05-04-resolver-execution, graph-validation]

# Tech tracking
tech-stack:
  added: [graphlib (stdlib)]
  patterns: [transitive-dep-walking, build-time-validation, keyword-only-is_start]

key-files:
  created: []
  modified:
    - bae/resolver.py
    - tests/test_resolver.py

key-decisions:
  - "Use id(fn) in visited set for walk deduplication (handles circular refs without hashing callables)"
  - "validate_node_deps calls build_dep_dag internally for cycle detection"
  - "Only first marker per field is processed (break after Dep or Recall)"
  - "CycleError formatted with _callable_name for human-readable cycle path"

patterns-established:
  - "Transitive dep walking: walk(fn) recursively inspects Dep-annotated params"
  - "Build-time validation pattern: collect errors as list[str], return empty for valid"

# Metrics
duration: 6min
completed: 2026-02-07
---

# Phase 5 Plan 2: Dep DAG Construction & Build-time Validation Summary

**build_dep_dag() with graphlib.TopologicalSorter for transitive dep ordering and validate_node_deps() catching cycles, type mismatches, missing annotations, and recall-on-start errors**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-08T00:15:15Z
- **Completed:** 2026-02-08T00:20:54Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- build_dep_dag() constructs TopologicalSorter from Dep-annotated fields with transitive walking (3+ levels deep)
- validate_node_deps() catches 4 error categories at build time: circular deps, return type mismatches (MRO), missing return annotations, recall on start node
- Circular dep detection produces human-readable function names via _callable_name()
- 12 new TDD tests covering all success criteria (6 DAG tests + 6 validation tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED - failing tests for dep DAG and validation** - `c7a4293` (test)
2. **Task 2: GREEN - implement build_dep_dag and validate_node_deps** - `f4a03b5` (feat)

_TDD cycle: RED (failing tests) then GREEN (implementation). No REFACTOR needed._

## Files Created/Modified
- `bae/resolver.py` - Added build_dep_dag(), validate_node_deps(), _callable_name() functions
- `tests/test_resolver.py` - Added TestBuildDepDag (6 tests) and TestValidateNodeDeps (6 tests) plus dep test helper functions

## Decisions Made
- Used `id(fn)` for visited set deduplication instead of hashing callables directly (avoids issues with unhashable or mutable callables)
- `validate_node_deps` calls `build_dep_dag` internally and catches `CycleError` to include cycle errors in the validation error list
- Only the first Dep/Recall marker per field is processed (consistent with classify_fields behavior)
- Circular dep test uses annotation patching (`__annotations__` dict mutation) after both functions are defined, avoiding forward reference issues

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **Parallel plan 05-03**: Both plans modify `tests/test_resolver.py` and `bae/resolver.py`. Plan 05-03 had already added `recall_from_trace` stubs and test imports to the working tree. Resolved by working with the current file state and staging only plan-specific files. The resolver.py commit includes 05-03's `recall_from_trace` implementation alongside 05-02's functions since both were in the same file.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- build_dep_dag() ready for consumption by Plan 04 (resolver execution)
- validate_node_deps() ready for Graph.validate() integration
- TopologicalSorter returned to caller for flexible use (static_order or prepare/done cycle)

---
*Phase: 05-markers-resolver*
*Completed: 2026-02-07*
