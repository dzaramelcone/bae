---
phase: 08-cleanup-migration
plan: 01
subsystem: markers
tags: [cleanup, markers, Context, Bind, Dep, v1-removal]

# Dependency graph
requires:
  - phase: 07-integration
    provides: v2 runtime with resolve_fields, classify_fields replacing v1 Context/Bind
provides:
  - Clean source files with zero v1 marker references
  - Dep marker with fn-only field (no description)
  - Package exports without Context or Bind
affects:
  - 08-02 (test cleanup to match removed source code)
  - 08-03 (further test migration)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_build_inputs collects all node model_fields (not just Context-annotated)"

key-files:
  created: []
  modified:
    - bae/markers.py
    - bae/compiler.py
    - bae/dspy_backend.py
    - bae/graph.py
    - bae/__init__.py
    - bae/lm.py

key-decisions:
  - "_build_inputs now collects all model_fields from node, not just Context-annotated ones"
  - "v1 make/decide methods kept on LM Protocol for custom __call__ escape-hatch nodes"

patterns-established:
  - "Dep(callable) is the only Dep constructor form"

# Metrics
duration: 3min
completed: 2026-02-08
---

# Phase 8 Plan 01: Source-Side v1 Marker Removal Summary

**Deleted Context and Bind classes, removed Dep.description field, excised all v1 marker code from compiler/backend/graph/init/lm**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-08T03:57:45Z
- **Completed:** 2026-02-08T04:01:10Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Context and Bind classes fully deleted from markers.py
- Dep.description field removed, leaving fn-only constructor
- _extract_context_fields deleted from both compiler.py and dspy_backend.py
- _validate_bind_uniqueness deleted from graph.py
- Package __init__.py no longer exports Context or Bind
- LM Protocol docstring updated (no Phase 8 removal reference)

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove Context and Bind from markers.py, clean up Dep** - `1a2786f` (feat)
2. **Task 2: Remove v1 code from compiler, backend, graph, init, lm** - `4cb981a` (feat)

## Files Created/Modified
- `bae/markers.py` - Now exports only Dep(fn) and Recall; Context and Bind deleted
- `bae/compiler.py` - _extract_context_fields deleted, Context import removed, unused typing imports removed
- `bae/dspy_backend.py` - _extract_context_fields deleted, _build_inputs rewritten to collect all model_fields, Context/Dep/Annotated/get_origin imports removed
- `bae/graph.py` - _validate_bind_uniqueness deleted, Bind import removed
- `bae/__init__.py` - Context and Bind removed from imports and __all__
- `bae/lm.py` - LM Protocol docstring updated

## Decisions Made
- _build_inputs rewritten to collect ALL node model_fields (not filtering by Context annotation). This is correct v2 behavior since all fields are potential inputs.
- v1 make/decide methods kept on LM Protocol with updated docstring describing them as "kept for custom __call__ escape-hatch nodes" rather than "will be removed in Phase 8".

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Source files are clean of v1 marker references
- Tests will temporarily fail (expected) -- Plans 02 and 03 fix them
- No blockers for Plan 02 (test cleanup)

---
*Phase: 08-cleanup-migration*
*Completed: 2026-02-08*
