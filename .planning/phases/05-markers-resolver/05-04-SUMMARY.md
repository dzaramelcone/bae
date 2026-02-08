---
phase: 05-markers-resolver
plan: 04
subsystem: core
tags: [resolver, dep-resolution, caching, resolve-fields, orchestrator, exports]

# Dependency graph
requires:
  - phase: 05-02
    provides: "build_dep_dag() and validate_node_deps() for DAG construction"
  - phase: 05-03
    provides: "recall_from_trace() for backward trace search by type"
provides:
  - "resolve_dep() function for recursive dep resolution with per-run caching"
  - "resolve_fields() orchestrator that resolves all Dep and Recall fields"
  - "Public API exports: Recall, RecallError, classify_fields, resolve_fields from bae package"
affects: [06-graph-engine, 07-graph-run-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Recursive dep resolution with cache short-circuit for transitive deps"
    - "Per-run cache dict keyed by callable identity (shared across resolve_fields calls)"
    - "Field declaration order preserved via dict insertion order from get_type_hints"
    - "Raw exception propagation from dep functions (no BaeError wrapping)"

# File tracking
key-files:
  created: []
  modified:
    - bae/resolver.py
    - bae/__init__.py
    - tests/test_resolver.py

# Decisions
decisions:
  - id: "resolve-dep-cache-by-callable"
    decision: "Cache keyed by callable identity (fn object), not by function name"
    reason: "Two different functions with the same name are different deps; identity is unambiguous"
  - id: "raw-exception-propagation"
    decision: "Dep function exceptions propagate raw without BaeError wrapping"
    reason: "Callers need to catch specific exceptions (ConnectionError, etc.); wrapping hides intent"
  - id: "resolve-fields-skips-plain"
    decision: "resolve_fields returns only Dep and Recall field values, not plain fields"
    reason: "Plain fields are LLM-filled or user-supplied; resolver only handles infrastructure fields"

# Metrics
metrics:
  duration: "~5min"
  completed: "2026-02-08"
  tests-added: 12
  tests-total: 44
---

# Phase 5 Plan 4: Dep Resolution & resolve_fields Orchestrator Summary

Recursive dep resolution with per-run caching and resolve_fields orchestrator combining dep DAG resolution and trace recall into a single entry point for Phase 7 graph.run() integration.

## What Was Done

### Task 1: RED - Failing tests (cb99f50)

Added 12 tests across two classes:

**TestResolveDep (5 tests):**
- Leaf dep resolution (no transitive deps)
- Chained dep resolution (transitive kwargs injection)
- Cache deduplication (same dep called once even through multiple paths)
- Cache keyed by identity (pre-populated cache entries used)
- Raw exception propagation (ConnectionError not wrapped)

**TestResolveFields (7 tests):**
- Single dep field resolution
- Single recall field resolution from trace
- Mixed dep + recall fields (plain fields excluded)
- Declaration order preservation in returned dict keys
- Cross-field caching (shared transitive dep called once)
- Empty dict for plain-only nodes
- Cache persistence across separate resolve_fields calls

### Task 2: GREEN - Implementation (7e2903d)

**`resolve_dep(fn, cache)`:** Recursive function that checks cache first, then inspects `fn`'s type hints for Dep-annotated parameters, recursively resolves those, calls `fn(**kwargs)`, stores result in cache, returns it. Exceptions propagate raw.

**`resolve_fields(node_cls, trace, dep_cache)`:** Iterates `get_type_hints(node_cls)` in declaration order. For Dep fields, delegates to `resolve_dep`. For Recall fields, delegates to `recall_from_trace`. Plain fields skipped. Returns `{field_name: resolved_value}` dict.

**Package exports:** Added `Recall`, `RecallError`, `classify_fields`, `resolve_fields` to `bae/__init__.py` imports and `__all__`.

## Deviations from Plan

None -- plan executed exactly as written.

## Test Results

- 44 resolver tests pass (32 existing + 12 new)
- 234 total tests pass across full suite, 5 skipped (PydanticAI API key tests)
- Zero regressions

## Phase 5 Completion Status

This is the capstone plan of Phase 5 (Markers & Resolver). All 4 plans complete:
- 05-01: Dep/Recall markers, RecallError, classify_fields
- 05-02: build_dep_dag, validate_node_deps (DAG construction + cycle detection)
- 05-03: recall_from_trace (backward trace search with MRO matching)
- 05-04: resolve_dep, resolve_fields (this plan)

**Phase 5 delivers to Phase 7:** `resolve_fields(node_cls, trace, dep_cache)` is the single entry point for Graph.run() to resolve all non-LLM fields before node execution.

## Next Phase Readiness

Phase 6 (Graph Engine v2) can proceed. All resolver infrastructure is in place:
- `classify_fields()` for field introspection
- `build_dep_dag()` + `validate_node_deps()` for build-time validation
- `recall_from_trace()` for trace-based field population
- `resolve_dep()` + `resolve_fields()` for runtime field resolution
