---
phase: 05-markers-resolver
verified: 2026-02-08T00:37:49Z
status: passed
score: 5/5 must-haves verified
---

# Phase 5: Markers & Resolver Verification Report

**Phase Goal:** Field-level dependency resolution and trace recall work correctly in isolation
**Verified:** 2026-02-08T00:37:49Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `Annotated[T, Dep(fn)]` field causes the resolver to call `fn` and return the result for injection | ✓ VERIFIED | `resolve_dep()` recursively resolves deps, calls fn with kwargs, caches result. Tests: `test_resolve_leaf_dep`, `test_resolve_chained_dep` |
| 2 | Dep functions whose parameters are themselves dep-typed resolve bottom-up via topological sort (chaining works) | ✓ VERIFIED | `build_dep_dag()` builds TopologicalSorter, `resolve_dep()` recursively resolves transitive deps. Tests: `test_chained_deps`, `test_deep_chain`, `test_shared_transitive_dep` |
| 3 | Circular dep chains raise a clear error naming the cycle at graph build time | ✓ VERIFIED | `validate_node_deps()` catches `graphlib.CycleError`, extracts cycle, formats error. Tests: `test_circular_deps_detected` |
| 4 | Recall() searches a trace list backward and returns the most recent node field matching the target type | ✓ VERIFIED | `recall_from_trace()` walks `reversed(trace)`, matches via `issubclass()`, skips Dep/Recall fields. Tests: `test_recall_finds_matching_type`, `test_recall_most_recent_wins`, `test_recall_searches_backward` |
| 5 | Recall on a start node raises an error at graph build time (no trace exists yet) | ✓ VERIFIED | `validate_node_deps()` checks `is_start` flag, adds error for Recall fields. Tests: `test_recall_on_start_node_error`, `test_recall_on_non_start_valid` |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bae/markers.py` | Dep and Recall marker classes | ✓ VERIFIED | 90 lines. Dep(fn) stores callable, Recall() is frozen dataclass. Both frozen, proper docstrings. |
| `bae/exceptions.py` | RecallError exception | ✓ VERIFIED | 42 lines. RecallError inherits from BaeError, proper message handling. |
| `bae/resolver.py` | classify_fields, recall_from_trace, build_dep_dag, validate_node_deps, resolve_dep, resolve_fields | ✓ VERIFIED | 302 lines. All 6 functions present, substantive implementations with proper type hints and docstrings. |
| `bae/__init__.py` | Public API exports | ✓ VERIFIED | Exports Recall, RecallError, classify_fields, resolve_fields in __all__. |
| `tests/test_resolver.py` | Comprehensive test coverage | ✓ VERIFIED | 590 lines, 44 tests covering all functions and edge cases. 100% pass rate. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `resolve_fields()` | `resolve_dep()` | Direct function call for Dep fields | ✓ WIRED | Line 295: `resolved[field_name] = resolve_dep(m.fn, dep_cache)` |
| `resolve_fields()` | `recall_from_trace()` | Direct function call for Recall fields | ✓ WIRED | Line 298: `resolved[field_name] = recall_from_trace(trace, base_type)` |
| `resolve_dep()` | `resolve_dep()` (recursive) | Transitive dep resolution | ✓ WIRED | Line 256: `kwargs[param_name] = resolve_dep(m.fn, cache)` |
| `validate_node_deps()` | `build_dep_dag()` | Cycle detection | ✓ WIRED | Line 217: `dag = build_dep_dag(node_cls)` |
| `build_dep_dag()` | `graphlib.TopologicalSorter` | DAG construction | ✓ WIRED | Line 117: `ts = graphlib.TopologicalSorter()`, lines 126-140 add edges |
| `recall_from_trace()` | `RecallError` | Error on no match | ✓ WIRED | Lines 94-96: raises RecallError with descriptive message |
| `bae/__init__.py` | `bae.resolver` | Package exports | ✓ WIRED | Line 18: imports classify_fields, resolve_fields; line 33-34: in __all__ |
| `tests/test_resolver.py` | All resolver functions | Test imports | ✓ WIRED | Lines 14-21: imports all functions, used in 44 tests |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| DEP2-01: Dep(callable) resolves fields | ✓ SATISFIED | None — `resolve_dep()` calls fn and injects result |
| DEP2-02: Dep chaining resolves recursively | ✓ SATISFIED | None — recursive `resolve_dep()` with topological sort via DAG |
| DEP2-03: Circular dep chains detected at build time | ✓ SATISFIED | None — `validate_node_deps()` catches CycleError, formats cycle |
| DEP2-04: Per-run dep caching | ✓ SATISFIED | None — cache keyed by callable identity, shared across resolve_fields calls |
| DEP2-05: Clear error when dep callable fails | ✓ SATISFIED | None — exceptions propagate raw (line 259: `result = fn(**kwargs)`) |
| RCL-01: Recall searches trace backward | ✓ SATISFIED | None — `recall_from_trace()` uses `reversed(trace)`, MRO matching |
| RCL-02: Clear error when Recall target not found | ✓ SATISFIED | None — RecallError raised with target type name |
| RCL-03: Recall on start node raises error at build time | ✓ SATISFIED | None — `validate_node_deps()` checks `is_start` flag |

### Anti-Patterns Found

None. All modified files contain substantive implementations with proper error handling, type hints, and documentation. No TODO/FIXME comments, no placeholder returns, no stub patterns.

### Human Verification Required

None. All success criteria are programmatically verifiable through:
- Unit tests (44 tests, 100% pass rate)
- Static analysis (type hints, imports, exports)
- Code inspection (implementation substantive, wired correctly)

---

## Verification Details

### Truth 1: Dep(fn) Resolution

**What must be TRUE:** When a field is annotated `Annotated[T, Dep(fn)]`, the resolver must call `fn()` and inject the returned value into the field.

**Artifacts supporting this truth:**
- `bae/markers.py`: Dep marker with `fn: Callable | None` field
- `bae/resolver.py`: `resolve_dep(fn, cache)` function
- `bae/resolver.py`: `resolve_fields()` orchestrator

**Verification:**
1. **Exists:** All files present ✓
2. **Substantive:**
   - `Dep` marker stores callable (line 48: `fn: Callable | None = None`)
   - `resolve_dep()` extracts fn from Dep metadata, calls it (line 259: `result = fn(**kwargs)`)
   - `resolve_fields()` delegates to resolve_dep for Dep fields (line 295)
3. **Wired:**
   - `resolve_fields()` calls `resolve_dep()` ✓
   - Result stored in cache and returned ✓
   - Tests verify end-to-end: `test_resolve_leaf_dep`, `test_resolve_dep_field` ✓

**Test Evidence:**
- `test_resolve_leaf_dep`: Calls `resolve_dep(get_location, cache)`, asserts result == "NYC" and cache contains entry
- `test_resolve_dep_field`: Resolves field via `resolve_fields()`, asserts field value matches fn return

**Status:** ✓ VERIFIED

---

### Truth 2: Dep Chaining (Topological Sort)

**What must be TRUE:** When a dep function has parameters that are themselves Dep-annotated, resolution must happen bottom-up (leaf deps first, then deps that depend on them).

**Artifacts supporting this truth:**
- `bae/resolver.py`: `build_dep_dag()` constructs TopologicalSorter
- `bae/resolver.py`: `resolve_dep()` recursively resolves transitive deps

**Verification:**
1. **Exists:** All functions present ✓
2. **Substantive:**
   - `build_dep_dag()` walks node fields and transitive params, builds DAG (lines 104-154)
   - `resolve_dep()` recursively resolves dep params before calling fn (lines 250-257)
   - Cache prevents duplicate resolution (line 244: early return if in cache)
3. **Wired:**
   - `build_dep_dag()` uses `graphlib.TopologicalSorter` ✓
   - `resolve_dep()` calls itself recursively for transitive deps ✓
   - Tests verify correct ordering ✓

**Test Evidence:**
- `test_chained_deps`: `get_weather` depends on `get_location`, verifies location resolved first
- `test_deep_chain`: 3-level chain (forecast -> weather -> location), verifies order
- `test_shared_transitive_dep`: Multiple fields share a leaf dep, verifies leaf appears once in DAG
- `test_cache_prevents_duplicate_calls`: Shared dep called only once via cache

**Status:** ✓ VERIFIED

---

### Truth 3: Circular Dependency Detection

**What must be TRUE:** When deps form a cycle (A depends on B, B depends on A), the system must raise a clear error at graph build time naming the cycle.

**Artifacts supporting this truth:**
- `bae/resolver.py`: `build_dep_dag()` constructs DAG
- `bae/resolver.py`: `validate_node_deps()` catches CycleError

**Verification:**
1. **Exists:** Functions present ✓
2. **Substantive:**
   - `build_dep_dag()` returns TopologicalSorter which detects cycles on iteration
   - `validate_node_deps()` calls `dag.static_order()` to trigger cycle detection (line 218)
   - Catches `graphlib.CycleError`, extracts cycle, formats human-readable error (lines 219-222)
3. **Wired:**
   - `validate_node_deps()` calls `build_dep_dag()` ✓
   - Error appended to errors list with cycle names ✓
   - Tests verify cycle detection ✓

**Test Evidence:**
- `test_circular_deps_detected`: Creates circular_a -> circular_b -> circular_a, verifies CycleError raised
- Error message includes callable names via `_callable_name()` helper

**Status:** ✓ VERIFIED

---

### Truth 4: Recall Backward Trace Search

**What must be TRUE:** `Recall()` annotation must search the execution trace backward (most recent first) and return the most recent node field matching the target type via MRO.

**Artifacts supporting this truth:**
- `bae/resolver.py`: `recall_from_trace(trace, target_type)`

**Verification:**
1. **Exists:** Function present ✓
2. **Substantive:**
   - Walks `reversed(trace)` so most recent node wins (line 73)
   - Uses `issubclass(base_type, target_type)` for MRO matching (line 89)
   - Skips Dep/Recall annotated fields (lines 85-86)
   - Raises RecallError if no match found (lines 94-96)
3. **Wired:**
   - `resolve_fields()` calls `recall_from_trace()` for Recall fields (line 298) ✓
   - RecallError imported from exceptions (line 13) ✓
   - Tests verify backward search and MRO ✓

**Test Evidence:**
- `test_recall_finds_matching_type`: Single node, finds matching str field
- `test_recall_most_recent_wins`: Two nodes with str fields, returns most recent
- `test_recall_searches_backward`: Multiple nodes, verifies backward search order
- `test_recall_subclass_matching`: Field typed as Animal matches when searching for Animal (MRO)
- `test_recall_skips_dep_fields`: Dep-annotated fields excluded from search
- `test_recall_skips_recall_fields`: Recall-annotated fields excluded from search

**Status:** ✓ VERIFIED

---

### Truth 5: Recall on Start Node Error

**What must be TRUE:** If a start node (no trace to search) has a Recall-annotated field, validation must raise a clear error at graph build time.

**Artifacts supporting this truth:**
- `bae/resolver.py`: `validate_node_deps(node_cls, *, is_start: bool)`

**Verification:**
1. **Exists:** Function present ✓
2. **Substantive:**
   - Takes `is_start` parameter (line 157)
   - Checks for Recall on start nodes (lines 187-191)
   - Appends descriptive error naming the field and node (lines 188-191)
3. **Wired:**
   - Error appended to errors list ✓
   - Tests verify behavior for both start and non-start nodes ✓

**Test Evidence:**
- `test_recall_on_start_node_error`: Node with Recall field, `is_start=True`, verifies error raised
- `test_recall_on_non_start_valid`: Same node, `is_start=False`, verifies no error

**Status:** ✓ VERIFIED

---

## Test Results

**Resolver tests:** 44/44 passed (0 skipped, 0 failed)
**Full suite:** 234/234 passed (5 skipped — PydanticAI API key tests unrelated to this phase)

**Regression check:** No regressions. All v1 tests continue to pass.

**Test coverage by function:**
- `Dep` marker: 3 tests
- `Recall` marker: 2 tests
- `RecallError`: 2 tests
- `classify_fields()`: 5 tests
- `recall_from_trace()`: 8 tests
- `build_dep_dag()`: 6 tests
- `validate_node_deps()`: 6 tests
- `resolve_dep()`: 5 tests
- `resolve_fields()`: 7 tests

**Total:** 44 tests covering all Phase 5 deliverables

---

## Phase Completion Analysis

### Phase Goal Achievement

**Goal:** Field-level dependency resolution and trace recall work correctly in isolation

**Achievement:** ✓ COMPLETE

All 5 success criteria verified through:
1. Implementation inspection (substantive, wired, no stubs)
2. Unit test coverage (44 tests, 100% pass)
3. Integration verification (exports wired, imports work)

### Requirements Satisfaction

All 8 Phase 5 requirements satisfied:
- DEP2-01 through DEP2-05 (dependency resolution)
- RCL-01 through RCL-03 (trace recall)

### Deliverables to Next Phase

**Phase 6 (Node & LM Protocol) receives:**
- `classify_fields(node_cls)` — field introspection
- `validate_node_deps(node_cls, is_start)` — build-time validation
- `resolve_fields(node_cls, trace, dep_cache)` — runtime field resolution

**Phase 7 (Integration) receives:**
- `resolve_dep(fn, cache)` — dep resolution primitive
- `recall_from_trace(trace, target_type)` — trace search primitive
- `build_dep_dag(node_cls)` — DAG construction for topological sort

All primitives tested in isolation and ready for integration.

---

_Verified: 2026-02-08T00:37:49Z_
_Verifier: Claude (gsd-verifier)_
_Test suite: 234 passed, 5 skipped_
_Phase 5 status: COMPLETE_
