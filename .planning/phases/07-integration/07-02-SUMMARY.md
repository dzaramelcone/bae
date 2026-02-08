---
phase: 07-integration
plan: 02
subsystem: graph-runtime
tags: [graph, run, resolve-fields, choose-type, fill, dep-injection, v2]
dependency-graph:
  requires: [07-01]
  provides: [v2-graph-run, resolve-fields-integration, choose-type-fill-routing]
  affects: [07-03, 07-04]
tech-stack:
  patterns: [field-resolution-loop, v2-lm-routing, dep-cache, iteration-guard]
key-files:
  created: []
  modified: [bae/graph.py, tests/test_dep_injection.py]
decisions:
  - id: keep-get-base-type
    summary: "Keep _get_base_type in graph.py (used by compiler.py, not incant-specific)"
  - id: recall-skips-dep-fields
    summary: "recall_from_trace skips Dep-annotated fields by design; tests use bridge nodes"
  - id: max-iters-zero-infinite
    summary: "max_iters=0 means infinite (falsy check skips guard)"
  - id: terminal-in-trace
    summary: "Terminal nodes appended to trace before loop exits via current=None"
metrics:
  duration: ~5min
  completed: 2026-02-08
---

# Phase 7 Plan 02: v2 Graph.run() Core Execution Loop Summary

**v2 execution loop: resolve_fields -> setattr -> routing via choose_type/fill, incant removed**

## What Was Done

### Task 1: TDD - v2 Graph.run() core execution loop

**RED:** Replaced all 11 v1 incant-based tests in test_dep_injection.py with 8 v2 integration tests covering:
1. Dep(callable) field resolution on start node
2. Multi-node with deps (Dep) and recalls (Recall) via bridge node pattern
3. Custom __call__ reading resolved dep fields from self
4. Dep failure raises DepError with __cause__ and trace attribute
5. Iteration guard: max_iters=5 raises BaeError, max_iters=0 allows infinite
6. Terminal node included in trace (last element)

MockV2LM implements choose_type/fill (v2 API), with make/decide stubs raising NotImplementedError.

**GREEN:** Rewrote bae/graph.py:
- Removed incant import and 3 incant helper functions: `_is_dep_annotated`, `_create_dep_hook_factory`, `_capture_bind_fields`
- Kept `_get_base_type` (used by compiler.py, not incant-specific)
- Added imports: `resolve_fields` from resolver, `_wants_lm` from node, `DepError`/`RecallError` from exceptions
- Added logging, `_build_context`, `_build_instruction` helpers
- Rewrote `Graph.run()` with v2 execution loop:
  1. `resolve_fields()` on each node
  2. `object.__setattr__` to set resolved values
  3. Append to trace after resolution, before __call__
  4. Route via `_get_routing_strategy`: terminal/custom/ellipsis(make/decide)
  5. Ellipsis nodes route via `lm.fill()` and `lm.choose_type()`
  6. Custom __call__ checks `_wants_lm` for LM injection
- Changed signature: `max_steps` -> `max_iters` (default 10), removed `**kwargs`
- Terminal nodes included in trace

**REFACTOR:** No refactoring needed.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Keep `_get_base_type` in graph.py | compiler.py imports it; it's a type utility, not incant-specific |
| Bridge node pattern for Recall tests | `recall_from_trace` skips Dep-annotated fields by design (Phase 5 decision); tests use plain-field bridge nodes |
| `max_iters=0` means infinite | Falsy check `if max_iters` is False when 0, skipping the guard |
| Fix `node.model_fields` -> `node.__class__.model_fields` | Pydantic V2.11 deprecated instance access |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] compiler.py imports _get_base_type from graph.py**

- **Found during:** GREEN phase, removing incant helpers
- **Issue:** Plan said to remove `_get_base_type`, but `bae/compiler.py` line 14 imports it from `bae.graph`
- **Fix:** Kept `_get_base_type` in graph.py since it's a general type utility, not incant-specific
- **Files modified:** bae/graph.py
- **Commit:** ad4576d

**2. [Rule 1 - Bug] recall_from_trace skips Dep fields, test design conflict**

- **Found during:** GREEN phase, running tests
- **Issue:** Plan specified `GatherInfo` with `Dep(fetch_info)` field, and `Analyze` with `Recall()` on same type. But `recall_from_trace` (Phase 5) intentionally skips Dep-annotated fields.
- **Fix:** Restructured test to use bridge node pattern: GatherInfo -> InfoBridge (plain field) -> Analyze (recalls from bridge)
- **Files modified:** tests/test_dep_injection.py
- **Commit:** ad4576d

**3. [Rule 1 - Bug] Pydantic deprecation on instance model_fields access**

- **Found during:** GREEN phase, running tests
- **Issue:** `_build_context` used `node.model_fields` which is deprecated in Pydantic V2.11
- **Fix:** Changed to `node.__class__.model_fields`
- **Files modified:** bae/graph.py
- **Commit:** ad4576d

## Expected Breakage

13 existing v1 tests fail because they use:
- `lm.make()/lm.decide()` (v1 API) -- now replaced by `lm.choose_type()/lm.fill()`
- `max_steps` parameter -- renamed to `max_iters`
- `**kwargs` for external dep injection -- removed

These tests are in: test_graph.py, test_auto_routing.py, test_integration.py, test_integration_dspy.py.
Plan 03 will update these v1 tests to v2 patterns.

## Commits

| Hash | Message |
|------|---------|
| aba7219 | test(07-02): add v2 integration tests for Graph.run() field resolution |
| ad4576d | feat(07-02): rewrite Graph.run() with v2 field resolution and LM routing |

## Test Results

- 8 v2 integration tests: all passing
- 290 other tests: passing
- 13 v1 tests: expected failures (Plan 03 scope)

## Next Phase Readiness

Plan 03 (test migration) is ready to proceed. All v1 test failures are well-understood:
- MockLM needs v2 API (choose_type/fill)
- Test call sites need max_iters instead of max_steps
- Tests using **kwargs need v2 dep patterns (Dep on fields)
