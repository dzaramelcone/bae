---
phase: 12-parallel-deps-migration
plan: 04
subsystem: resolver-tests
tags: [tdd, async, concurrency, pytest, resolver]
depends_on:
  requires: ["12-01", "12-02"]
  provides: ["parallel-dep-test-coverage"]
  affects: []
tech-stack:
  added: []
  patterns: ["asyncio.sleep timing tests", "execution-order interleaving assertions"]
key-files:
  created: ["tests/test_parallel_deps.py"]
  modified: []
decisions:
  - id: "12-04-01"
    choice: "Module-scope dep functions for Python 3.14 PEP 649 compatibility"
    why: "get_type_hints evaluates annotations in module scope -- locally-defined functions in test methods fail NameError"
metrics:
  duration: "3m17s"
  completed: "2026-02-09"
---

# Phase 12 Plan 04: Parallel Dep Resolution Tests Summary

TDD test suite for Phase 12 async resolver: concurrent gather, sync/async mixing, topo ordering, caching, fail-fast, DepError wrapping, run/arun API.

## What Was Done

21 new tests across 8 test classes covering all Phase 12 parallel dep resolution behavior:

| Class | Tests | Area |
|---|---|---|
| TestConcurrentGather | 2 | Timing-based concurrency proof + execution interleaving |
| TestSyncAsyncMixing | 3 | Mixed sync/async deps through resolve_fields and resolve_dep |
| TestAsyncDetection | 3 | inspect.iscoroutinefunction dispatch verification |
| TestTopoOrdering | 2 | Transitive dep ordering (2-level and 3-level chains) |
| TestCacheCorrectness | 3 | Per-run cache sharing, identity, call-count verification |
| TestFailFast | 3 | Raw exception propagation, no ExceptionGroup wrapping |
| TestDepErrorWrapping | 2 | Graph.arun DepError with node_type and cause chain |
| TestRunArunAPI | 3 | Sync run(), async arun(), run()-in-loop RuntimeError |

## TDD Flow

Since the implementation already existed (resolver.py from 12-01, graph.py from 12-02), the RED/GREEN phases collapsed:

- **RED:** One test (`test_deep_transitive_chain`) initially failed due to Python 3.14 PEP 649 annotation scoping -- locally-defined async dep functions inside test methods weren't visible to `get_type_hints`. This was a test design issue, not an implementation bug.
- **GREEN:** Moved dep functions to module scope. All 21 tests pass.
- **REFACTOR:** Suppressed expected RuntimeWarning on `test_run_from_running_event_loop_raises` (unawaited coroutine when asyncio.run fails).

## Deviations from Plan

None -- plan executed exactly as written.

## Test Results

```
344 collected, 334 passed, 10 skipped, 0 failures
New tests: 21 (from 323 to 344)
```

## Decisions Made

1. **Module-scope dep functions for PEP 649 compatibility** -- Python 3.14's deferred annotation evaluation means `get_type_hints()` resolves annotations in module scope. Dep functions referenced in `Annotated[T, Dep(fn)]` type hints must be visible at module level, not defined inside test method bodies.

## Commits

| Hash | Message |
|---|---|
| fcfd5e3 | test(12-04): add parallel dep resolution test suite |

## Next Phase Readiness

Phase 12 is complete. All 4 plans executed:
- 12-01: Async resolver conversion (resolve_fields, resolve_dep, _resolve_one)
- 12-02: Graph run/arun split + test migration
- 12-03: Existing test async migration (done as deviation in 12-02)
- 12-04: New parallel dep behavior tests (this plan)

v3.0 async graphs milestone ready for wrap-up.
