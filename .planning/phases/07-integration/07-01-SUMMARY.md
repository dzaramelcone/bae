---
phase: 07-integration
plan: 01
subsystem: exceptions, node
tags: [exceptions, type-hints, protocol, runtime_checkable, tdd]

# Dependency graph
requires:
  - phase: 06-node-lm-protocol
    provides: BaeError hierarchy, _wants_lm helper, LM Protocol, NodeConfig
provides:
  - DepError and FillError structured exception subclasses
  - Type-hint-based _wants_lm detection
  - @runtime_checkable LM Protocol
  - DepError/FillError in bae package exports
affects: [07-02 graph-run-v2, 07-03 runtime]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Type-hint-based parameter detection via get_type_hints + identity check"
    - "Structured exception attributes (node_type, field_name, trace) for diagnostics"

key-files:
  created:
    - tests/test_exceptions.py
  modified:
    - bae/exceptions.py
    - bae/node.py
    - bae/lm.py
    - bae/__init__.py
    - tests/test_node_config.py

key-decisions:
  - "Identity check (hint is LM) over issubclass to avoid Protocol edge cases"
  - "Removed from __future__ import annotations dependency for _wants_lm by using real LM import"
  - "DepError/FillError __str__ uses message as-is (terse, caller formats)"
  - "Exception tests in dedicated test_exceptions.py (not test_node_config.py)"

patterns-established:
  - "Structured exceptions carry node_type + trace for graph-level diagnostics"
  - "_wants_lm uses get_type_hints, not inspect.signature, for param detection"

# Metrics
duration: 6min
completed: 2026-02-08
---

# Phase 7 Plan 01: Exception Subclasses + Type-Hint _wants_lm Summary

**DepError/FillError structured exceptions with node_type/trace attributes, and _wants_lm rewritten from name-based to type-hint-based LM detection**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-08T02:47:51Z
- **Completed:** 2026-02-08T02:53:20Z
- **Tasks:** 2 (TDD, 4 commits)
- **Files modified:** 6

## Accomplishments
- DepError and FillError exception subclasses with structured attributes (node_type, field_name/validation_errors, attempts, trace)
- _wants_lm switched from param name check ("lm") to type hint check (LM protocol)
- LM Protocol decorated with @runtime_checkable for isinstance checks
- DepError and FillError exported from bae package

## Task Commits

Each task was committed atomically (TDD RED/GREEN):

1. **Task 1: DepError and FillError exceptions**
   - `5b8bcbc` test(07-01): add failing tests for DepError and FillError
   - `47b54f3` feat(07-01): implement DepError and FillError exception subclasses

2. **Task 2: _wants_lm type-hint detection + exports**
   - `1ae3d01` test(07-01): rewrite _wants_lm tests for type-hint detection
   - `323ffce` feat(07-01): type-hint-based _wants_lm and @runtime_checkable LM

## Files Created/Modified
- `tests/test_exceptions.py` - 14 tests for DepError/FillError attributes, chaining, inheritance
- `bae/exceptions.py` - Added DepError and FillError subclasses of BaeError
- `bae/node.py` - Rewrote _wants_lm to use get_type_hints + identity check against LM
- `bae/lm.py` - Added @runtime_checkable to LM Protocol
- `bae/__init__.py` - Added DepError, FillError to imports and __all__
- `tests/test_node_config.py` - Rewrote TestWantsLm for type-hint semantics (6 tests)

## Decisions Made
- Used `hint is LM` identity check rather than `issubclass` to avoid Protocol metaclass edge cases with runtime_checkable
- Moved LM import from TYPE_CHECKING to real import in node.py (required for get_type_hints to resolve "LM" strings from annotations)
- Exception __str__ delegates to message (caller formats the string, keeps exception class simple)
- Created dedicated test_exceptions.py rather than adding to test_node_config.py (cleaner separation of concerns)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- DepError and FillError ready for Graph.run() v2 (Plan 02) to raise on dep failures and fill validation failures
- _wants_lm type-hint detection ready for v2 runtime to inject LM by type, not name
- 306 tests pass, 0 failures, no regressions

---
*Phase: 07-integration*
*Completed: 2026-02-08*
