# Phase 7: Integration - Research

**Researched:** 2026-02-07
**Domain:** Internal codebase integration -- Graph.run() v2 rewrite, incant removal, resolver/compiler/LM wiring
**Confidence:** HIGH

## Summary

This phase integrates modules built in Phases 5 (resolver) and 6 (compiler/LM protocol) into a rewritten `Graph.run()`. The current `Graph.run()` in `bae/graph.py` uses incant for dependency injection into `__call__` parameters and the v1 LM protocol (`make`/`decide` operating on node instances). The v2 runtime replaces this with field-level resolution (Dep/Recall on node fields, resolved before `__call__`), the v2 LM protocol (`choose_type`/`fill` operating on context dicts), and drops incant entirely.

The change surface is concentrated in `bae/graph.py` (the execution loop), `bae/exceptions.py` (new error types), `bae/node.py` (`_wants_lm` update), and `pyproject.toml` (incant removal). The resolver (`bae/resolver.py`) and LM backends (`bae/lm.py`, `bae/dspy_backend.py`) are mostly ready -- they already have the v2 APIs (`resolve_fields`, `choose_type`, `fill`). The main work is replacing the execution loop's guts and updating/replacing v1 tests.

**Primary recommendation:** Rewrite `Graph.run()` iteratively: first wire resolver integration (deps+recalls set on self before `__call__`), then replace routing with `choose_type`/`fill`, then remove incant, then add error hierarchy and logging. Each step is independently testable.

## Standard Stack

This phase uses NO new external dependencies. It removes one.

### Core (Already in codebase)

| Library | Version | Purpose | Role in Phase 7 |
|---------|---------|---------|-----------------|
| pydantic | >=2.0 | BaseModel, model_construct, model_validate | Node field population, validation retry |
| pydantic-ai | >=0.1 | format_as_xml | Context serialization for LM prompts |
| dspy | >=2.0 | Predict, Signature | DSPyBackend (unchanged, already has fill/choose_type) |
| graphlib | stdlib | TopologicalSorter | Dep DAG resolution (unchanged, in resolver.py) |
| logging | stdlib | Logger | New DEBUG-level observability in Graph.run() |

### Removed

| Library | Current Version | Why Removed |
|---------|----------------|-------------|
| incant | 25.1.0 | Replaced by bae's own resolver. Only used in graph.py lines 11, 304-306, 327-328. |

### No New Dependencies

The v2 integration is purely internal rewiring. All building blocks exist.

## Architecture Patterns

### Current v1 Execution Flow (What Changes)

```python
# Current Graph.run() flow (bae/graph.py lines 258-344):
def run(self, start_node, lm=None, max_steps=100, **kwargs):
    # 1. Default LM to DSPyBackend
    # 2. Initialize dep_registry from kwargs
    # 3. Create incanter with dep hook factory
    # 4. Loop:
    #    a. trace.append(current)
    #    b. _get_routing_strategy(current.__class__)
    #    c. Dispatch:
    #       - "terminal" -> None
    #       - "make" -> lm.make(current, target_type)       # v1 API
    #       - "decide" -> lm.decide(current)                 # v1 API
    #       - "custom" -> incanter.compose_and_call(...)     # incant
    #    d. _capture_bind_fields(current, dep_registry)
    #    e. current = next_node
```

### v2 Execution Flow (Target State)

```python
# v2 Graph.run() flow:
def run(self, start_node, lm=None, max_iters=10):
    dep_cache = {}  # Per-run dep cache
    trace = []

    current = start_node
    iters = 0
    while current is not None:
        if max_iters and iters >= max_iters:
            raise BaeError(...)

        # 1. Resolve deps (bae/resolver.py resolve_fields)
        resolved = resolve_fields(current.__class__, trace, dep_cache)

        # 2. Set resolved values on self (model_construct already created shell)
        for field_name, value in resolved.items():
            object.__setattr__(current, field_name, value)

        # 3. Append to trace (after dep/recall resolution, before __call__)
        trace.append(current)

        # 4. Invoke __call__
        if _wants_lm(current.__class__.__call__):
            next_type_or_node = current(lm)
        else:
            next_type_or_node = current()

        # 5. Determine next node via LM
        #    - If __call__ returned a Node instance (custom logic) -> use directly
        #    - If __call__ has ... body -> LM routing
        #       - Return None -> terminal, stop
        #       - Return single type -> lm.fill(type, context, instruction)
        #       - Return union -> lm.choose_type(types, context) then lm.fill(...)

        iters += 1
```

### Pattern 1: Field Resolution Before __call__

**What:** Dep and Recall fields are resolved and set on `self` BEFORE `__call__` runs. Custom `__call__` logic reads `self.dep_field` instead of receiving injected parameters.

**Why critical:** This is the fundamental paradigm shift from v1. In v1, deps are injected as `__call__` parameters via incant. In v2, deps are node FIELDS resolved before execution. `__call__` only takes `self` and optionally `lm`.

**Current state in code:**
- `resolve_fields(node_cls, trace, dep_cache)` in `bae/resolver.py` (lines 264-301) returns `{field_name: value}` for Dep and Recall fields
- `resolve_dep(fn, cache)` in `bae/resolver.py` (lines 227-261) handles transitive dep chains with caching
- These functions are fully tested and working (test_resolver.py, 590 lines)

**How to set fields on a Pydantic model instance:**
```python
# Use object.__setattr__ to bypass Pydantic's frozen model protection
for field_name, value in resolved.items():
    object.__setattr__(current, field_name, value)
```

Note: `model_config` has `arbitrary_types_allowed=True` already set (node.py line 164). Setting via `object.__setattr__` works on Pydantic v2 models. For non-frozen models, `setattr(current, field_name, value)` also works.

### Pattern 2: LM Fill Creates Next Node

**What:** After `__call__` determines the next type, the LM creates the next node instance using `fill()` with resolved context from the current node.

**Context assembly for fill:**
```python
# The context for fill() is the current node's resolved fields as XML
# format_as_xml(node_instance, root_tag=ClassName) handles BaseModel directly
from pydantic_ai import format_as_xml
context_xml = format_as_xml(current, root_tag=current.__class__.__name__)
```

**Key detail from CONTEXT.md:** "model_dump_xml" means using `format_as_xml` on the BaseModel instance (not `node.model_dump()` then format). `format_as_xml` already supports BaseModel directly and preserves field metadata.

**Current `fill()` API** (already implemented in all backends):
```python
# bae/dspy_backend.py line 355
def fill(self, target: type[T], context: dict[str, Any], instruction: str) -> T:
    # Uses node_to_signature(target, is_start=False)
    # Context dict provides InputField values; LM generates OutputField values
    # Returns target.model_construct(**all_fields)
```

**IMPORTANT tension:** The current `fill()` takes a `dict[str, object]` context, but the CONTEXT.md decision says "model_dump_xml from the BaseModel (XML serialization, not flat dict)". This needs reconciliation:
- `fill()` on DSPyBackend passes context as keyword args to `dspy.Predict`, which needs individual field values (dict)
- PydanticAIBackend and ClaudeCLIBackend format context as XML string in their prompts
- Recommendation: The context dict is the right interface for `fill()`. The XML formatting happens INSIDE the backend (as it already does in `choose_type`). The CONTEXT.md "model_dump_xml" decision applies to how the context is presented to the LLM, not the API surface.

### Pattern 3: Validation Retry on Fill

**What:** When `fill()` creates a node via `model_construct`, validation may fail. Error messages are fed back to the LM for correction.

**Current state:** DSPyBackend already has retry logic (`max_retries` in `_call_with_retry`, line 113). The `fill()` method uses `model_construct()` which skips validation. For v2 fill validation retry:

```python
# Proposed fill-with-retry pattern:
for attempt in range(max_retries + 1):
    node = lm.fill(target, context, instruction)
    try:
        target.model_validate(node.model_dump())  # Validate the constructed node
        return node
    except ValidationError as e:
        if attempt < max_retries:
            context["validation_error"] = str(e)  # Feed back to LM
            continue
        raise FillError(target, e, attempt + 1) from e
```

### Pattern 4: _wants_lm Type-Hint Detection

**What:** The CONTEXT.md decision changes `_wants_lm` from name-based to type-hint-based detection.

**Current implementation** (node.py lines 109-121):
```python
def _wants_lm(method) -> bool:
    sig = inspect.signature(method)
    return "lm" in sig.parameters
```

**New implementation** per CONTEXT decision:
```python
def _wants_lm(method) -> bool:
    """Check if __call__ has a parameter type-hinted as LM protocol."""
    hints = get_type_hints(method)
    for name, hint in hints.items():
        if name == "return" or name == "self":
            continue
        # Check if the type hint is LM or a subclass/protocol match
        if hint is LM or (isinstance(hint, type) and issubclass(hint, LM)):
            return True
    return False
```

**Complication:** LM is a `Protocol` class. `issubclass()` may not work cleanly with Protocol types in all Python versions. For Python 3.14+, `isinstance` and `issubclass` work with `runtime_checkable` Protocols. Need to verify LM has `@runtime_checkable`. Currently it does NOT -- LM is just `Protocol` (lm.py line 19). This needs to be added or the detection needs a different approach (e.g., checking if the annotation IS the LM class by identity).

**Tests that need updating:** test_node_config.py `TestWantsLm` class (5 tests) -- these test name-based detection and will need rewriting for type-hint-based detection.

### Anti-Patterns to Avoid

- **Mixing v1 and v2 in the execution loop:** Don't call both `lm.decide(current)` AND `lm.choose_type(...)` in the same code path. Clean cut: v2 loop uses ONLY `choose_type`/`fill`.

- **Resolving deps AFTER `__call__`:** The ordering is critical: resolve deps/recalls FIRST, set on self, THEN invoke `__call__`. Breaking this order means custom `__call__` can't read dep fields.

- **Using `setattr` on frozen models:** If model_config ever sets `frozen=True`, `setattr` will fail. Use `object.__setattr__` to bypass Pydantic's descriptor.

## Integration Point Map

### File-by-File Change Surface

| File | What Changes | Severity |
|------|-------------|----------|
| `bae/graph.py` | **MAJOR rewrite** of `run()`, removal of incant imports and helpers (`_is_dep_annotated`, `_create_dep_hook_factory`, `_capture_bind_fields`), `_get_routing_strategy` may be simplified or removed | HIGH |
| `bae/exceptions.py` | Add `DepError`, `FillError` subclasses with structured attributes | MEDIUM |
| `bae/node.py` | Update `_wants_lm` to type-hint-based detection, potentially update base `Node.__call__` signature | MEDIUM |
| `bae/__init__.py` | Update exports (add DepError, FillError; eventually remove Bind/Context in Phase 8) | LOW |
| `pyproject.toml` | Remove `"incant>=1.0"` from dependencies | LOW |
| `bae/lm.py` | No changes needed -- v2 API already present | NONE |
| `bae/resolver.py` | No changes needed -- already complete | NONE |
| `bae/compiler.py` | No changes needed -- node_to_signature v2 already works | NONE |
| `bae/dspy_backend.py` | Minor: may need context format adjustment for fill() | LOW |

### Functions to Remove from graph.py

| Function | Lines | Reason |
|----------|-------|--------|
| `_is_dep_annotated()` | 20-28 | incant hook -- no longer needed |
| `_get_base_type()` | 31-49 | Used only by incant dep registry and Bind capture |
| `_create_dep_hook_factory()` | 52-65 | incant hook factory -- replaced by resolver |
| `_capture_bind_fields()` | 68-84 | Bind is v1 -- removed in Phase 8, but graph.run no longer uses it |

Note: `_get_routing_strategy()` (lines 87-131) may still be useful for determining whether the node has an ellipsis body, single return, union return, or terminal return. But it could be simplified since the v2 loop handles routing differently.

### Functions Used Unchanged from resolver.py

| Function | Purpose | Called From |
|----------|---------|-------------|
| `resolve_fields(node_cls, trace, dep_cache)` | Resolve all Dep and Recall fields | Each loop iteration |
| `resolve_dep(fn, cache)` | Single dep resolution with caching | Called by resolve_fields |
| `recall_from_trace(trace, target_type)` | Search trace for matching type | Called by resolve_fields |
| `classify_fields(node_cls)` | Classify fields as dep/recall/plain | Used by node_to_signature (already wired) |

### Functions Used Unchanged from LM backends

| Function | Purpose | Called From |
|----------|---------|-------------|
| `lm.choose_type(types, context)` | Pick successor type from union | Routing step for union returns |
| `lm.fill(target, context, instruction)` | Populate plain fields via LM | Node creation step |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dep resolution + caching | Custom dep loop in graph.py | `resolve_fields()` from resolver.py | Already handles DAG ordering, caching, error propagation |
| Trace search for recall | Manual trace iteration | `recall_from_trace()` from resolver.py | Handles MRO matching, dep/recall field skipping |
| XML context formatting | Custom XML builder | `pydantic_ai.format_as_xml()` | Already handles BaseModel, nested types, field metadata |
| Node field classification | Manual hint inspection | `classify_fields()` from resolver.py | Already handles Annotated unwrapping, marker matching |
| DSPy signature generation | Manual field mapping | `node_to_signature()` from compiler.py | Already handles is_start, dep/recall/plain classification |
| Dep cycle detection | Custom graph walk | `build_dep_dag()` + `validate_node_deps()` from resolver.py | Already uses graphlib.TopologicalSorter |

**Key insight:** Phase 5 and Phase 6 built all the pieces. Phase 7's job is ONLY to wire them into graph.py's execution loop. Resist the urge to rebuild anything in the resolver, compiler, or LM backends.

## Common Pitfalls

### Pitfall 1: Trace Timing -- When to Append

**What goes wrong:** Appending to trace at the wrong time causes recall to see stale data or miss the current node.

**Why it happens:** v1 appends `trace.append(current)` as the FIRST action in the loop (line 309). For v2, recall resolution needs to search the trace, so the current node should be in the trace BEFORE recall runs on it? Actually no -- recall searches for PREVIOUS nodes' fields, not the current node. The current node's recall fields are looking backward.

**How to avoid:** Append current node to trace AFTER dep/recall resolution and field-setting, BEFORE `__call__`. This ensures:
1. Recall resolution sees all PREVIOUS nodes (correct)
2. Terminal node (from CONTEXT: "included in the trace") is appended before the loop exits
3. Trace order matches execution order

**Warning signs:** Test that recall finds data from 2 nodes ago but not from the current node.

### Pitfall 2: model_construct vs model_validate for LM-Created Nodes

**What goes wrong:** Using `model_construct()` skips validation, so LM-generated invalid field values silently pass through. Using `model_validate()` may reject partially-constructed nodes.

**Why it happens:** The CONTEXT decision says "LM fill creates a new node instance (model_construct + validation). Validation failure -> error messages fed back to LM for correction." This means: first `model_construct` to build, then `model_validate` to check, then retry if invalid.

**How to avoid:** The fill-then-validate pattern should live in the execution loop (or a helper), not deep inside the LM backend. The LM backend's `fill()` already uses `model_construct()`. The validation retry wraps around `fill()` at the graph.run level.

**Warning signs:** Nodes with required fields that the LM didn't populate -- these should trigger FillError, not silently pass with None values.

### Pitfall 3: Ellipsis Body Node __call__ Return Value

**What goes wrong:** For `...` body nodes, `__call__` is "always invoked" per CONTEXT. But an ellipsis body returns `None` (that's what `...` evaluates to at runtime). The caller must NOT interpret this as "terminal" -- it must use the return type HINT for routing.

**Why it happens:** `def __call__(self) -> NextType: ...` -- when called, this returns `None` (the default return of a function body that's just `...`). But the return TYPE HINT says `NextType`.

**How to avoid:** For ellipsis-body nodes, DON'T use the runtime return value. Use `_get_routing_strategy()` to read the type hints, then route accordingly. Only for custom-body nodes (non-ellipsis) should the runtime return value be used.

**Current code already handles this correctly** (graph.py lines 311-329) -- it checks strategy first and only calls `__call__` for "custom" strategy. The CONTEXT says "__call__ always invoked (even for ... body nodes)" -- this is a CHANGE from v1. The v2 loop should call `__call__` on every node (for consistency), but for `...` body nodes, ignore the return value and route via type hints.

**Recommendation:** For `...` body nodes, calling `__call__` is harmless (returns None/Ellipsis) and can be done for uniform lifecycle. But the routing decision comes from type hint introspection, not the return value.

### Pitfall 4: _wants_lm with Protocol Type Checking

**What goes wrong:** LM is a Protocol class. `issubclass(SomeType, LM)` may raise `TypeError` if LM isn't `@runtime_checkable`, or may not work as expected with structural subtyping.

**Why it happens:** Python's `issubclass` with Protocol types has specific behavior. For structural Protocols (without `@runtime_checkable`), `issubclass` raises `TypeError`.

**How to avoid:** Either:
1. Make LM `@runtime_checkable` (add decorator to LM class in lm.py)
2. Check by identity: `hint is LM`
3. Check if the annotation name contains "LM" and the type is from bae.lm module

**Recommendation:** Use approach 1 (add `@runtime_checkable`) OR approach 2 (identity check `hint is LM`). Identity check is simpler and avoids Protocol complexity. The parameter can be named anything -- what matters is the type annotation.

### Pitfall 5: Bind Capture Removal Timing

**What goes wrong:** v1 tests rely on `_capture_bind_fields` to propagate values between nodes via the dep_registry. Removing this before replacing those tests breaks the test suite.

**Why it happens:** Bind is a v1 concept being removed in Phase 8. But Phase 7 removes incant which is the mechanism that CONSUMES bound values. The tests in test_dep_injection.py test Bind -> Dep injection via incant.

**How to avoid:** The CONTEXT says "v1 tests that verify incant injection behavior are deleted and replaced with v2 integration tests." This means:
- Delete test_dep_injection.py tests that test Bind -> incant -> Dep injection
- Write new tests that test Dep(callable) -> resolve_fields -> set on self
- Bind tests in test_bind_validation.py (graph topology validation) can stay -- they test Graph.validate(), not Graph.run()

### Pitfall 6: max_steps vs max_iters Naming

**What goes wrong:** CONTEXT says "Max iteration limit with low default (10)". Current code uses `max_steps=100`. Changing the parameter name is a breaking API change.

**How to avoid:** Change parameter name from `max_steps` to `max_iters` with default `10`. This IS a breaking change but is intentional per CONTEXT. Update all call sites in tests.

## Code Examples

### Example 1: v2 Graph.run() Core Loop (Pseudocode)

```python
# Source: Synthesized from CONTEXT.md decisions + existing resolver/LM APIs
def run(self, start_node: Node, lm: LM | None = None, max_iters: int = 10) -> GraphResult:
    if lm is None:
        from bae.dspy_backend import DSPyBackend
        lm = DSPyBackend()

    trace: list[Node] = []
    dep_cache: dict = {}
    current: Node | None = start_node
    iters = 0

    logger.debug("Graph.run() starting with %s", current.__class__.__name__)

    while current is not None:
        if max_iters and iters >= max_iters:
            err = BaeError(f"Graph execution exceeded {max_iters} iterations")
            err.trace = trace
            raise err

        # 1. Resolve deps and recalls
        try:
            resolved = resolve_fields(current.__class__, trace, dep_cache)
        except RecallError as e:
            raise RecallError(str(e), cause=e)  # Already correct type
        except Exception as e:
            raise DepError(
                f"{e.__class__.__name__}: failed on {current.__class__.__name__}",
                node_type=current.__class__,
                cause=e,
            ) from e

        # 2. Set resolved values on self
        for field_name, value in resolved.items():
            object.__setattr__(current, field_name, value)

        logger.debug("Resolved %d fields on %s", len(resolved), current.__class__.__name__)

        # 3. Append to trace
        trace.append(current)

        # 4. Invoke __call__
        strategy = _get_routing_strategy(current.__class__)

        if strategy[0] == "terminal":
            current = None
        elif strategy[0] == "custom":
            # Custom __call__ logic
            if _wants_lm(current.__class__.__call__):
                current = current(lm)
            else:
                current = current()
        else:
            # Ellipsis body -> LM routing
            # Build context from current node
            context = _build_context(current)

            if strategy[0] == "make":
                target_type = strategy[1]
                instruction = _build_instruction(target_type)
                current = lm.fill(target_type, context, instruction)
            elif strategy[0] == "decide":
                types_list = list(strategy[1])
                chosen = lm.choose_type(types_list, context)
                instruction = _build_instruction(chosen)
                current = lm.fill(chosen, context, instruction)

        iters += 1

    return GraphResult(node=None, trace=trace)
```

### Example 2: New Error Types

```python
# Source: CONTEXT.md error propagation model decisions
class DepError(BaeError):
    """Raised when a Dep function fails."""
    def __init__(self, message: str, *, node_type: type | None = None,
                 field_name: str = "", cause: Exception | None = None):
        super().__init__(message, cause=cause)
        self.node_type = node_type
        self.field_name = field_name
        self.trace: list | None = None

    def __str__(self):
        parts = ["DepError"]
        if self.field_name:
            parts.append(f": {self.field_name}")
        if self.node_type:
            parts.append(f" on {self.node_type.__name__}")
        if self.__cause__:
            parts.append(f" ({self.__cause__})")
        return "".join(parts)


class FillError(BaeError):
    """Raised when LM fill validation fails after retries."""
    def __init__(self, message: str, *, node_type: type | None = None,
                 validation_errors: str = "", attempts: int = 0,
                 cause: Exception | None = None):
        super().__init__(message, cause=cause)
        self.node_type = node_type
        self.validation_errors = validation_errors
        self.attempts = attempts
        self.trace: list | None = None
```

### Example 3: Context Building for LM Fill

```python
# Source: pydantic_ai.format_as_xml docs + CONTEXT.md "model_dump_xml" decision
from pydantic_ai import format_as_xml

def _build_context(node: Node) -> dict[str, object]:
    """Build context dict from current node for LM fill.

    Returns all field values on the node (deps resolved, recalls resolved,
    plain fields caller-provided or LM-filled from previous step).
    """
    return {
        name: getattr(node, name)
        for name in node.model_fields
        if hasattr(node, name)
    }

def _build_instruction(target_type: type) -> str:
    """Build instruction string from class name + optional docstring."""
    instruction = target_type.__name__
    if target_type.__doc__:
        instruction += f": {target_type.__doc__.strip()}"
    return instruction
```

Note: The context dict is passed to `fill()` which internally uses `node_to_signature(target, is_start=False)`. Dep/Recall fields become InputFields (context), plain fields become OutputFields (LM fills). The XML formatting happens inside each backend's `fill()` implementation.

## State of the Art

| Old Approach (v1) | New Approach (v2) | Changed In | Impact |
|---|---|---|---|
| `incant.compose_and_call()` for dep injection | `resolve_fields()` + `object.__setattr__()` | Phase 7 | Removes incant dependency entirely |
| `lm.make(node, target)` / `lm.decide(node)` | `lm.choose_type(types, ctx)` + `lm.fill(target, ctx, instr)` | Phase 7 | Decouples LM from node instances |
| `__call__` params for deps (Dep on params) | Node fields for deps (Dep on fields) | Phase 5+7 | Deps visible as data, not hidden in signatures |
| `_wants_lm` checks param name "lm" | `_wants_lm` checks param type hint LM | Phase 7 | Type-safe, name-independent |
| `max_steps=100` (generous default) | `max_iters=10` (low pedagogical default) | Phase 7 | Forces explicit config for large graphs |
| `_capture_bind_fields` for value propagation | Not needed (Recall replaces Bind's use case) | Phase 7/8 | Simpler, no mutable registry |

**Deprecated/outdated:**
- `_is_dep_annotated()` in graph.py: incant hook, removed
- `_create_dep_hook_factory()` in graph.py: incant hook factory, removed
- `_capture_bind_fields()` in graph.py: Bind mechanism, removed (Bind itself removed in Phase 8)
- v1 `make`/`decide` on LM Protocol: Kept for Phase 8 removal but not used in v2 loop

## Test Impact Analysis

### Tests That Must Be DELETED and REPLACED

| Test File | Test Class / Tests | Why Deleted | Replacement |
|-----------|-------------------|-------------|-------------|
| `test_dep_injection.py` | `TestExternalDepsFromRunKwargs` (3 tests) | Tests incant injection of `__call__` params | v2 integration tests with Dep(callable) on fields |
| `test_dep_injection.py` | `TestBindFieldCapture` (2 tests) | Tests Bind -> incant dep registry | v2 tests with Recall or Dep(callable) |
| `test_dep_injection.py` | `TestDepInjectionViaIncant` (2 tests) | Tests incant type matching | v2 tests with resolve_fields |
| `test_dep_injection.py` | `TestDepsAccumulateThroughRun` (2 tests) | Tests Bind accumulation via incant | v2 tests with trace-based Recall |
| `test_dep_injection.py` | `TestMissingDepsRaiseError` (2 tests) | Tests incant missing dep error | v2 tests with DepError |
| `test_integration_dspy.py` | `TestBindDepValueFlow` | Tests Bind -> Dep via incant | v2 integration test |
| `test_integration_dspy.py` | `TestExternalDepInjection` | Tests run() kwargs -> incant | v2 integration test |
| `test_integration_dspy.py` | `test_dep_params_injected_via_incant` | Explicitly tests incant | v2 equivalent |

### Tests That Must Be UPDATED

| Test File | What Changes | Why |
|-----------|-------------|-----|
| `test_graph.py` | `TestGraphRun` tests: update MockLM, max_steps->max_iters | API parameter change |
| `test_auto_routing.py` | `TestGraphRunAutoRouting`: update MockLM pattern | v2 loop calls `__call__` differently |
| `test_node_config.py` | `TestWantsLm`: rewrite for type-hint detection | Name-based -> type-hint-based |
| `test_integration_dspy.py` | `TestAutoRouting*`, `TestDSPyBackendDefault` | v2 routing changes |

### Tests That Should Be UNCHANGED

| Test File | Why Unchanged |
|-----------|--------------|
| `test_resolver.py` | Tests resolver in isolation (no graph.run involvement) |
| `test_compiler.py` | Tests node_to_signature in isolation |
| `test_lm_protocol.py` | Tests choose_type/fill in isolation |
| `test_node.py` | Tests Node topology (successors, is_terminal) |
| `test_result.py` / `test_result_v2.py` | Tests GraphResult structure |
| `test_bind_validation.py` | Tests Graph.validate() (not run()) |
| `test_signature_v2.py` | Tests node_to_signature v2 |
| `test_dspy_backend.py` | Tests DSPyBackend methods in isolation |
| `test_optimized_lm.py` | Tests OptimizedLM in isolation |
| `test_optimizer.py` | Tests optimizer pipeline |

## Open Questions

1. **model_dump_xml vs context dict for fill():**
   - What we know: CONTEXT says "model_dump_xml" format. Current `fill()` takes `dict[str, object]`. `format_as_xml` handles BaseModel directly.
   - What's unclear: Should `fill()` API change to accept a string (XML) instead of dict? Or does "model_dump_xml" just mean the LM sees XML internally?
   - Recommendation: Keep `fill(target, context_dict, instruction)` API unchanged. The XML formatting is an implementation detail of each backend. The context dict is the right abstraction. Document that backends should format as XML when presenting to the LM.

2. **Static recall analysis at graph build time:**
   - What we know: CONTEXT says "RecallError raised at graph build time via static analysis -- covers both obvious cases (type never in graph) AND path-dependent cases (type reachable but specific paths skip it)."
   - What's unclear: How deep should path-dependent analysis go? This is potentially a hard graph reachability problem.
   - Recommendation: Start with the obvious case (type never appears in any node reachable from start). Path-dependent analysis can be a stretch goal or deferred to a later iteration if it proves complex. The runtime RecallError already handles the runtime miss case.

3. **Base Node.__call__ signature change:**
   - What we know: Current base Node.__call__ has `(self, lm: LM, *_args, **_kwargs)`. CONTEXT says `__call__` only takes `self` and optionally LM.
   - What's unclear: Should the base Node.__call__ signature change? Should *_args/**_kwargs be removed?
   - Recommendation: Yes, simplify to `def __call__(self) -> Node | None: ...` with no default implementation. Subclasses that want LM add `def __call__(self, lm: LM) -> ...: ...`. The current default `return lm.decide(self)` is a v1 pattern that should go away. But this is a Phase 8 concern (cleanup) -- for Phase 7, just make the v2 loop not depend on the base signature.

4. **Validation retry ownership:**
   - What we know: CONTEXT says "Retry limit on LM fill validation is configurable (default exists, overridable per-node or per-graph)."
   - What's unclear: Where does the retry config live? In NodeConfig? In Graph constructor? As a parameter to run()?
   - Recommendation: Add `max_fill_retries: int = 3` as a Graph.run() parameter for simplicity. Per-node override can use `NodeConfig` (already has `lm` field, can add `max_fill_retries`).

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of `/Users/dzaramelcone/lab/bae/bae/*.py` (all source files read in full)
- Direct codebase analysis of `/Users/dzaramelcone/lab/bae/tests/*.py` (all test files read in full)
- `/Users/dzaramelcone/lab/bae/.planning/phases/07-integration/07-CONTEXT.md` -- locked decisions
- `/Users/dzaramelcone/lab/bae/.planning/STATE.md` -- project state and accumulated decisions
- `/Users/dzaramelcone/lab/bae/.planning/ROADMAP.md` -- phase dependencies and success criteria
- `pydantic_ai.format_as_xml` -- verified via `help()` in bae's venv (supports BaseModel directly)

### Secondary (MEDIUM confidence)
- [Pydantic v2 serialization docs](https://docs.pydantic.dev/latest/concepts/serialization/) -- confirmed no native `model_dump_xml`; XML requires pydantic-xml or format_as_xml from pydantic-ai

### Tertiary (LOW confidence)
- `@runtime_checkable` behavior on Python 3.14 with Protocol types -- behavior inferred from training data, not verified on 3.14 specifically

## Metadata

**Confidence breakdown:**
- Codebase analysis: HIGH -- every file read directly, all integration points mapped
- Architecture patterns: HIGH -- synthesized from locked CONTEXT decisions + verified existing APIs
- Pitfalls: HIGH -- identified from actual code structure and CONTEXT decision tensions
- Test impact: HIGH -- every test file analyzed for incant/Bind/v1 dependencies

**Research date:** 2026-02-07
**Valid until:** 2026-03-07 (internal codebase research, no external version drift risk)
