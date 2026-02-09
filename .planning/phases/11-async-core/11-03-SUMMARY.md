---
phase: 11-async-core
plan: 03
subsystem: graph-execution
tags: [async, graph, node, compiler, cli, asyncio]
dependency-graph:
  requires: ["11-01", "11-02"]
  provides: ["async-graph-run", "async-node-call", "asyncio-cli-boundary"]
  affects: ["11-04"]
tech-stack:
  added: []
  patterns: ["async-graph-execution", "asyncio.run-cli-boundary", "async-node-call"]
key-files:
  created: []
  modified:
    - bae/node.py
    - bae/graph.py
    - bae/compiler.py
    - bae/cli.py
    - tests/test_node.py
    - tests/test_graph.py
    - tests/test_auto_routing.py
    - tests/test_fill_protocol.py
    - tests/test_compiler.py
    - tests/test_dep_injection.py
    - tests/test_integration.py
    - tests/test_integration_dspy.py
    - tests/test_ootd_e2e.py
    - examples/ootd.py
decisions:
  - id: async-node-call
    choice: "Node.__call__ is async def, subclasses must override with async def"
    reason: "Consistent async throughout — all LM calls are async"
  - id: resolve-fields-stays-sync
    choice: "resolve_fields() remains sync (Phase 12)"
    reason: "Plan explicitly defers async dep resolution to Phase 12"
  - id: cli-asyncio-run
    choice: "Typer commands stay sync, wrap graph.run() with asyncio.run()"
    reason: "Typer doesn't support async commands; asyncio.run() is the standard boundary"
metrics:
  duration: "9 minutes"
  completed: "2026-02-09"
  tests-passed: 313
  tests-skipped: 10
  tests-failed: 0
---

# Phase 11 Plan 03: Async Graph Execution Summary

Converted Node.__call__, Graph.run(), CompiledGraph.run(), and CLI to async, completing the async conversion of all production code.

**One-liner:** Graph execution layer fully async with await on LM calls, node __call__, and asyncio.run() CLI boundary.

## What Was Done

### Task 1: Convert node.py, graph.py, compiler.py to async
- `Node.__call__` -> `async def __call__` with `await lm.decide(self)`
- `Graph.run()` -> `async def run()` with `await` on all LM calls (`choose_type`, `fill`) and custom `__call__` invocations
- `CompiledGraph.run()` -> `async def run()` with `await self.graph.run()`
- `resolve_fields()` intentionally kept sync (Phase 12 scope)
- All pure-computation helpers unchanged: `_get_routing_strategy`, `_build_context`, `_build_instruction`, `_discover`, `validate`, `to_mermaid`

### Task 2: Convert CLI to asyncio.run() boundary
- Added `import asyncio` to cli.py
- `run_graph()` wraps `graph.run()` with `asyncio.run()`
- Typer commands remain sync (Typer doesn't support async)

### Task 3: Migrate all tests and examples to async
- All MockLM classes across 8 test files: `make/decide/choose_type/fill` now `async def`
- All Node `__call__` in test files and examples: `async def` with `await` on LM calls
- All `graph.run()` calls: `await` in async test functions
- Re-enabled 3 `TestGraphFillIntegration` tests (were skipped pending this plan)
- DSPy mock predictors updated to use `predictor.acall()` pattern
- `examples/ootd.py`: async `__call__` + `asyncio.run()` in `__main__`
- 313 passed, 10 skipped (expected e2e/API-key skips), 0 failed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed graph._start -> graph.start in cli.py**
- **Found during:** Task 2
- **Issue:** CLI referenced `graph._start` which doesn't exist (attribute is `graph.start`)
- **Fix:** Changed to `graph.start` on lines 243 and 268
- **Files modified:** bae/cli.py
- **Commit:** c0fd585

**2. [Rule 3 - Blocking] Migrated additional test files and examples to async**
- **Found during:** Task 3
- **Issue:** Converting core methods to async broke all callers across the codebase, not just the 3 test files specified in the plan
- **Fix:** Updated 7 additional files: test_compiler.py, test_dep_injection.py, test_integration.py, test_integration_dspy.py, test_ootd_e2e.py, and examples/ootd.py
- **Files modified:** Listed above
- **Commit:** c252953

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Node.__call__ async | All subclasses must use `async def __call__` | Consistent async chain from node through LM calls |
| resolve_fields stays sync | Not awaited in Graph.run() | Phase 12 scope — dep resolution becomes async there |
| CLI boundary | `asyncio.run()` wraps `graph.run()` | Standard Python async boundary pattern; Typer is sync |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| b3eed3d | feat | Convert node, graph, compiler to async |
| c0fd585 | feat | Convert CLI to asyncio.run() boundary |
| c252953 | test | Migrate all tests and examples to async |

## Next Phase Readiness

Plan 11-04 (full test suite verification) should verify:
- All 313+ tests still passing
- No coroutine warnings in test output
- async patterns consistent across codebase
- The 3 re-enabled TestGraphFillIntegration tests stay green
