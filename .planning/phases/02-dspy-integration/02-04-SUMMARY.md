---
phase: 02
plan: 04
subsystem: graph-execution
tags: [incant, dependency-injection, bind, dep, tdd]
dependency-graph:
  requires: [02-01, 02-02]
  provides: [dep-injection]
  affects: [02-05, 03-*]
tech-stack:
  added: [incant]
  patterns: [type-based-injection, bind-capture, accumulating-deps]
key-files:
  created:
    - tests/test_dep_injection.py
  modified:
    - bae/graph.py
    - bae/node.py
decisions:
  - id: hook-factory-over-register-by-type
    choice: Use incant hook_factory for Dep injection instead of register_by_type
    rationale: Hook factory allows dynamic lookup at compose time, supports accumulating deps
  - id: bind-fields-optional
    choice: Bind-annotated fields should be `X | None = None`
    rationale: Fields set during __call__ execution, not at instantiation
  - id: base-type-extraction
    choice: Extract non-None type from X | None for registry lookup
    rationale: Dep[X] should match Bind[X | None] by the underlying X type
metrics:
  duration: 8 min
  completed: 2026-02-05
---

# Phase 2 Plan 4: Dep Injection Summary

**One-liner:** Incant-based dependency injection with external deps from run() kwargs and Bind field capture for downstream Dep params

## What Was Built

### Dependency Injection System (bae/graph.py)

Core injection mechanics using incant library:

1. **External Dependencies via run() kwargs**
   - `graph.run(node, db=conn, cache=redis)` registers deps by type
   - Creates fresh Incanter per run with dep registry
   - Available to any node's Dep-annotated __call__ params

2. **Bind Field Capture**
   - After each node executes, scans for Bind-annotated fields
   - Captures field values into dep registry by base type
   - Handles `X | None` unions - extracts X for registry key

3. **Dep Param Injection**
   - Uses incant hook_factory to match Dep params to registry
   - Injects at compose_and_call time for custom __call__ logic
   - Missing deps raise BaeError with clear type name

4. **Helper Functions**
   - `_is_dep_annotated(param)` - checks for Dep marker
   - `_get_base_type(hint)` - extracts non-None type from unions
   - `_create_dep_hook_factory(registry)` - returns hook for incant
   - `_capture_bind_fields(node, registry)` - captures Bind values

### Node Configuration (bae/node.py)

- Added `arbitrary_types_allowed=True` to Node base class
- Allows non-Pydantic types as Dep/Bind field types

### Test Coverage (tests/test_dep_injection.py)

11 tests covering:
- Single external dep injection
- Multiple external deps
- Missing external dep error
- Bind field capture after execution
- Bind value passed to downstream Dep
- Dep injection from registry
- No deps needed case
- Deps accumulate across nodes
- External and bound deps coexist
- Missing external dep raises BaeError
- Missing bound dep raises BaeError

## Key Implementation Details

```python
# Create incanter with dep injection hook
incanter = Incanter()
incanter.register_hook_factory(
    _is_dep_annotated,
    _create_dep_hook_factory(dep_registry)
)

# Call node with injection
next_node = incanter.compose_and_call(current.__call__, lm=lm)

# Capture Bind fields after execution
_capture_bind_fields(current, dep_registry)
```

```python
# Hook factory for Dep params
def dep_hook_factory(param: inspect.Parameter):
    base_type = _get_base_type(param.annotation)
    if base_type not in dep_registry:
        raise TypeError(f"Missing dependency: {base_type.__name__}")
    def factory():
        return dep_registry[base_type]
    return factory
```

## Deviations from Plan

### [Rule 1 - Bug] Base type extraction for optional Binds

**Found during:** Implementation
**Issue:** Bind fields typed as `X | None` were registered under union type, not X
**Fix:** `_get_base_type()` now extracts non-None type from unions
**Files modified:** bae/graph.py
**Commit:** 190a410

## Verification Results

```
pytest tests/test_dep_injection.py -v
11 passed

pytest tests/ -v
105 passed, 5 skipped (integration tests without API key)
```

## Next Phase Readiness

Dep injection is ready for:
- Integration with DSPyBackend for Dep field values in signatures
- Graph validation to check Dep/Bind type compatibility
- Real graph execution with external services

Dependencies satisfied:
- Uses Bind/Dep markers from 02-01
- Integrates with Graph.run() from 02-02
