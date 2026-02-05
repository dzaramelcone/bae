---
phase: 04-production-runtime
plan: 01
subsystem: api
tags: [dspy, optimized-predictor, lm-backend, production]

# Dependency graph
requires:
  - phase: 03-optimization
    provides: load_optimized(), optimize_node(), CompiledGraph.optimized dict
  - phase: 02-dspy-integration
    provides: DSPyBackend with make/decide pattern
provides:
  - OptimizedLM backend extending DSPyBackend
  - Predictor registry lookup with fallback
  - Usage statistics for observability
affects: [04-02-PLAN (CompiledGraph.run integration)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "OptimizedLM extends DSPyBackend for predictor selection override"
    - "Dict-based predictor registry with type[Node] keys"
    - "Stats tracking for optimized vs naive predictor usage"

key-files:
  created:
    - bae/optimized_lm.py
    - tests/test_optimized_lm.py
  modified: []

key-decisions:
  - "Extend DSPyBackend rather than wrap (cleaner inheritance, preserves all behavior)"
  - "Use dict[type[Node], dspy.Predict] for O(1) predictor lookup"
  - "get_stats() returns copy to prevent external mutation"
  - "decide() inherited unchanged - uses our make() automatically"

patterns-established:
  - "OptimizedLM._get_predictor_for_target(target) for centralized predictor selection"
  - "self.stats dict with 'optimized' and 'naive' counters"
  - "Fallback to node_to_signature() when node type not in optimized dict"

# Metrics
duration: 5min
completed: 2026-02-05
---

# Phase 04 Plan 01: OptimizedLM Summary

**OptimizedLM backend using pre-loaded predictors with naive fallback and usage statistics**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-05T12:25:59Z
- **Completed:** 2026-02-05T12:31:29Z
- **Tasks:** 1 (TDD: test + feat)
- **Files modified:** 2

## Accomplishments
- OptimizedLM class extending DSPyBackend with predictor registry
- Pre-loaded predictor lookup when target type in optimized dict
- Graceful fallback to fresh predictor via node_to_signature
- Usage statistics tracking (optimized vs naive counts)
- 15 comprehensive test cases covering all behavior

## Task Commits

Each task was committed atomically:

1. **Task 1: TDD RED** - `711840a` (test: add failing tests for OptimizedLM)
2. **Task 1: TDD GREEN** - `aef8f24` (feat: implement OptimizedLM)

_TDD pattern: failing tests first, then implementation to make them pass_

## Files Created/Modified
- `bae/optimized_lm.py` - OptimizedLM class with predictor registry and stats
- `tests/test_optimized_lm.py` - 15 test cases covering optimized/naive selection, stats, retry behavior

## Decisions Made
- Extended DSPyBackend rather than creating wrapper (inherits all retry/error handling)
- Used type[Node] dict keys for O(1) lookup (class identity works correctly in Python)
- decide() not overridden - inherits from DSPyBackend and calls our make() method
- get_stats() returns shallow copy to prevent external mutation of stats dict

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- OptimizedLM complete, ready for CompiledGraph.run() integration (04-02)
- Stats observability available for production monitoring
- All DSPyBackend behavior preserved (retry, error handling, decide two-step)

---
*Phase: 04-production-runtime*
*Completed: 2026-02-05*
