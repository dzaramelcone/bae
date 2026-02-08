---
phase: 08-cleanup-migration
plan: 02
subsystem: tests
tags: [cleanup, tests, v1-removal, Context, Bind, Dep]

# Dependency graph
requires:
  - phase: 08-01
    provides: Source files with v1 markers removed (Context, Bind, Dep.description)
provides:
  - v2-only compiler tests (no Context/Bind/Dep references)
  - v2-only DSPy backend tests (plain fields, no Context annotations)
  - v2 signature tests without backward compat section
affects:
  - 08-03 (remaining test file migrations)

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - tests/test_compiler.py
    - tests/test_dspy_backend.py
    - tests/test_signature_v2.py
  deleted:
    - tests/test_bind_validation.py

key-decisions:
  - "TestNodeToSignature fixtures updated to use plain str fields (Context was just noise in v2)"
  - "NodeWithDep.__call__ db param changed from Annotated[str, Dep(description=...)] to plain str"
  - "TestBackwardCompat kept in test_signature_v2.py (tests valid v2 default behavior)"

patterns-established: []

# Metrics
duration: 4min
completed: 2026-02-08
---

# Phase 8 Plan 02: Compiler-Adjacent Test Migration Summary

**Deleted test_bind_validation.py, removed v1 Context/Bind/Dep(description) from test_compiler.py, test_dspy_backend.py, and test_signature_v2.py -- 41 tests passing**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-02-08T04:04:19Z
- **Completed:** 2026-02-08T04:08:10Z
- **Tasks:** 2
- **Files modified:** 3
- **Files deleted:** 1

## Accomplishments
- Deleted test_bind_validation.py entirely (7 dead tests for removed Bind marker)
- test_compiler.py: Deleted TestContextMarker (3 tests) and TestDepMarker (3 tests) classes
- test_compiler.py: Replaced Context-annotated fields with plain str fields in all fixtures
- test_compiler.py: Removed unused imports (pytest, Annotated, Context, Dep)
- test_dspy_backend.py: Replaced all Context annotations with plain fields in 4 node fixtures
- test_dspy_backend.py: Changed NodeWithDep.__call__ db param from Dep(description=...) to plain str
- test_signature_v2.py: Deleted TestExistingTestsStillPass class (imported deleted _extract_context_fields)
- All 41 remaining tests pass across the 3 files

## Task Commits

Each task was committed atomically:

1. **Task 1: Delete test_bind_validation.py and clean test_compiler.py** - `f46052d` (feat)
2. **Task 2: Migrate test_dspy_backend.py and test_signature_v2.py** - `45740c7` (feat)

## Files Created/Modified
- `tests/test_bind_validation.py` - DELETED (all 7 Bind tests dead)
- `tests/test_compiler.py` - TestContextMarker and TestDepMarker deleted; RunStartNode and TestNodeToSignature fixtures use plain fields; removed markers imports
- `tests/test_dspy_backend.py` - All 4 node fixtures use plain str fields; NodeWithDep.__call__ uses plain db param; removed Context/Dep/Annotated imports
- `tests/test_signature_v2.py` - TestExistingTestsStillPass class deleted

## Decisions Made
- TestNodeToSignature test fixtures updated to use plain `str` fields instead of `Annotated[str, Context(description=...)]`. The tests remain valid because v2 classify_fields treats Context-annotated fields the same as plain fields (both are "plain").
- TestBackwardCompat class kept in test_signature_v2.py because it tests valid v2 behavior (default is_start=False).
- Updated test method name/docstring `test_make_passes_context_fields_as_inputs` to `test_make_passes_node_fields_as_inputs` to reflect v2 semantics.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TestNodeToSignature fixtures also used Context annotations**
- **Found during:** Task 1
- **Issue:** Plan said to keep TestNodeToSignature intact, but its test fixtures used `Context(description=...)` which no longer exists. Tests would fail at import time.
- **Fix:** Updated all 5 test fixtures in TestNodeToSignature to use plain `str` fields. The tests still verify the same v2 behavior (plain fields become OutputFields on non-start nodes).
- **Files modified:** tests/test_compiler.py
- **Commit:** f46052d

## Issues Encountered
None.

## User Setup Required
None.

## Next Phase Readiness
- Compiler, DSPy backend, and signature v2 tests all clean and passing
- test_bind_validation.py deleted
- Ready for Plan 03 (remaining test file migrations)

---
*Phase: 08-cleanup-migration*
*Completed: 2026-02-08*
