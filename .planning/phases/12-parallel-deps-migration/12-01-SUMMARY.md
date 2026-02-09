---
phase: 12-parallel-deps-migration
plan: 01
subsystem: resolver
tags: [asyncio, gather, topological-sort, graphlib, inspect, coroutine]

# Dependency graph
requires:
  - phase: 11-async-core
    provides: async Node.__call__, async graph.run(), asyncio.run() CLI boundary
provides:
  - async resolve_fields() with per-level asyncio.gather()
  - async resolve_dep() with mini-DAG topo-sort gather
  - _resolve_one() async helper with sync/async callable detection
  - _build_fn_dag() for single-callable DAG construction
affects: [12-02 graph.py await migration, 12-03 test migration, 12-04 verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Topo-sort level-by-level gather: prepare() -> get_ready() -> asyncio.gather() -> done()"
    - "Thin coroutine wrapper: sync callable inside async def participates in gather"
    - "inspect.iscoroutinefunction for runtime sync/async detection"

key-files:
  created: []
  modified:
    - bae/resolver.py

key-decisions:
  - "Added _build_fn_dag() helper for resolve_dep's mini-DAG rather than refactoring build_dep_dag, keeping existing sync functions unchanged"
  - "Tasks 1 and 2 committed atomically since resolve_dep and resolve_fields share _resolve_one and the topo-sort gather pattern"

patterns-established:
  - "Topo-sort gather: build DAG, prepare(), loop get_ready() with asyncio.gather(*[_resolve_one(...)]), cache results, done()"
  - "Sync/async callable detection via inspect.iscoroutinefunction -- sync called directly, async awaited"
  - "Declaration order preservation: iterate hints dict, map from dep/recall buckets"

# Metrics
duration: 3min
completed: 2026-02-09
---

# Phase 12 Plan 01: Async Resolver Summary

**async resolve_fields/resolve_dep with topo-sort level-by-level asyncio.gather for concurrent dep resolution**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-09T01:46:10Z
- **Completed:** 2026-02-09T01:48:49Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Converted resolve_fields() and resolve_dep() from sync to async def
- Independent deps on the same topo level now fire concurrently via asyncio.gather()
- Both sync and async dep callables supported via runtime inspect.iscoroutinefunction detection
- Declaration order preserved in resolved dict
- Recall fields resolved synchronously after deps (pure computation)
- All existing sync functions (classify_fields, recall_from_trace, build_dep_dag, validate_node_deps) unchanged

## Task Commits

Tasks 1 and 2 were committed together because the changes are tightly coupled -- `_resolve_one` is shared between `resolve_dep` and `resolve_fields`, and both functions were rewritten simultaneously:

1. **Task 1+2: Convert resolve_dep/resolve_fields to async with gather** - `e77d49c` (feat)

## Files Created/Modified

- `bae/resolver.py` - Added asyncio/inspect imports, async _resolve_one() helper, _build_fn_dag() helper, rewrote resolve_dep() and resolve_fields() as async with topo-sort gather

## Decisions Made

- **_build_fn_dag helper:** Created a separate `_build_fn_dag(fn)` function for resolve_dep's mini-DAG construction rather than generalizing `build_dep_dag`, because the plan specified keeping all existing sync functions unchanged.
- **Atomic commit for both tasks:** resolve_dep and resolve_fields share the _resolve_one helper and the topo-sort gather pattern. Splitting them into separate commits would create a broken intermediate state where resolve_fields calls a non-existent sync resolve_dep.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- resolver.py async conversion complete
- graph.py still calls resolve_fields synchronously (needs `await` -- Plan 02)
- test_resolver.py still calls resolve_dep/resolve_fields synchronously (needs async test migration -- Plan 03)
- Existing tests will NOT pass until Plan 02 (graph.py) and Plan 03 (test migration) are complete

---
*Phase: 12-parallel-deps-migration*
*Completed: 2026-02-09*
