---
phase: 06-node-lm-protocol
plan: 02
subsystem: compiler
tags: [dspy, signature, classify-fields, input-field, output-field]

# Dependency graph
requires:
  - phase: 05-markers-resolver
    provides: classify_fields() for Dep/Recall/plain field classification
provides:
  - v2 node_to_signature with classify_fields integration
  - is_start parameter for start node InputField semantics
  - Docstring-aware instruction generation
affects: [06-04-dspy-backend, 07-graph-execution, 08-cleanup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "classify_fields -> InputField/OutputField mapping via node_to_signature"
    - "is_start parameter controls plain field direction (Input vs Output)"

key-files:
  created:
    - tests/test_signature_v2.py
  modified:
    - bae/compiler.py
    - tests/test_compiler.py
    - tests/test_optimizer.py

key-decisions:
  - "Reuse _get_base_type from bae.graph rather than duplicating"
  - "Context marker fields are plain in v2 (classify_fields only knows Dep/Recall)"
  - "No generic output field -- OutputFields are node's actual plain fields"
  - "Docstring appended to class name for instruction text"

patterns-established:
  - "node_to_signature(cls, is_start=False) is the canonical signature builder"
  - "classify_fields drives all field -> DSPy field direction decisions"

# Metrics
duration: 11min
completed: 2026-02-08
---

# Phase 6 Plan 2: node_to_signature v2 with classify_fields Summary

**Redesigned node_to_signature to use classify_fields for Dep/Recall/plain -> InputField/OutputField mapping with is_start parameter for start node semantics**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-08T01:30:47Z
- **Completed:** 2026-02-08T01:41:23Z
- **Tasks:** 2 (RED + GREEN, no refactor needed)
- **Files modified:** 4

## Accomplishments
- node_to_signature now uses classify_fields from bae.resolver instead of Context markers
- is_start parameter makes plain fields InputFields on start nodes (caller-provided) vs OutputFields on non-start (LLM-filled)
- Dep and Recall fields are always InputFields regardless of is_start
- Instruction text includes docstring when present (ClassName: docstring)
- Full backward compat: calling without is_start defaults to non-start behavior
- 273 tests pass (14 new + updated existing)

## Task Commits

Each task was committed atomically:

1. **RED: Failing tests for v2 signature generation** - `b4fe0be` (test)
2. **GREEN: Implement v2 node_to_signature + update existing tests** - `d271d59` (feat)

_TDD plan: RED-GREEN cycle, no refactor needed (implementation is minimal and clean)_

## Files Created/Modified
- `bae/compiler.py` - v2 node_to_signature with classify_fields, is_start param, docstring instruction
- `tests/test_signature_v2.py` - 14 tests covering all v2 field mapping rules
- `tests/test_compiler.py` - Updated 5 old v1 tests to match v2 field behavior
- `tests/test_optimizer.py` - Updated 1 test for docstring-in-instruction change

## Decisions Made
- Reuse `_get_base_type` from `bae.graph` rather than duplicating or moving it
- Context-annotated fields are "plain" in v2 since classify_fields only recognizes Dep and Recall markers. This is correct -- Context is a Phase 1 concept that Phase 8 removes.
- No generic "output" OutputField anymore. OutputFields are the node's actual plain fields with their real names and types.
- `_extract_context_fields()` kept in compiler.py for v1 backward compat (Phase 8 cleanup removes it)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated v1 test_compiler.py tests for v2 behavior**
- **Found during:** GREEN phase verification
- **Issue:** Plan expected old tests to pass unchanged, but v2 fundamentally changes how Context markers and plain fields map to Input/OutputFields. Old tests asserted Context -> InputField and generic "output" -> OutputField, neither of which holds in v2.
- **Fix:** Updated 5 tests in TestNodeToSignature to assert v2 behavior (Context fields are plain -> OutputField on non-start, no generic output field, all fields included)
- **Files modified:** tests/test_compiler.py
- **Verification:** All 19 test_compiler.py tests pass
- **Committed in:** d271d59

**2. [Rule 1 - Bug] Updated test_optimizer.py instruction assertion**
- **Found during:** Full suite verification
- **Issue:** test_round_trip_uses_correct_signature_per_node expected instruction "StartNode" but v2 appends docstring to get "StartNode: A starting node."
- **Fix:** Updated assertion to match v2 instruction format
- **Files modified:** tests/test_optimizer.py
- **Verification:** Full suite passes (273 passed)
- **Committed in:** d271d59

---

**Total deviations:** 2 auto-fixed (2 bugs -- test assertions incompatible with v2 behavior)
**Impact on plan:** Both fixes necessary for correct test behavior. No scope creep. The plan's expectation that old tests would pass was incorrect because it assumed classify_fields would handle Context markers, but correctly, it only handles Dep and Recall.

## Issues Encountered
- Stale .pyc cache caused confusing test results where edited source files appeared to have no effect. Resolved by clearing `__pycache__` directories before test runs.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- node_to_signature v2 ready for DSPyBackend integration (06-04)
- classify_fields -> signature pipeline complete
- compile_graph still uses default is_start=False, will need update when DSPyBackend passes start node info

---
*Phase: 06-node-lm-protocol*
*Completed: 2026-02-08*
