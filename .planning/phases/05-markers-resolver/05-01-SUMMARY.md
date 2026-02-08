---
phase: 05-markers-resolver
plan: 01
subsystem: core
tags: [dataclass, markers, typing, annotated, field-classification]

# Dependency graph
requires:
  - phase: 01-signature-generation
    provides: "existing Dep/Context markers and Node base class"
  - phase: 01.1-deps-signature-extension
    provides: "v1 Dep(description) convention"
provides:
  - "v2 Dep(callable) marker for deferred field population"
  - "Recall() marker for execution trace field resolution"
  - "RecallError exception for missing trace matches"
  - "classify_fields() function for field type classification"
affects: [05-02, 05-03, 05-04, 06-graph-engine, 07-migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Annotated metadata inspection via get_type_hints(include_extras=True)"
    - "isinstance checks on Annotated args for marker classification"

key-files:
  created:
    - bae/resolver.py
    - tests/test_resolver.py
  modified:
    - bae/markers.py
    - bae/exceptions.py

key-decisions:
  - "Dep.fn is first field (before description) so Dep(callable) works positionally"
  - "Recall has no fields - trace search parameters determined by field type at resolve time"
  - "classify_fields skips 'return' key from get_type_hints"

patterns-established:
  - "Field classification: inspect Annotated metadata with isinstance checks"
  - "Backward compat: new fields with defaults prepended to existing dataclasses"

# Metrics
duration: 8min
completed: 2026-02-07
---

# Phase 5 Plan 01: Markers & Resolver Foundation Summary

**v2 Dep(callable) and Recall() markers with classify_fields() for Annotated metadata inspection**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-07
- **Completed:** 2026-02-07
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 4

## Accomplishments
- Dep(callable) stores a callable reference for deferred field population
- Dep(description="...") v1 backward compatibility preserved
- Recall() parameterless marker for execution trace resolution
- RecallError(BaeError) exception for missing trace matches
- classify_fields() correctly classifies dep/recall/plain fields via Annotated metadata
- 12 new tests, all passing; 202 existing tests unaffected

## Task Commits

Each task was committed atomically:

1. **Task 1: RED - Write failing tests** - `26a1b01` (test)
2. **Task 2: GREEN - Implement markers and classify_fields** - `3fead6f` (feat)

_TDD cycle: RED (failing tests) then GREEN (passing implementation). No refactor needed._

## Files Created/Modified
- `bae/markers.py` - Added `fn: Callable | None = None` to Dep, added Recall dataclass
- `bae/exceptions.py` - Added RecallError(BaeError)
- `bae/resolver.py` - New module with classify_fields() function
- `tests/test_resolver.py` - 12 tests covering markers, exception, and field classification

## Decisions Made
- Dep.fn placed as first positional field so `Dep(some_fn)` works without keyword; description remains as optional keyword arg for v1 compat
- Recall() has no fields; the trace search will use the annotated field's type (determined at resolve time, not marker creation)
- classify_fields() skips the "return" key that get_type_hints includes

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Markers and classify_fields ready for Plan 02 (resolve_fields) to consume
- All Phase 5 plans (02, 03, 04) depend on this foundation layer
- No blockers

---
*Phase: 05-markers-resolver*
*Completed: 2026-02-07*
