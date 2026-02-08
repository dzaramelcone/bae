# Technology Stack: v2.0 Context Frames

**Project:** Bae - Type-driven agent graphs with DSPy optimization
**Researched:** 2026-02-07
**Focus:** Stack additions/changes for Dep(callable) chaining, Recall() trace search, field categorization, and Annotated metadata extraction
**Overall confidence:** HIGH -- verified all patterns against live Python 3.14 + Pydantic 2.12.5 in bae's venv

---

## Executive Summary

v2.0 context frames require **zero new dependencies**. Every capability needed -- DAG resolution, Annotated metadata extraction, field categorization, trace search -- is covered by Python's standard library (`graphlib`, `typing`) and Pydantic's existing `FieldInfo` API. The one dependency to **remove** is `incant`, which v2's `Dep(callable)` replaces entirely.

The key insight verified through live testing: Pydantic's `FieldInfo.metadata` already contains Dep/Recall instances when fields use `Annotated[T, Dep(fn)]`. This means bae can use either `model_fields[name].metadata` (simpler, Pydantic-native) or `get_type_hints(include_extras=True)` + `get_origin`/`get_args` (lower-level, needed for dep function parameter introspection). Both approaches work; the right tool depends on context.

---

## Stack Changes: v1 to v2

### Remove

| Package | Current Use | v2 Replacement | Why Remove |
|---------|------------|----------------|------------|
| `incant` | Dep injection in `Graph.run()` via `Incanter.compose_and_call` | `Dep(callable)` with `graphlib.TopologicalSorter` for DAG resolution | incant is a generic DI framework; v2's Dep system is simpler, purpose-built, and avoids the hook factory indirection. The entire `_create_dep_hook_factory` + `_is_dep_annotated` machinery in `graph.py` goes away. |

### Add (stdlib only -- no new pip packages)

| Module | Purpose | Already Available |
|--------|---------|-------------------|
| `graphlib.TopologicalSorter` | Resolve dep function execution order | Yes, stdlib since Python 3.9 |
| `typing.get_type_hints(include_extras=True)` | Extract Annotated metadata from dep function signatures | Yes, stdlib |
| `typing.get_origin` / `typing.get_args` | Decompose `Annotated[T, Dep(fn)]` into base type + metadata | Yes, stdlib (already used in `graph.py`) |

### Keep (unchanged)

| Package | Version (installed) | v2 Role |
|---------|-------------------|---------|
| `pydantic` | 2.12.5 | Node base class, field introspection, model validation |
| `pydantic-ai` | (installed) | LLM backend (`PydanticAIBackend`) |
| `dspy` | 3.1.2 | DSPy compilation (orthogonal to context frames) |
| `typer` | (installed) | CLI |

---

## Capability 1: DAG Resolution for Dep Chaining

### Recommendation: `graphlib.TopologicalSorter` (stdlib)

**Why:** Built into Python since 3.9. Bae requires 3.14+, so this is guaranteed available. No external dep needed. The API is minimal and correct: it detects cycles (raises `CycleError`), handles the exact graph shape we need, and `static_order()` gives us execution order in one call.

**Why not external libraries:** Libraries like `networkx` or `toposort` are overkill. We need exactly one operation (topological sort of a small function DAG), not a graph analysis toolkit. `graphlib` does this in ~5 lines.

### Verified Pattern

Tested and confirmed working in bae's venv (Python 3.14, Pydantic 2.12.5):

```python
from graphlib import TopologicalSorter, CycleError
from typing import Annotated, get_type_hints, get_origin, get_args

def resolve_dep_order(node_cls: type[Node]) -> list[Callable]:
    """Discover all Dep functions on a node, resolve transitive deps,
    return execution order via topological sort."""

    # 1. Collect direct dep fns from node fields
    hints = get_type_hints(node_cls, include_extras=True)
    direct_deps = []
    for field_name, hint in hints.items():
        if get_origin(hint) is Annotated:
            for arg in get_args(hint)[1:]:
                if isinstance(arg, Dep):
                    direct_deps.append(arg.fn)

    # 2. Discover transitive deps by introspecting fn params
    all_fns = set(direct_deps)
    to_scan = list(direct_deps)
    while to_scan:
        fn = to_scan.pop()
        fn_hints = get_type_hints(fn, include_extras=True)
        for param_name, param_hint in fn_hints.items():
            if param_name == "return":
                continue
            if get_origin(param_hint) is Annotated:
                for arg in get_args(param_hint)[1:]:
                    if isinstance(arg, Dep):
                        if arg.fn not in all_fns:
                            all_fns.add(arg.fn)
                            to_scan.append(arg.fn)

    # 3. Build predecessor graph for TopologicalSorter
    graph = {}
    for fn in all_fns:
        fn_hints = get_type_hints(fn, include_extras=True)
        predecessors = set()
        for param_name, param_hint in fn_hints.items():
            if param_name == "return":
                continue
            if get_origin(param_hint) is Annotated:
                for arg in get_args(param_hint)[1:]:
                    if isinstance(arg, Dep):
                        predecessors.add(arg.fn)
        graph[fn] = predecessors

    # 4. Topological sort -- CycleError if circular deps
    ts = TopologicalSorter(graph)
    return list(ts.static_order())
```

**Test result:** For `get_weather(location: LocationDep)` where `LocationDep = Annotated[GeoLocation, Dep(get_location)]`, the output is `[get_location, get_schedule, get_weather]` -- location resolves before weather. Confirmed correct.

### Error Handling

`graphlib.CycleError` is a subclass of `ValueError`. When a cycle is detected:
- `CycleError.args[1]` contains the cycle as a list where first and last elements are identical
- Bae should catch this and raise a `BaeError` with a clear message about the circular dependency

### Key API Details

| Method | Use |
|--------|-----|
| `TopologicalSorter(graph)` | Constructor; graph is `{node: {predecessors}}` |
| `static_order()` | Returns iterator of nodes in valid execution order |
| `CycleError` | Raised if graph has cycles; `.args[1]` has the cycle |
| `prepare()` + `get_ready()` + `done()` | For parallel execution (YAGNI for now) |

---

## Capability 2: Type Matching for Recall (Trace Search)

### Recommendation: Linear scan with `isinstance` check

**Why:** The trace is a `list[Node]` that grows one node per step. For typical agent graphs (5-30 steps), this is a list of 5-30 items. Linear backward scan is the right approach -- anything fancier (indexing by type, etc.) is premature optimization.

### Verified Pattern

```python
def recall_from_trace(target_type: type, trace: list[Node]) -> object | None:
    """Search trace backward for the nearest field matching target_type."""
    for node in reversed(trace):
        for field_name in type(node).model_fields:  # class-level access, not instance
            value = getattr(node, field_name)
            if isinstance(value, target_type):
                return value
    return None
```

**Important Pydantic 2.12 note:** Accessing `node.model_fields` (instance-level) is deprecated since Pydantic 2.11 and will be removed in v3. Use `type(node).model_fields` or `node.__class__.model_fields` instead. This was surfaced by a deprecation warning during testing.

### Field Resolution at Node Construction

When bae constructs a new node, Recall fields are resolved from the trace:

```python
hints = get_type_hints(target_node_cls, include_extras=True)
recall_values = {}
for field_name, hint in hints.items():
    if get_origin(hint) is Annotated:
        base_type = get_args(hint)[0]
        for arg in get_args(hint)[1:]:
            if isinstance(arg, Recall):
                value = recall_from_trace(base_type, trace)
                if value is not None:
                    recall_values[field_name] = value
                break
```

### Performance Note

If graphs ever grow beyond ~100 steps, consider building a `dict[type, object]` index during trace accumulation (O(1) lookup). But for v2, YAGNI -- the linear scan is correct and simple.

---

## Capability 3: Distinguishing "Has Value" vs "Needs LLM Fill"

### Recommendation: Three-way field categorization using `FieldInfo.metadata` + `FieldInfo.is_required()`

The v2 model has exactly three field categories:

| Category | How to Detect | Source |
|----------|--------------|--------|
| **Dep field** | `FieldInfo.metadata` contains a `Dep` instance | Bae calls the dep function |
| **Recall field** | `FieldInfo.metadata` contains a `Recall` instance | Bae searches the trace |
| **LLM field** | No Dep/Recall in metadata | LLM fills when constructing this node |

### Verified Pattern

Tested and confirmed on Pydantic 2.12.5:

```python
def categorize_fields(node_cls: type[Node]) -> tuple[dict, dict, dict]:
    """Categorize node fields into dep, recall, and llm-fill buckets.

    Returns:
        (dep_fields, recall_fields, llm_fields) where each is
        {field_name: metadata_instance} or {field_name: FieldInfo}.
    """
    dep_fields = {}
    recall_fields = {}
    llm_fields = {}

    for field_name, fi in node_cls.model_fields.items():
        found = False
        for meta in fi.metadata:
            if isinstance(meta, Dep):
                dep_fields[field_name] = meta
                found = True
                break
            elif isinstance(meta, Recall):
                recall_fields[field_name] = meta
                found = True
                break
        if not found:
            llm_fields[field_name] = fi

    return dep_fields, recall_fields, llm_fields
```

### Why `FieldInfo.metadata` and Not `get_type_hints`

Two approaches exist:

1. **`FieldInfo.metadata`** -- Pydantic already parsed the `Annotated` type and stored metadata objects in `fi.metadata` as a list. Direct, no re-parsing needed.

2. **`get_type_hints(cls, include_extras=True)`** + `get_origin`/`get_args` -- Lower-level stdlib approach. Re-parses the type annotation.

**Use `FieldInfo.metadata` for node field introspection** (Dep/Recall detection on model classes). It is simpler and Pydantic has already done the parsing.

**Use `get_type_hints(include_extras=True)` for dep function parameter introspection** (dep chaining). Dep functions are plain callables, not Pydantic models, so `model_fields` does not apply.

### Start Node vs Other Nodes

For start nodes, all fields are caller-provided. Bae does not need to distinguish -- the caller constructs the start node directly with all values. The categorization matters only for nodes that bae constructs during graph execution.

### "Has Value" at Construction Time

When bae constructs a non-start node:
1. Resolve Dep fields (call functions in topological order)
2. Resolve Recall fields (search trace backward)
3. Pass dep + recall values to the LLM alongside the current node context
4. LLM fills remaining fields (the LLM fields)
5. Construct the new node with all values

Pydantic validates the complete node. If a required LLM field is missing, Pydantic raises `ValidationError` -- this is correct behavior and should propagate.

---

## Capability 4: Annotated Metadata Extraction Patterns

### Two Access Paths (Both Verified)

#### Path A: Pydantic `FieldInfo.metadata` (for model fields)

```python
for field_name, fi in MyNode.model_fields.items():
    for meta in fi.metadata:
        if isinstance(meta, Dep):
            print(f"{field_name}: dep fn = {meta.fn}")
        elif isinstance(meta, Recall):
            print(f"{field_name}: recall")
```

**Verified output:**
```
weather: dep fn = get_weather
schedule: dep fn = get_schedule
```

#### Path B: stdlib `get_type_hints` (for plain callables)

```python
from typing import get_type_hints, get_origin, get_args, Annotated

hints = get_type_hints(get_weather, include_extras=True)
for param_name, hint in hints.items():
    if param_name == "return":
        continue
    if get_origin(hint) is Annotated:
        base_type = get_args(hint)[0]
        metadata = get_args(hint)[1:]
        for meta in metadata:
            if isinstance(meta, Dep):
                print(f"  param {param_name}: chained dep = {meta.fn.__name__}")
```

**Verified output:**
```
  param location: chained dep = get_location
```

### Type Alias Transparency

Annotated type aliases (e.g., `WeatherDep = Annotated[WeatherResult, Dep(get_weather)]`) are fully transparent to both access paths. When a dep function parameter is typed as `location: LocationDep`, `get_type_hints` resolves the alias and returns `Annotated[GeoLocation, Dep(get_location)]`. No special handling needed. **Verified.**

### Dep and Recall Marker Design

Current v1 markers are `@dataclass(frozen=True)` classes. For v2:

```python
@dataclass(frozen=True)
class Dep:
    """Marker: bae calls this function to populate the field."""
    fn: Callable

@dataclass(frozen=True)
class Recall:
    """Marker: bae searches the trace to populate the field."""
    pass
```

Using frozen dataclasses is correct: they are hashable (useful if we ever need to deduplicate), immutable, and have clean `__repr__`. No reason to change this pattern.

### Edge Case: `__future__.annotations`

Bae uses `from __future__ import annotations` in some files. On Python 3.14 with PEP 649, `get_type_hints()` handles deferred annotations correctly. However, `get_type_hints` on functions defined in modules with `from __future__ import annotations` requires the function's `__globals__` for resolution, which `get_type_hints` uses automatically when called with the function object. **No special handling needed.**

---

## What NOT to Add

| Temptation | Why Not | What to Use Instead |
|------------|---------|---------------------|
| `networkx` for dep DAG | 40MB+ dependency for one topological sort | `graphlib.TopologicalSorter` (stdlib, 0 bytes) |
| `typing-inspection` (Pydantic's utility) | Already a transitive dep of Pydantic, but unnecessary -- `get_origin`/`get_args` + `FieldInfo.metadata` cover all needs | stdlib `typing` + Pydantic's `FieldInfo.metadata` |
| `inject` or `dependency-injector` | Generic DI frameworks; Dep(callable) is simpler and domain-specific | Hand-rolled dep resolution with `graphlib` |
| Custom sentinel for "needs LLM fill" | Pydantic's `PydanticUndefined` + `FieldInfo.is_required()` already distinguish this; MISSING sentinel (experimental in 2.12) is overkill | `FieldInfo.metadata` categorization (no Dep/Recall = LLM fills) |
| `toposort` PyPI package | Redundant with stdlib `graphlib` | `graphlib.TopologicalSorter` |

---

## Updated `pyproject.toml` Changes

```toml
[project]
dependencies = [
    "pydantic>=2.11",        # was >=2.0; bump for model_fields deprecation awareness
    "pydantic-ai>=0.1",
    "dspy>=2.0",
    # "incant>=1.0",         # REMOVE: replaced by Dep(callable) + graphlib
    "typer>=0.12",
]
```

**Note:** Bump `pydantic>=2.11` minimum to match our reliance on class-level `model_fields` access (instance-level deprecated in 2.11). The installed version is 2.12.5, so this is a documentation concern, not a practical one.

---

## Version Compatibility (v2-specific)

| Component | Minimum | Installed | Notes |
|-----------|---------|-----------|-------|
| Python | 3.9 (graphlib) / 3.14 (PEP 649) | 3.14 | PEP 649 is the real constraint; graphlib comes free |
| `pydantic` | 2.11 | 2.12.5 | 2.11+ for clean `model_fields` access |
| `graphlib` | stdlib 3.9+ | stdlib | No version to manage |
| `typing` | stdlib | stdlib | `get_type_hints(include_extras=True)` available since 3.11 |

---

## Confidence Assessment

| Claim | Confidence | Verification |
|-------|------------|--------------|
| `graphlib.TopologicalSorter` handles dep DAGs correctly | HIGH | Live-tested in bae's venv; correct ordering for chained deps |
| `FieldInfo.metadata` contains Dep/Recall from Annotated | HIGH | Live-tested; Pydantic 2.12.5 stores metadata instances directly |
| `get_type_hints(include_extras=True)` resolves type aliases | HIGH | Live-tested; `LocationDep` alias transparent to introspection |
| Linear trace scan sufficient for Recall | HIGH | Architectural reasoning; graphs are 5-30 steps |
| `incant` can be fully replaced | HIGH | v2 Dep pattern covers all current incant usage in `graph.py` |
| Instance-level `model_fields` deprecated in 2.11 | HIGH | Deprecation warning observed during testing |
| `CycleError` provides cycle details in `.args[1]` | HIGH | [Python docs](https://docs.python.org/3/library/graphlib.html) |

---

## Sources

### Primary (HIGH confidence -- verified against live environment)
- [Python graphlib documentation](https://docs.python.org/3/library/graphlib.html) -- TopologicalSorter API, CycleError
- [Python typing documentation](https://docs.python.org/3/library/typing.html) -- get_type_hints, Annotated, get_origin, get_args
- [Pydantic Fields API](https://docs.pydantic.dev/latest/api/fields/) -- FieldInfo.metadata, FieldInfo.is_required()
- [Pydantic Models documentation](https://docs.pydantic.dev/latest/concepts/models/) -- model_fields_set, model_fields
- Live testing in bae's venv (Python 3.14, Pydantic 2.12.5, graphlib stdlib)

### Secondary (MEDIUM confidence)
- [Pydantic 2.12 release notes](https://pydantic.dev/articles/pydantic-v2-12-release) -- MISSING sentinel (experimental, decided not to use)
- [Python discuss: PEP 593 annotation extraction](https://discuss.python.org/t/what-is-the-right-way-to-extract-pep-593-annotations/42424) -- edge cases with Required/NotRequired nesting (not relevant to bae's use case)
- [typing-inspection docs](https://typing-inspection.pydantic.dev/latest/usage/) -- evaluated and decided against using directly

### Previous Research (this project)
- v1 STACK.md (2026-02-04) -- DSPy compilation stack (orthogonal, still valid)
