---
phase: 12-parallel-deps-migration
plan: 02
subsystem: graph-api
tags: [asyncio, sync-wrapper, run-arun-split, caller-migration]

# Dependency graph
requires:
  - phase: 12-01
    provides: async resolve_fields(), async resolve_dep()
provides:
  - Graph with sync run() and async arun()
  - CompiledGraph with sync run() and async arun()
  - CLI calling graph.run() directly (no asyncio.run wrapper)
  - Examples calling graph.run() directly (no asyncio.run wrapper)
  - All tests updated to use arun() in async contexts
affects: [12-03 test migration, 12-04 verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - sync-over-async: "sync def run() wraps asyncio.run(self.arun(...))"
    - dual-api: "run() for sync callers, arun() for async callers"

# File tracking
key-files:
  modified:
    - bae/graph.py
    - bae/compiler.py
    - bae/cli.py
    - examples/ootd.py
    - tests/test_auto_routing.py
    - tests/test_compiler.py
    - tests/test_dep_injection.py
    - tests/test_fill_protocol.py
    - tests/test_graph.py
    - tests/test_integration.py
    - tests/test_integration_dspy.py
    - tests/test_ootd_e2e.py
    - tests/test_resolver.py

# Decisions
decisions:
  - id: run-arun-naming
    choice: "run() sync, arun() async"
    reason: "Standard pattern (httpx, SQLAlchemy). Sync is primary public API."
  - id: asyncio-run-boundary
    choice: "Graph.run() calls asyncio.run(self.arun(...))"
    reason: "Clean sync boundary. Cannot be called from running event loop (RuntimeError)."

# Metrics
metrics:
  duration: ~7 minutes
  completed: 2026-02-09
  tests: "313 passed, 10 skipped, 0 failures"
---

# Phase 12 Plan 02: Graph run/arun Split Summary

**Split Graph.run() into sync run() + async arun(), migrated all callers, updated tests.**

## What Was Done

### Task 1: Split Graph.run() into sync run() and async arun()

Split the existing `async def run()` on Graph into two methods:

- **`def run()`** -- sync wrapper calling `asyncio.run(self.arun(...))`. Primary public API.
- **`async def arun()`** -- full async execution loop (the original body). For callers already in an event loop.

Added `await` to both `resolve_fields()` calls inside `arun()`:
- Line 270: `resolved = await resolve_fields(current.__class__, trace, dep_cache)` -- current node resolution
- Line 321: `target_resolved = await resolve_fields(target_type, trace, dep_cache)` -- target node resolution before fill

DepError wrapping preserved around the current-node resolve_fields call.

**Commit:** `75b9acc`

### Task 2: Update CompiledGraph, CLI, examples, and __init__.py

- **bae/compiler.py:** Added sync `run()` + async `arun()` to CompiledGraph. `arun()` delegates to `graph.arun()`.
- **bae/cli.py:** Removed `import asyncio`. Changed `asyncio.run(graph.run(...))` to `graph.run(...)`.
- **examples/ootd.py:** Removed `import asyncio` from `__main__` block. Changed to `graph.run(...)`.
- **examples/run_ootd_traced.py:** Already called `graph.run()` without asyncio.run -- now correct since run() is sync.

**Commit:** `13b7048`

### Test Updates (Deviation)

Updated all test files to call `graph.arun()` and `compiled.arun()` instead of `graph.run()` / `compiled.run()` since tests run inside an event loop (pytest-asyncio). Also converted `TestResolveDep` and `TestResolveFields` to async with `await` since resolve_dep/resolve_fields became async in 12-01.

**Commit:** `765f165`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Tests calling await graph.run() broke with sync run()**

- **Found during:** Task 2 verification
- **Issue:** All async tests called `await graph.run(...)` which fails because `run()` is now sync (not a coroutine). `asyncio.run()` inside `run()` raises RuntimeError when called from a running event loop.
- **Fix:** Changed all test calls from `await graph.run()` to `await graph.arun()` across 8 test files. Updated compiler test mock to patch `graph.arun` instead of `graph.run`.
- **Files modified:** tests/test_auto_routing.py, tests/test_compiler.py, tests/test_dep_injection.py, tests/test_fill_protocol.py, tests/test_graph.py, tests/test_integration.py, tests/test_integration_dspy.py, tests/test_ootd_e2e.py
- **Commit:** `765f165`

**2. [Rule 3 - Blocking] TestResolveDep/TestResolveFields not async after 12-01**

- **Found during:** Task 2 verification (full test run)
- **Issue:** resolve_dep() and resolve_fields() became async in 12-01 but their direct-call tests in test_resolver.py were not updated. Tests returned coroutine objects instead of asserting values.
- **Fix:** Converted all TestResolveDep and TestResolveFields methods to `async def` with `await` on resolve_dep/resolve_fields calls.
- **Files modified:** tests/test_resolver.py
- **Commit:** `765f165`

## Verification

All must_haves truths verified:
- Graph.run() is sync def (calls asyncio.run internally) -- confirmed via `inspect.iscoroutinefunction`
- Graph.arun() is async def -- confirmed
- CompiledGraph.run() is sync def, CompiledGraph.arun() is async def -- confirmed
- CLI calls graph.run() directly (no asyncio.run wrapper) -- confirmed, no asyncio import in cli.py
- ootd.py __main__ calls graph.run() directly -- confirmed, no asyncio import
- DepError wrapping preserved in graph.arun() around resolve_fields -- confirmed
- resolve_fields() calls in graph.arun() use await -- confirmed, two occurrences

## Next Phase Readiness

Ready for 12-03 (test migration) and 12-04 (verification). All existing tests pass (313/313 + 10 skipped). The test migration in this plan may overlap with 12-03's scope -- tests are already updated for the run/arun split.
