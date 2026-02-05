---
phase: 03-optimization
plan: 01
subsystem: optimizer
tags: [dspy, Example, trace, metric, bootstrapping]

# Dependency graph
requires:
  - phase: 02-dspy-integration
    provides: DSPyBackend, GraphResult.trace
provides:
  - trace_to_examples() converts execution traces to DSPy training format
  - node_transition_metric() scores predictions for optimizer selection
affects: [03-02, 03-03, optimization infrastructure]

# Tech tracking
tech-stack:
  added: []
  patterns: [trace-to-example conversion, type-match metric]

key-files:
  created: [bae/optimizer.py, tests/test_optimizer.py]
  modified: [bae/compiler.py, tests/test_*.py (forward reference fixes)]

key-decisions:
  - "Substring matching for flexible LLM output (EndNode matches 'The next node should be EndNode')"
  - "Return type depends on trace parameter: float for evaluation, bool for bootstrapping"
  - "model_fields accessed via type() to avoid deprecation warning"

patterns-established:
  - "trace_to_examples: iterate pairs, model_dump() fields, with_inputs() for input marking"
  - "metric: normalize to lowercase, check substring containment both directions"

# Metrics
duration: 7min
completed: 2026-02-05
---

# Phase 03 Plan 01: Trace-to-Example Conversion Summary

**DSPy Example conversion from GraphResult.trace with type-match metric for bootstrapping and evaluation**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-05T02:38:35Z
- **Completed:** 2026-02-05T02:46:30Z
- **Tasks:** 1 (TDD - 3 commits: test, feat, fix)
- **Files modified:** 8

## Accomplishments
- trace_to_examples() converts node traces to DSPy's training format with proper input marking
- node_transition_metric() returns correct types for evaluation (float) vs bootstrapping (bool)
- Case-insensitive substring matching handles flexible LLM output variations
- 22 comprehensive tests covering all edge cases

## Task Commits

TDD task produced multiple commits:

1. **RED: Failing tests** - `021daa9` (test)
   - 22 tests for trace conversion and metric function
   - Fixed pre-existing forward reference in compiler.py
2. **GREEN: Implementation** - `46ba2a7` (feat)
   - trace_to_examples() and node_transition_metric() in bae/optimizer.py
3. **FIX: Test infrastructure** - `fdb2e0b` (fix)
   - Forward reference fixes for Python 3.13 compatibility

## Files Created/Modified
- `bae/optimizer.py` - trace_to_examples() and node_transition_metric() (116 lines)
- `tests/test_optimizer.py` - TDD tests for conversion and metric (280 lines)
- `bae/compiler.py` - Added __future__.annotations for forward reference
- `tests/test_*.py` (6 files) - Forward reference fixes for Python 3.13

## Decisions Made
- **Substring matching**: LLM might say "EndNode" or "The next node should be EndNode" - both match
- **Bidirectional containment**: Check if expected in predicted OR predicted in expected
- **Bootstrap vs evaluation**: DSPy uses trace parameter to signal mode, returns bool vs float

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Forward reference in compiler.py**
- **Found during:** TDD RED phase (test collection)
- **Issue:** `CompiledGraph` used as return type before class fully defined
- **Fix:** Added `from __future__ import annotations` to compiler.py
- **Files modified:** bae/compiler.py
- **Verification:** Tests collect successfully
- **Committed in:** 021daa9 (part of test commit)

**2. [Rule 3 - Blocking] Forward references in test files**
- **Found during:** Full test suite run after implementation
- **Issue:** Python 3.13 doesn't defer annotation evaluation by default
- **Fix:** Added `from __future__ import annotations` to 6 test files
- **Fix:** Moved locally-defined test Node classes to module level where forward refs exist
- **Files modified:** tests/test_node.py, tests/test_graph.py, tests/test_integration.py, tests/test_integration_dspy.py, tests/test_bind_validation.py, tests/test_dep_injection.py
- **Verification:** Full test suite passes (145 tests)
- **Committed in:** fdb2e0b

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking)
**Impact on plan:** Both fixes necessary for tests to run on Python 3.13. Pre-existing bugs in codebase.

## Issues Encountered
- Python 3.13 requires explicit `from __future__ import annotations` for forward references, while Python 3.14+ handles this via PEP 649. Tests were likely created on 3.14.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Foundation for OPT-01 and OPT-02 complete
- trace_to_examples() and node_transition_metric() exported from bae.optimizer
- Ready for Graph.optimize() API (03-02) and BootstrapFewShot integration (03-03)

---
*Phase: 03-optimization*
*Completed: 2026-02-05*
