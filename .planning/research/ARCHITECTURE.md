# Architecture: v2 Context Frames Integration

**Domain:** Bae node API redesign -- "nodes as context frames"
**Researched:** 2026-02-07
**Confidence:** HIGH (analysis of existing codebase + v2 reference implementation)

## Executive Summary

The v2 redesign replaces three marker types (Context, Bind, Dep-on-params) with two field-level markers (Dep(callable), Recall()) and eliminates the LM parameter from `__call__`. This is a focused refactoring, not a rewrite. The existing topology discovery (graph.py `_discover`), validation, and trace collection all survive with minor modifications. The major structural change is in the execution loop: `Graph.run()` must now resolve field values (Dep, Recall) *before* calling the LM to fill remaining fields, rather than the current pattern where the LM produces the entire next node.

The critical insight: **v1 nodes produce their successors. v2 nodes receive their fields from three sources (Dep, Recall, LM) and bae orchestrates the assembly.** This inverts control -- bae owns field population, nodes just declare what they need.

## v1 vs v2 Execution Flow Comparison

### v1 (Current)

```
Graph.run() loop:
  1. current_node = start_node
  2. strategy = _get_routing_strategy(current)
  3. if "make":  next = lm.make(current, target_type)
     if "decide": next = lm.decide(current)
     if "custom": next = incanter.compose_and_call(current.__call__, lm=lm)
     if "terminal": next = None
  4. _capture_bind_fields(current, dep_registry)
  5. current = next; repeat
```

LM receives current node, produces entire next node. Fields are either LM-generated or injected via incant at __call__ time.

### v2 (Target)

```
Graph.run() loop:
  1. current_node = start_node (fields provided by caller)
  2. strategy = _get_routing_strategy(current)
  3. Determine next node TYPE (lm.decide or return type analysis)
  4. Resolve target node's Dep fields (topological order, call fns)
  5. Resolve target node's Recall fields (search trace backward)
  6. LM fills remaining plain fields (given resolved deps/recalls as context)
  7. Construct next node instance from all field sources
  8. Append to trace
  9. current = next; repeat
```

LM receives resolved Dep/Recall values as context, fills only the unresolved fields. Node construction is bae's job, not the LM's.

## Component-by-Component Impact Analysis

### 1. markers.py -- Refactored

**Current state:** Context, Dep (description-only), Bind
**v2 state:** Dep(callable), Recall()

```python
# v1 markers.py
@dataclass(frozen=True)
class Context:         # REMOVE -- redundant with "fields with values"
    description: str = ""

@dataclass(frozen=True)
class Dep:             # CHANGE -- takes callable instead of description
    description: str = ""

@dataclass(frozen=True)
class Bind:            # REMOVE -- replaced by implicit trace + Recall
    pass

# v2 markers.py
@dataclass(frozen=True)
class Dep:
    fn: Callable       # The function bae calls to populate this field
    # No description needed -- the function IS the description

@dataclass(frozen=True)
class Recall:          # NEW -- search trace backward for matching type
    pass
```

**Breaking changes:**
- `Context` removed: all references in compiler.py, dspy_backend.py, tests must be updated
- `Dep` signature changes: no longer takes `description`, takes `fn` callable
- `Bind` removed: all references in graph.py, tests must be updated
- `Recall` added: new marker

**Migration path:**
- v1 `Context(description="...")` fields --> plain fields (no annotation needed for LM context)
- v1 `Bind()` fields --> removed entirely (trace stores all nodes implicitly)
- v1 `Dep(description="...")` on __call__ params --> `Dep(fn)` on node fields
- New: `Recall()` on node fields for trace lookback

### 2. node.py -- Minimal Changes

**What stays:**
- `Node(BaseModel)` base class
- `successors()` classmethod (return type extraction)
- `is_terminal()` classmethod
- `_has_ellipsis_body()` (still used for routing strategy)
- `_extract_types_from_hint()`, `_hint_includes_none()`
- `NodeConfig` (still used for per-node model/temperature)

**What changes:**
- `__call__` signature: remove `lm: LM` parameter
- `__call__` default implementation: just `...` (ellipsis) since bae handles everything
- The `Node` base `__call__` should no longer call `lm.decide(self)` -- bae owns routing

```python
# v1
class Node(BaseModel):
    def __call__(self, lm: LM, *_args, **_kwargs) -> Node | None:
        return lm.decide(self)

# v2
class Node(BaseModel):
    def __call__(self) -> Node | None:
        ...  # Default: bae handles routing via return type hint
```

**Impact:**
- All user-defined nodes lose `lm` parameter in `__call__`
- Custom logic nodes that called `lm.make()` / `lm.decide()` need an escape hatch (see graph.py section)
- `get_type_hints(cls.__call__)` still works for extracting return types

### 3. graph.py -- Major Changes to run()

This is the biggest change. The execution loop must now:

**A. Remove incant dependency**

v1 uses incant for Dep injection into `__call__` parameters. v2 has no `__call__` parameters to inject into. Dep is now on node fields, resolved before LM call.

```python
# v1: incant injects deps into __call__ params
incanter.compose_and_call(current.__call__, lm=lm)

# v2: no incant needed -- field resolution replaces parameter injection
```

**B. Add field resolution step**

New function: resolve Dep and Recall fields for a target node type before constructing it.

```python
def _resolve_fields(
    target_cls: type[Node],
    trace: list[Node],
    dep_cache: dict[type, Any],
) -> dict[str, Any]:
    """Resolve Dep and Recall fields for a target node type.

    Returns dict of field_name -> resolved_value for non-LM fields.
    """
    resolved = {}
    hints = get_type_hints(target_cls, include_extras=True)

    for field_name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            base_type = args[0]
            metadata = args[1:]

            for meta in metadata:
                if isinstance(meta, Dep):
                    # Resolve dep (may chain)
                    resolved[field_name] = _resolve_dep(meta.fn, dep_cache)
                elif isinstance(meta, Recall):
                    # Search trace backward
                    resolved[field_name] = _resolve_recall(base_type, trace)

    return resolved
```

**C. Dep chaining resolution**

Dep functions can themselves declare Dep-typed parameters. This creates a DAG that must be resolved in topological order. This is the most complex new logic.

```
get_weather(location: LocationDep) -> WeatherResult
get_location() -> GeoLocation

Resolution order: get_location() first, then get_weather(location=result)
```

This is a DAG resolution problem. The resolver must:
1. Inspect the dep fn's parameter type hints
2. For params with Dep annotations, resolve those first (recursively)
3. Cache results (a dep fn should only run once per graph execution step)

**D. Recall resolution**

Search the trace backward for a node whose fields contain a value matching the requested type.

```python
def _resolve_recall(target_type: type, trace: list[Node]) -> Any:
    """Search trace backward for a field value matching target_type."""
    for node in reversed(trace):
        hints = get_type_hints(type(node), include_extras=True)
        for field_name, hint in hints.items():
            base_type = _get_base_type(hint)
            if base_type == target_type or (isinstance(base_type, type) and issubclass(base_type, target_type)):
                value = getattr(node, field_name)
                if value is not None:
                    return value
    raise BaeError(f"Recall failed: no {target_type.__name__} found in trace")
```

**E. Modified execution loop**

```python
def run(self, start_node: Node, lm: LM | None = None, max_steps: int = 100) -> GraphResult:
    trace: list[Node] = []
    current: Node | None = start_node
    dep_cache: dict[type, Any] = {}  # Cache dep fn results across the run

    while current is not None and steps < max_steps:
        trace.append(current)

        strategy = _get_routing_strategy(current.__class__)

        if strategy[0] == "terminal":
            break  # Terminal node -- current IS the output
        elif strategy[0] == "custom":
            next_node = current()  # No lm param in v2
        else:
            # Determine target type(s)
            if strategy[0] == "make":
                target_type = strategy[1]
            elif strategy[0] == "decide":
                target_type = lm.choose_type(current, strategy[1])

            # Resolve Dep and Recall fields for target type
            resolved = _resolve_fields(target_type, trace, dep_cache)

            # LM fills remaining fields, given resolved values as context
            next_node = lm.fill(current, target_type, resolved_fields=resolved)

        current = next_node
        steps += 1

    return GraphResult(node=trace[-1] if trace else None, trace=trace)
```

**F. Validation changes**

- Remove `_validate_bind_uniqueness()` -- Bind is gone
- Add: validate that start node has no Dep/Recall fields (start node fields are caller-provided)
- Add: validate that Dep fn signatures don't create cycles (DAG check)
- Keep: terminal path validation (unchanged)

**G. What to do with `_get_routing_strategy()`**

Still useful. Ellipsis body detection still determines whether bae auto-routes or the user has custom logic. But the "custom" path changes -- custom `__call__` no longer receives `lm`, so custom nodes that need LM access need a different escape hatch.

**Escape hatch options for custom logic:**
1. Custom nodes return a type (not an instance) and bae still resolves fields
2. Custom nodes can call a graph-level helper to access LM
3. Custom nodes receive a `ctx` object with trace/lm access

Recommendation: Option 1 is simplest and fits the paradigm. Custom `__call__` returns a type or `None`, bae resolves fields. If custom nodes need to set specific field values, they return a partial dict.

### 4. lm.py -- Protocol Changes

**Current LM protocol:**
```python
class LM(Protocol):
    def make(self, node: Node, target: type[T]) -> T: ...
    def decide(self, node: Node) -> Node | None: ...
```

**v2 LM protocol:**

The LM's job changes. It no longer produces entire node instances. It:
1. Chooses a type from union options (`choose_type`)
2. Fills plain fields given resolved deps/recalls as context (`fill`)

```python
class LM(Protocol):
    def choose_type(
        self,
        current: Node,
        options: list[type[Node]],
    ) -> type[Node]:
        """Pick which successor type to produce."""
        ...

    def fill(
        self,
        current: Node,
        target: type[T],
        resolved_fields: dict[str, Any],
    ) -> T:
        """Fill plain fields of target type. Resolved fields are provided as context."""
        ...
```

`make` and `decide` collapse into `choose_type` + `fill`. This is cleaner -- the LM always does two distinct jobs (type selection and field population), and bae handles field resolution.

**Impact on backends:**
- `PydanticAIBackend`: rewrite `make`/`decide` into `choose_type`/`fill`
- `ClaudeCLIBackend`: same refactor
- `DSPyBackend`: same refactor, but signature generation changes too (see compiler.py)
- `OptimizedLM`: extends new base protocol

### 5. compiler.py -- Significant Changes

**Current:** `node_to_signature()` extracts `Context`-annotated fields as InputFields.

**v2:** Context is gone. The signature must reflect the new field taxonomy:

| Field Kind | In Signature? | As What |
|------------|---------------|---------|
| Dep(fn) | YES (as InputField) | Resolved value is LLM context |
| Recall() | YES (as InputField) | Recalled value is LLM context |
| Plain (no annotation) | YES (as OutputField) | LLM must produce this |
| Fields with defaults | Depends | If caller-set, InputField; if LLM-filled, OutputField |

```python
def node_to_signature(node_cls: type[Node]) -> type[dspy.Signature]:
    fields = {}
    hints = get_type_hints(node_cls, include_extras=True)

    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            metadata = args[1:]
            for meta in metadata:
                if isinstance(meta, (Dep, Recall)):
                    # Resolved by bae -- becomes InputField (context for LLM)
                    fields[name] = (args[0], dspy.InputField())
                    break
        else:
            # Plain field -- LLM fills this -- becomes OutputField
            fields[name] = (hint, dspy.OutputField())

    instruction = node_cls.__name__
    return dspy.make_signature(fields, instruction)
```

**Impact on optimization pipeline:**
- `trace_to_examples()` in optimizer.py needs to know which fields are inputs vs outputs
- `optimize_node()` and `node_transition_metric()` may need updates
- Save/load format unchanged (still JSON predictor state)

### 6. result.py -- Minor Changes

**Current:** `GraphResult(node: Node | None, trace: list[Node])`

In v2, terminal node IS the output (its fields ARE the response schema). The `node` field should be the terminal node instance, not `None`.

```python
# v1: node is None when graph terminates normally
# v2: node is the terminal node instance (its fields are the output)
```

This is mostly a semantic change. The data structure stays the same, but the terminal node is always the last trace entry and `result.node` should be that terminal node.

### 7. Start Node and Terminal Node Semantics

**Start node:**
- Fields are caller-provided (no Dep, no Recall, no LM fill)
- Validation should enforce: start node has no Dep/Recall annotations
- Start node is created by the user: `graph.run(MyStartNode(field=value))`
- This is already how v1 works, just needs enforcement

**Terminal node:**
- Returns `None` from `__call__` (unchanged)
- Fields ARE the output schema
- All fields filled by bae (Dep, Recall, LM) during the last transition
- `GraphResult.node` should be the terminal node instance

## New Components Needed

### A. `bae/resolver.py` (NEW MODULE)

Houses the Dep and Recall resolution logic. This is the core new functionality.

**Contents:**
- `resolve_fields(target_cls, trace, dep_cache) -> dict[str, Any]`
- `resolve_dep(fn, dep_cache) -> Any` (with chaining)
- `resolve_recall(target_type, trace) -> Any`
- `build_dep_dag(fn) -> list[Callable]` (topological sort of dep chain)

**Rationale for separate module:** This logic is self-contained, testable in isolation, and doesn't belong in graph.py (which is already handling topology and execution). The resolver is a new concept that deserves its own module.

### B. Updated `bae/markers.py`

Not a new module, but significantly changed. Dep gets a callable, Recall is new, Context and Bind are removed.

## Integration Points

```
                    +------------------+
                    |      Graph       |
                    | - _discover()    |  UNCHANGED
                    | - validate()     |  MODIFIED (remove Bind check, add start/dep DAG checks)
                    | - run()          |  MAJOR REWRITE
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
    +---------v---+   +------v------+  +----v----------+
    |   Node      |   |  Resolver   |  |    LM         |
    | - fields    |   |  (NEW)      |  | - choose_type |
    | - __call__  |   | - deps      |  | - fill        |
    | - successors|   | - recalls   |  +----+----------+
    +-------------+   +------+------+       |
                             |        +-----+------+
                             |        |            |
                      +------v------+ v            v
                      |   markers   | PydanticAI  DSPy
                      | - Dep(fn)   | Backend     Backend
                      | - Recall()  |
                      +-------------+
```

### Data Flow (v2)

```
1. Graph.__init__(start=StartNode)
   --> _discover() walks return types (UNCHANGED)

2. Graph.run(StartNode(field=value))
   --> start_node added to trace

3. Loop iteration:
   a. _get_routing_strategy(current) --> strategy
   b. If terminal: break, return current as result
   c. If decide: lm.choose_type(current, [TypeA, TypeB]) --> target_type
      If make: target_type = strategy[1]
   d. resolver.resolve_fields(target_type, trace, dep_cache)
      --> resolves Dep fields (calls fns, caches results)
      --> resolves Recall fields (searches trace)
      --> returns {field_name: value} for resolved fields
   e. lm.fill(current, target_type, resolved_fields)
      --> LM gets: current node as context, resolved fields as additional context
      --> LM produces: values for remaining plain fields
      --> Returns: target_type instance with all fields populated
   f. next_node added to trace
   g. current = next_node
```

## Suggested Build Order

Based on dependency analysis:

### Phase 1: Markers + Resolver (Foundation)

1. **Refactor markers.py** -- New Dep(callable), new Recall(), remove Context/Bind
2. **Create resolver.py** -- Dep resolution with chaining, Recall trace search
3. **Test resolver in isolation** -- Unit tests for dep DAG, recall search, error cases

*Rationale:* Everything else depends on these. They're testable without touching graph.py or lm.py.

### Phase 2: Node + LM Protocol (Interface)

4. **Update node.py** -- Remove `lm` from `__call__`, update default implementation
5. **Update LM protocol** -- `choose_type` + `fill` replacing `make` + `decide`
6. **Update one backend** (PydanticAI or DSPy) -- Implement new protocol

*Rationale:* Node changes are small but affect every test. LM protocol change gates the execution loop rewrite.

### Phase 3: Execution Loop (Integration)

7. **Rewrite Graph.run()** -- New execution loop with resolver integration
8. **Update validation** -- Remove Bind checks, add start node + dep DAG checks
9. **Remove incant dependency** -- No longer needed

*Rationale:* This is the integration phase. Everything from phases 1-2 comes together here.

### Phase 4: Compiler + Optimization (Adaptation)

10. **Update compiler.py** -- New signature generation (Dep/Recall as InputField, plain as OutputField)
11. **Update optimizer.py** -- Trace format changes, metric updates
12. **Update OptimizedLM** -- Implement new protocol over optimized predictors

*Rationale:* Compiler and optimization are downstream of the core execution changes.

### Phase 5: Cleanup + Migration

13. **Update __init__.py exports** -- Remove Context/Bind, add Recall
14. **Update all tests** -- Remove v1 patterns, test v2 behavior
15. **Verify examples/ootd.py runs end-to-end**

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Dep chaining creates cycles | HIGH | DAG validation at graph init, not at runtime |
| Recall finds wrong type match | MEDIUM | Exact type match first, subclass match as fallback |
| Custom __call__ escape hatch unclear | MEDIUM | Design decision needed: what do custom nodes return? |
| LM fill quality degrades vs make | LOW | fill() gets more context (resolved deps), should be better |
| incant removal breaks something unexpected | LOW | incant only used in one place (Graph.run custom path) |

## Open Design Questions

### 1. Custom __call__ escape hatch

When a node has custom logic in `__call__`, what can it do in v2? In v1 it received `lm` and could call `lm.make()` / `lm.decide()`. In v2 there's no `lm` parameter.

**Options:**
- A) Custom `__call__` returns a type (bae resolves fields)
- B) Custom `__call__` returns a dict of field overrides + a type
- C) Custom `__call__` receives a `Context` object with trace/lm/resolver access
- D) Custom `__call__` can still receive lm via NodeConfig or graph-level injection

**Recommendation:** Option A for simplicity. If custom logic needs to set specific field values, Option B as extension. Option C is over-engineering for v2.

### 2. Dep cache scope

Should dep fn results be cached per-step or per-run?

- Per-step: `get_weather()` called fresh each time a node needs it
- Per-run: `get_weather()` called once, result reused across all nodes

The ootd.py example suggests per-run (weather doesn't change mid-conversation). But some deps might be time-sensitive.

**Recommendation:** Per-run cache by default. Add a `cache=False` option to Dep if needed later (YAGNI for now).

### 3. Start node Dep/Recall validation

Should bae error if start node has Dep or Recall fields? Or silently skip resolution?

**Recommendation:** Error. Start node fields are caller-provided. If a user puts Dep on a start node, it's a mistake.

### 4. Terminal node field population

In the ootd.py example, `RecommendOOTD` is the terminal node. Its fields (top, bottom, footwear, etc.) need to be filled by the LM. So terminal nodes DO go through field resolution -- they're not just passthrough.

The flow for the last step is:
1. Current node is `AnticipateUsersDay` (all fields resolved)
2. Strategy: make `RecommendOOTD`
3. Resolve `RecommendOOTD`'s Dep/Recall fields (none in this case)
4. LM fills plain fields (top, bottom, footwear, etc.)
5. `RecommendOOTD` instance is the final output

This means terminal detection should happen AFTER the node is constructed, not before. The loop should check if the newly constructed node's `__call__` returns None.

## Sources

- Bae codebase analysis: `bae/node.py`, `bae/graph.py`, `bae/lm.py`, `bae/compiler.py`, `bae/markers.py`
- v2 reference implementation: `examples/ootd.py`
- v2 design decisions: `.planning/PROJECT.md` (v2 Design Decisions section)
- v1 architecture: `.planning/codebase/ARCHITECTURE.md`
- v1 research: `.planning/research/ARCHITECTURE.md` (DSPy integration)

---
*Architecture research: 2026-02-07 -- v2 context frames integration*
