---
phase: 02-dspy-integration
plan: 01
subsystem: core-types
tags: [result, exceptions, markers, validation]
dependency-graph:
  requires: [01-signature-generation]
  provides: [GraphResult, BaeError hierarchy, Bind marker, type-unique validation]
  affects: [02-02, 02-03, 02-04, 02-05]
tech-stack:
  added: []
  patterns: [dataclass marker, cause chaining, graph validation]
key-files:
  created:
    - bae/result.py
    - bae/exceptions.py
    - tests/test_result.py
    - tests/test_bind_validation.py
  modified:
    - bae/markers.py
    - bae/graph.py
decisions:
  - name: Bind has no description field
    rationale: Pure marker for type matching, description comes from Dep on consumer side
    impact: Simpler API, consistent with DSPy injection pattern
metrics:
  duration: 6 min
  completed: 2026-02-05
---

# Phase 02 Plan 01: Foundation Types Summary

**One-liner:** GraphResult dataclass + BaeError hierarchy with cause chaining + Bind marker with Graph type-unique validation

## What Was Built

### Feature 1: GraphResult and Exception Hierarchy

Created `bae/result.py` with GraphResult dataclass:
- `node: Node | None` - final node after execution, or None if terminated
- `trace: list[Node]` - flat list of nodes in execution order

Created `bae/exceptions.py` with exception hierarchy:
- `BaeError` - base exception with cause chaining via `__cause__`
- `BaeParseError` - for validation/parse failures
- `BaeLMError` - for API failures (timeout, rate limit, network)

### Feature 2: Bind Marker and Type-Unique Validation

Extended `bae/markers.py` with Bind:
- Frozen dataclass marker (like Context/Dep)
- Used in `Annotated[Type, Bind()]` for node fields
- Signals value should be available for downstream Dep injection

Extended `bae/graph.py` with Bind validation:
- `_validate_bind_uniqueness()` scans all nodes for Bind-annotated fields
- Collects Bind types -> node.field mappings
- Returns error listing conflicting nodes if duplicate types found

## Key Code

```python
# bae/result.py
@dataclass
class GraphResult:
    node: Node | None
    trace: list[Node]

# bae/exceptions.py
class BaeError(Exception):
    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause

# bae/markers.py
@dataclass(frozen=True)
class Bind:
    pass

# bae/graph.py validation
def _validate_bind_uniqueness(self) -> list[str]:
    bind_types: dict[type, list[tuple[type[Node], str]]] = {}
    # Collect and check for duplicates...
```

## Test Coverage

- `tests/test_result.py` (115 lines)
  - GraphResult construction and attributes
  - Exception cause chaining
  - Exception inheritance and catchability

- `tests/test_bind_validation.py` (185 lines)
  - Bind marker properties (frozen, equality)
  - Graph validation for single/duplicate/multiple Bind types
  - Error message content verification

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 5531a54 | test | Add failing tests for GraphResult and exception hierarchy |
| 62d196f | feat | Implement GraphResult and exception hierarchy |
| e56c114 | test | Add failing tests for Bind marker and type-unique validation |
| d8b8274 | feat | Implement Bind marker and type-unique validation |

## Deviations from Plan

None - plan executed exactly as written.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Bind has no description field | Pure marker for type matching; description comes from Dep on consumer side |
| Test mock types use Pydantic BaseModel | Needed for Pydantic compatibility in Node subclasses |

## Next Phase Readiness

**Blockers:** None

**Ready for:**
- 02-02: Graph.run() returning GraphResult with execution trace
- 02-03: DSPyBackend using BaeError hierarchy (already implemented)
- 02-04: Dep injection using Bind values
