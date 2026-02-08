# Phase 5: Markers & Resolver - Research

**Researched:** 2026-02-07
**Domain:** Python type annotation introspection, dependency resolution (DAG), Pydantic model construction
**Confidence:** HIGH

## Summary

Phase 5 builds the resolver that populates Node fields from two non-LLM sources: dep functions (`Dep(fn)`) and trace recall (`Recall()`). The v2 `Dep` marker changes from a description-only annotation to a callable-bearing one. The resolver introspects field annotations at graph construction time to build a dependency DAG, then resolves fields at runtime in topological order with per-run caching.

All core technologies are Python stdlib (`graphlib`, `typing`, `inspect`) plus Pydantic's `model_construct()`. No new dependencies needed. The main complexity is correct annotation introspection across callables (functions, lambdas, bound methods, `__call__` classes) and the interplay between Pydantic's required fields and deferred population via `model_construct()`.

**Primary recommendation:** Use `graphlib.TopologicalSorter` with callables as graph nodes, `typing.get_type_hints(fn, include_extras=True)` for annotation extraction, and `model_construct()` for deferred field population. The resolver is a standalone module (`bae/resolver.py`) that is pure function-based -- no class needed for v5 scope.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `graphlib` (stdlib) | Python 3.14 | Topological sort of dep DAG + cycle detection | Locked decision. `TopologicalSorter` handles both ordering and `CycleError` with cycle-naming. |
| `typing` (stdlib) | Python 3.14 | `get_type_hints()`, `get_args()`, `get_origin()` for annotation introspection | Already used throughout codebase. `include_extras=True` preserves `Annotated` metadata. |
| `inspect` (stdlib) | Python 3.14 | `isfunction()`, `ismethod()` for callable type detection | Already used in `node.py`. Needed to distinguish callable types for `get_type_hints` dispatch. |
| `pydantic` | >=2.0 | `BaseModel.model_construct()` for bypassing validation on deferred fields | Locked decision from STATE.md. Required because Dep/Recall fields are Pydantic-required but populated after construction. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` (stdlib) | Python 3.14 | Frozen dataclasses for marker definitions | Already used for v1 markers. Continues for v2 Dep/Recall markers. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `graphlib.TopologicalSorter` | Manual DFS-based topo sort | Stdlib handles cycle detection with named cycles out of the box. No reason to hand-roll. |
| `model_construct()` | Regular `__init__` with `Optional` defaults | Would require all Dep/Recall fields to have defaults, polluting the type model. `model_construct()` preserves clean required-field semantics. |

## Architecture Patterns

### Recommended Project Structure

```
bae/
├── markers.py       # v2 Dep(callable), Recall() markers (modify existing)
├── resolver.py      # NEW: resolve_fields() + dep DAG builder + trace search
├── exceptions.py    # Add RecallError (modify existing)
├── node.py          # Unchanged for Phase 5
├── graph.py         # Unchanged for Phase 5 (integration in Phase 7)
```

### Pattern 1: Annotation-Driven Field Classification

**What:** Classify each Node field by its annotation marker to determine its resolution source.
**When to use:** At graph construction time (for validation) and at resolve time (for dispatch).

```python
# Source: Verified with Python 3.14 typing module
from typing import Annotated, get_type_hints, get_args, get_origin

def classify_fields(node_cls: type) -> dict[str, str]:
    """Classify fields as 'dep', 'recall', or 'plain'."""
    hints = get_type_hints(node_cls, include_extras=True)
    result = {}
    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            for m in args[1:]:
                if isinstance(m, Dep):
                    result[name] = 'dep'
                    break
                elif isinstance(m, Recall):
                    result[name] = 'recall'
                    break
            else:
                result[name] = 'plain'
        else:
            result[name] = 'plain'
    return result
```

**Confidence:** HIGH -- verified with Python 3.14 interactive testing.

### Pattern 2: Dep DAG Construction via Annotation Walking

**What:** Build a DAG of dep function dependencies by walking `Annotated[T, Dep(fn)]` annotations on dep function parameters.
**When to use:** At graph construction time, to detect cycles and validate return types.

```python
# Source: Verified with Python 3.14 + graphlib
import graphlib
from typing import get_type_hints, get_args, get_origin, Annotated

def build_dep_dag(node_cls: type) -> graphlib.TopologicalSorter:
    """Walk all Dep-annotated fields and their transitive deps to build a DAG."""
    ts = graphlib.TopologicalSorter()
    visited = set()

    def walk(fn):
        if fn in visited:
            return
        visited.add(fn)
        hints = get_type_hints(fn, include_extras=True)
        for name, hint in hints.items():
            if name == 'return':
                continue
            if get_origin(hint) is Annotated:
                args = get_args(hint)
                for m in args[1:]:
                    if isinstance(m, Dep):
                        ts.add(fn, m.fn)  # fn depends on m.fn
                        walk(m.fn)
                        break
        # Ensure leaf functions are in the DAG
        ts.add(fn)

    # Start from node's Dep-annotated fields
    hints = get_type_hints(node_cls, include_extras=True)
    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            for m in args[1:]:
                if isinstance(m, Dep):
                    walk(m.fn)
                    break

    return ts
```

**Confidence:** HIGH -- `TopologicalSorter.add(node, *predecessors)` with callable keys verified to work.

### Pattern 3: Per-Run Dep Cache Keyed by Callable Identity

**What:** Cache dep function results by function identity (`id(fn)` or function-as-dict-key) within a single resolver run.
**When to use:** During resolver execution, to avoid calling the same dep function twice.

```python
# Source: Verified with Python 3.14
# Functions are hashable and can be used as dict keys directly.
cache: dict[callable, object] = {}

def resolve_dep(fn, cache):
    if fn in cache:
        return cache[fn]
    # ... resolve fn's own deps first ...
    result = fn(**resolved_args)
    cache[fn] = result
    return result
```

**Confidence:** HIGH -- verified functions are hashable and support `is`/`==` identity.

**Important note on callable identity:** Bound methods create new wrapper objects each call (`obj.method is obj.method` is `False`). However, the decision doc says "keyed by function identity" and dep functions are standalone (no access to node instance). So the typical case is plain functions, which have stable identity. Classes with `__call__` used as dep functions would be keyed by the class instance, which is stable.

### Pattern 4: Trace Search for Recall

**What:** Walk the execution trace backward, checking LLM-filled fields on each node for type match.
**When to use:** At field resolve time when a field has `Recall()` annotation.

```python
# Source: Verified with Python 3.14
def recall_from_trace(trace: list, target_type: type) -> object:
    """Search trace backward for most recent LLM-filled field matching target_type."""
    for node in reversed(trace):
        hints = get_type_hints(node.__class__, include_extras=True)
        for field_name, hint in hints.items():
            # Determine base type and whether it's dep/recall annotated
            if get_origin(hint) is Annotated:
                args = get_args(hint)
                base_type = args[0]
                # Skip dep-annotated and recall-annotated fields
                is_infra = any(isinstance(m, (Dep, Recall)) for m in args[1:])
                if is_infra:
                    continue
                field_type = base_type
            else:
                field_type = hint

            # MRO-based type matching
            if isinstance(field_type, type) and issubclass(field_type, target_type):
                value = getattr(node, field_name, None)
                if value is not None:
                    return value
    raise RecallError(f"No field matching {target_type.__name__} found in trace")
```

**Confidence:** HIGH -- `issubclass()` MRO matching verified. Trace structure (`list[Node]`) already exists in `GraphResult.trace`.

### Pattern 5: model_construct() for Deferred Field Population

**What:** Use Pydantic's `model_construct()` to create node instances where Dep/Recall fields are populated after construction.
**When to use:** When the resolver creates a successor node that has fields requiring resolution.

```python
# Source: Verified with Pydantic 2.12+ model_construct()
# Required fields without defaults: model_construct() skips them (no AttributeError on construction)
# They can be set via attribute assignment after construction
node = TargetNode.model_construct(**caller_provided_fields)
# node.dep_field -> AttributeError (not yet set)
node.dep_field = resolved_value  # Set after resolution
# node.dep_field -> resolved_value
```

**Critical behavior verified:**
- `model_construct()` applies defaults for fields that have them
- Required fields without defaults are simply absent (no error on construction, `AttributeError` on access)
- Fields can be set via normal attribute assignment after `model_construct()`
- `_fields_set` tracks which fields were explicitly provided

**Confidence:** HIGH -- verified with Pydantic 2.12 on Python 3.14.

### Anti-Patterns to Avoid

- **Resolving deps at runtime without build-time validation:** The dep DAG, cycle detection, and return type MRO checks must all happen at graph construction time. Deferring to runtime means errors surface late.
- **Using Optional/default for Dep/Recall fields:** This would let users construct nodes without providing deps, but it pollutes the type model. `model_construct()` is the right escape hatch for internal use.
- **Caching by args instead of by callable identity:** The locked decision says "keyed by function identity" and "same function = cached regardless of args." Don't over-engineer arg-based caching.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Topological sort | Custom DFS sort | `graphlib.TopologicalSorter` | Handles cycle detection with `CycleError.args[1]` naming the cycle. Stdlib, zero deps. |
| Cycle detection | Manual visited-set tracking | `graphlib.CycleError` | Cycle is reported as a list of nodes. First and last elements are the same, showing the loop. |
| Bypass Pydantic validation | Subclass `__init__` override | `model_construct()` | Official Pydantic API for trusted data. Handles defaults, `_fields_set`, and `__pydantic_extra__`. |
| Type annotation extraction | Manual `__annotations__` parsing | `get_type_hints(cls, include_extras=True)` | Handles `from __future__ import annotations`, PEP 649 deferred evaluation, and `Annotated` metadata. |

**Key insight:** The entire resolver uses stdlib + Pydantic. No new dependencies needed.

## Common Pitfalls

### Pitfall 1: get_type_hints Without include_extras

**What goes wrong:** `get_type_hints()` strips `Annotated` metadata by default. `Annotated[int, Dep(fn)]` becomes just `int`.
**Why it happens:** Default `include_extras=False` was designed for backward compatibility.
**How to avoid:** Always pass `include_extras=True` when extracting Dep/Recall markers.
**Warning signs:** Field classification finds zero Dep/Recall fields.

### Pitfall 2: get_type_hints on Lambdas Returns Empty

**What goes wrong:** `get_type_hints(lambda: 42)` returns `{}` because lambdas can't have annotations.
**Why it happens:** Python syntax limitation -- lambdas don't support type annotations.
**How to avoid:** The build-time return type check will catch this: dep functions require a return type annotation. Document that lambdas without return annotations are invalid dep functions.
**Warning signs:** `hints.get('return')` is `None` for a dep function.

### Pitfall 3: Bound Method Identity

**What goes wrong:** `obj.method is obj.method` is `False` -- each access creates a new wrapper.
**Why it happens:** Python's descriptor protocol creates new bound method objects on attribute access.
**How to avoid:** The locked decision says dep functions are standalone (no access to node instance). The typical case is plain functions, which have stable identity. If someone passes a bound method as a dep function, caching by identity still works within a single resolution pass because the same `Dep(obj.method)` reference is reused from the annotation. The callable stored in `Dep(fn)` is captured once at class definition time.
**Warning signs:** Same dep function being called multiple times per run.

### Pitfall 4: Circular Dep Error Message Quality

**What goes wrong:** `CycleError.args[1]` contains raw callable objects, not readable names.
**Why it happens:** `graphlib` returns whatever objects were used as nodes.
**How to avoid:** Format the cycle error message by extracting `__name__` (or `__qualname__`) from each callable in the cycle list.
**Warning signs:** Error message shows `<function fn_a at 0x...>` instead of `fn_a`.

### Pitfall 5: Required Fields vs model_construct

**What goes wrong:** If you forget to populate a required Dep/Recall field after `model_construct()`, accessing it raises `AttributeError` with no helpful context.
**Why it happens:** `model_construct()` doesn't create the attribute at all for unset required fields.
**How to avoid:** The resolver must populate ALL Dep and Recall fields before returning the node. Add an assertion/check after resolution that all annotated fields have been set.
**Warning signs:** `AttributeError: 'NodeType' object has no attribute 'field_name'` at runtime.

### Pitfall 6: Recall Searches Need Field Declaration Order

**What goes wrong:** If a node has multiple LLM-filled fields of compatible types, the search could return an unexpected field.
**Why it happens:** `get_type_hints()` returns a dict that in Python 3.7+ preserves insertion order (field declaration order), but when searching trace nodes backward, the first matching field on the most recent node wins.
**How to avoid:** The locked decision says "most recent wins" -- walk trace backward, take first match. Within a single node, field declaration order determines which field is checked first. This is consistent and deterministic.
**Warning signs:** Recall returns a value from an unexpected field.

## Code Examples

### Example 1: v2 Dep Marker Definition

```python
# Source: Derived from CONTEXT decisions + existing markers.py pattern
from dataclasses import dataclass
from collections.abc import Callable

@dataclass(frozen=True)
class Dep:
    """Marker for fields populated by calling a function.

    Usage on node fields:
        weather: Annotated[WeatherResult, Dep(get_weather)]

    Usage on dep function parameters (chaining):
        def get_weather(location: Annotated[GeoLocation, Dep(get_location)]) -> WeatherResult:
            ...
    """
    fn: Callable
```

### Example 2: Recall Marker Definition

```python
# Source: Derived from CONTEXT decisions
from dataclasses import dataclass

@dataclass(frozen=True)
class Recall:
    """Marker for fields populated from the execution trace.

    Searches trace backward for the most recent LLM-filled field
    matching the target type (via issubclass/MRO).

    Usage:
        previous_vibe: Annotated[VibeCheck, Recall()]
    """
    pass
```

### Example 3: RecallError Definition

```python
# Source: Follows existing BaeError pattern in exceptions.py
class RecallError(BaeError):
    """Raised when Recall() finds no matching field in the trace."""
    pass
```

### Example 4: Build-Time Validation

```python
# Source: Derived from locked decisions
import graphlib
from typing import get_type_hints, get_args, get_origin, Annotated

def validate_node_deps(node_cls: type, is_start: bool) -> list[str]:
    """Validate dep and recall annotations on a node class. Returns errors."""
    errors = []
    hints = get_type_hints(node_cls, include_extras=True)

    for field_name, hint in hints.items():
        if get_origin(hint) is not Annotated:
            continue
        args = get_args(hint)
        base_type = args[0]

        for m in args[1:]:
            if isinstance(m, Recall) and is_start:
                errors.append(
                    f"{node_cls.__name__}.{field_name}: "
                    f"Recall on start node is not allowed (no trace exists)"
                )
            if isinstance(m, Dep):
                # Validate return type annotation exists
                dep_hints = get_type_hints(m.fn, include_extras=True)
                ret_type = dep_hints.get('return')
                if ret_type is None:
                    errors.append(
                        f"{node_cls.__name__}.{field_name}: "
                        f"Dep function {_callable_name(m.fn)} has no return type annotation"
                    )
                elif isinstance(ret_type, type) and not issubclass(ret_type, base_type):
                    errors.append(
                        f"{node_cls.__name__}.{field_name}: "
                        f"Dep function {_callable_name(m.fn)} returns {ret_type.__name__}, "
                        f"expected subclass of {base_type.__name__}"
                    )
            break  # Only process first marker per field
    return errors

def _callable_name(fn) -> str:
    """Get a human-readable name for a callable."""
    return getattr(fn, '__qualname__', None) or getattr(fn, '__name__', repr(fn))
```

### Example 5: Dep Resolution with Caching

```python
# Source: Derived from locked decisions (FastAPI Depends pattern)
def resolve_dep(fn, cache: dict, dep_dag_order: list):
    """Resolve a dep function, using cache and resolving transitive deps first."""
    if fn in cache:
        return cache[fn]

    # Resolve this fn's own dep-annotated params
    hints = get_type_hints(fn, include_extras=True)
    kwargs = {}
    for param_name, hint in hints.items():
        if param_name == 'return':
            continue
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            for m in args[1:]:
                if isinstance(m, Dep):
                    # Transitive dep -- should already be in cache
                    # (topo sort guarantees predecessors resolved first)
                    kwargs[param_name] = cache[m.fn]
                    break

    result = fn(**kwargs)
    cache[fn] = result
    return result
```

### Example 6: Complete resolve_fields Skeleton

```python
# Source: Synthesis of all patterns above
def resolve_fields(
    node_cls: type,
    trace: list,
    dep_cache: dict,
    dep_order: list,  # From topological sort
) -> dict[str, object]:
    """Resolve all Dep and Recall fields for a node class.

    Returns dict of {field_name: resolved_value} to pass to model_construct().
    """
    resolved = {}
    hints = get_type_hints(node_cls, include_extras=True)

    for field_name, hint in hints.items():
        if get_origin(hint) is not Annotated:
            continue
        args = get_args(hint)
        base_type = args[0]

        for m in args[1:]:
            if isinstance(m, Dep):
                # Resolve dep (transitive deps already in cache via topo order)
                resolved[field_name] = resolve_dep(m.fn, dep_cache, dep_order)
                break
            elif isinstance(m, Recall):
                # Search trace backward for matching type
                resolved[field_name] = recall_from_trace(trace, base_type)
                break

    return resolved
```

## State of the Art

| Old Approach (v1) | Current Approach (v2) | When Changed | Impact |
|--------------------|-----------------------|--------------|--------|
| `Dep(description="...")` on `__call__` params | `Dep(callable)` on node fields | v2.0 (Phase 5) | Dep marker takes a callable instead of a description string. Shifts from injection-time params to field-level annotations. |
| `Bind()` for downstream data sharing | `Recall()` for trace search | v2.0 (Phase 5) | Explicit publish replaced by implicit trace. Write is automatic, read is `Recall()`. |
| `Context(description="...")` for LLM inputs | Plain fields (no annotation) | v2.0 (Phase 8) | Context marker becomes redundant. Fields without markers = LLM-filled. Removal in Phase 8. |
| `incant` for dep injection | `graphlib.TopologicalSorter` + custom resolver | v2.0 (Phase 5/7) | incant removed in Phase 7. Phase 5 builds the replacement. |

**Deprecated/outdated:**
- v1 `Dep(description=...)`: Still exists in `markers.py`. Phase 5 introduces the new `Dep(fn)` form. Cleanup in Phase 8.
- v1 `Bind()`: Still exists in `markers.py`. Replaced by `Recall()`. Cleanup in Phase 8.
- `incant` library: Still used in `graph.py`. Replacement built in Phase 5, wired in Phase 7.

## Open Questions

1. **v1/v2 Dep coexistence strategy**
   - What we know: v1 `Dep(description="...")` exists in `markers.py` with `description: str` field. v2 `Dep(fn)` needs a `fn: Callable` field. These have incompatible signatures.
   - What's unclear: Should Phase 5 modify the existing `Dep` class (breaking v1 tests) or introduce a new class (e.g., rename existing to `DepV1` temporarily)?
   - Recommendation: Modify `Dep` to accept `fn` as positional arg with a default. v1 usage `Dep(description="...")` uses keyword arg and would still work. Add `fn: Callable | None = None` as the first field. This preserves backward compat until Phase 8 cleanup, and avoids a second Dep class. Alternatively, since Phase 8 removes the old markers, we could just break v1 now if Dzara approves. **Flag for planner to decide.**

2. **Resolver scope: per-node or per-graph?**
   - What we know: Phase 5 builds the resolver "in isolation" (per the phase boundary). Phase 7 integrates it into `Graph.run()`.
   - What's unclear: Should the resolver's public API operate on a single node (resolve one node's fields), or should it manage the full graph run's dep cache?
   - Recommendation: The resolver should be a stateless function `resolve_node_fields(node_cls, trace, dep_cache)` that takes the cache as a mutable input. The caller (Phase 7's run loop) manages the cache lifetime. This keeps Phase 5 self-contained.

3. **Declaration order for field resolution**
   - What we know: CONTEXT says "all fields in declaration order (deps and recalls interleaved, not separated)."
   - What's unclear: Does Python's `get_type_hints()` guarantee field declaration order?
   - Resolution: Yes. Since Python 3.7, `dict` preserves insertion order, and `get_type_hints()` returns fields in declaration order for classes. Verified empirically on Python 3.14. **HIGH confidence.**

## Sources

### Primary (HIGH confidence)

- Python 3.14 `graphlib` documentation: https://docs.python.org/3/library/graphlib.html -- `TopologicalSorter` API, `CycleError` exception, `static_order()`, `add()` with predecessor semantics
- Python 3.14 `typing` documentation: https://docs.python.org/3/library/typing.html -- `get_type_hints(include_extras=True)`, `get_args()`, `get_origin()` with `Annotated`
- Pydantic `model_construct()` API: https://docs.pydantic.dev/latest/api/base_model/ -- classmethod signature `model_construct(_fields_set=None, **values)`, default handling, validation bypass
- Interactive verification on Python 3.14.2 with Pydantic 2.12 -- all code examples tested in the bae project venv

### Secondary (MEDIUM confidence)

- None needed. All findings verified with primary sources.

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib + Pydantic, verified on target Python version
- Architecture: HIGH -- patterns derived from locked decisions and verified interactively
- Pitfalls: HIGH -- all pitfalls discovered through interactive testing, not speculation

**Research date:** 2026-02-07
**Valid until:** 2026-03-07 (stable domain -- stdlib and Pydantic 2.x are mature)
