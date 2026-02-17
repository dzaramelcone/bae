# Phase 2: DSPy Integration - Research

**Researched:** 2026-02-04
**Domain:** DSPy Predict integration, incant dependency injection, auto-routing in graph execution
**Confidence:** HIGH

## Summary

This phase wires the signature generation from Phase 1 to `Graph.run()` with three major capabilities: (1) auto-routing based on return type introspection (union -> decide, single -> make), (2) dependency injection via incant for both external kwargs and node-bound values, and (3) dspy.Predict replacing naive prompts.

The locked decisions from CONTEXT.md define clear implementation paths:
- **Two-step pattern** for union return types: pick type, then fill (already implemented in `ClaudeCLIBackend.decide()` - this pattern carries forward to DSPy)
- **GraphResult** with `.node` and `.trace` attributes for execution results
- **Bind/Dep markers** for accumulating values through the run (Bind on node fields, Dep on `__call__` params)
- **Self-correction** on parse failures: pass validation error back to LM with 1 retry (2 total attempts)

The research confirms DSPy 3.1.2 is installed with `dspy.Predict` as the core module. For retry/self-correction, we build custom logic rather than using deprecated `dspy.Assert` or complex `dspy.Refine`. Incant 25.1.0 provides type-based dependency injection via `register_by_type()` and `compose_and_call()`.

**Primary recommendation:** Use `dspy.Predict(signature)` for LM calls, build a custom retry wrapper for parse failures that injects the `AdapterParseError` message as a hint field, and use incant's `register_by_type()` for Bind-to-Dep injection with type-unique validation at graph construction time.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | 3.1.2 | Predict module for structured LM calls | Already installed; provides Signature-based prompting |
| incant | 25.1.0 | Dependency injection | Already in pyproject.toml; lightweight, type-based |
| pydantic | 2.x | Node validation, model parsing | Already used by bae Node |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typing (stdlib) | Python 3.14 | `get_type_hints`, `get_origin`, `get_args`, `Union` | Return type introspection |
| tenacity | (via dspy) | Retry logic | Could use for API failure retries, but simple loop is cleaner |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom retry wrapper | `dspy.Refine` | Refine is designed for reward-based optimization, not simple parse-failure correction; custom is simpler |
| incant | Manual kwargs passing | incant handles transitive deps automatically; manual is error-prone |
| `dspy.Assert` (deprecated) | Custom self-correction | Assert is deprecated in DSPy 2.6+; custom gives us control |

**Installation:**
Already installed:
```bash
uv pip install dspy incant pydantic
```

## Architecture Patterns

### Recommended Project Structure
```
bae/
|-- compiler.py     # node_to_signature() (Phase 1, extended for union outputs)
|-- markers.py      # Context, Dep, Bind markers
|-- graph.py        # Graph.run() with auto-routing and dep injection
|-- lm.py           # DSPyBackend implementing LM protocol
|-- errors.py       # Bae exception hierarchy (NEW)
|-- node.py         # Node base class (mostly unchanged)
```

### Pattern 1: Two-Step Decide with dspy.Predict

**What:** For union return types (`A | B | None`), first call LM to pick the type, then call LM again to fill the chosen type's fields.

**When to use:** When `__call__` return type is a union of multiple Node types.

**Example:**
```python
# Source: Existing ClaudeCLIBackend.decide() pattern, adapted for DSPy
from dspy import Predict, make_signature, InputField, OutputField

def decide_with_dspy(node, successors: tuple[type[Node], ...], is_terminal: bool) -> Node | None:
    """Two-step decide: pick type, then fill."""
    # Step 1: Pick the type
    type_names = [t.__name__ for t in successors]
    if is_terminal:
        type_names.append("None")

    choice_sig = make_signature({
        "context": (str, InputField(desc="Current node state")),
        "choice": (str, OutputField(desc=f"One of: {', '.join(type_names)}")),
    }, "Decide the next step")

    choice_pred = Predict(choice_sig)
    result = choice_pred(context=node_to_context_string(node))
    chosen = result.choice

    if chosen == "None":
        return None

    # Step 2: Fill the chosen type
    target = next(t for t in successors if t.__name__ == chosen)
    return make_with_dspy(node, target)
```

### Pattern 2: Self-Correction Retry Wrapper

**What:** Wrap dspy.Predict calls with a retry loop that catches `AdapterParseError`, extracts the error message, and injects it as a hint field on the next attempt.

**When to use:** All LM calls (both make and decide).

**Example:**
```python
# Source: Pattern derived from dspy.Refine feedback injection
from dspy import Predict, InputField
from dspy.utils.exceptions import AdapterParseError

def predict_with_retry(
    predictor: Predict,
    inputs: dict,
    max_retries: int = 1,  # 2 total attempts
) -> Prediction:
    """Call predictor with parse-failure self-correction."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            if last_error is None:
                return predictor(**inputs)
            else:
                # Inject hint from previous error
                hint_sig = predictor.signature.append(
                    "correction_hint",
                    InputField(desc="Previous attempt failed validation. Fix this issue.")
                )
                hint_pred = Predict(hint_sig)
                inputs_with_hint = {**inputs, "correction_hint": str(last_error)}
                return hint_pred(**inputs_with_hint)
        except AdapterParseError as e:
            last_error = e

    # All retries exhausted
    raise BaeParseError("Parse failed after retries", __cause__=last_error)
```

### Pattern 3: Incant-Based Dependency Injection

**What:** Use incant's `register_by_type()` to inject Bind-captured values into Dep-annotated `__call__` params by type matching.

**When to use:** Graph.run() to inject both external kwargs and accumulated Bind values.

**Example:**
```python
# Source: incant documentation + bae Bind/Dep pattern
from incant import Incanter

def run_with_deps(graph, start_node: Node, **external_deps) -> GraphResult:
    """Run graph with dependency injection."""
    incanter = Incanter()

    # Register external deps (passed to run())
    for name, value in external_deps.items():
        # Register by type (value's type)
        incanter.register_by_type(lambda v=value: v, type=type(value))

    trace = []
    current = start_node

    while current is not None:
        # Before calling __call__, collect Bind fields from current node
        bind_values = collect_bind_values(current)
        for bind_type, bind_value in bind_values.items():
            # Check type-unique constraint
            if has_registered_type(incanter, bind_type):
                raise BaeGraphError(f"Duplicate Bind for type {bind_type}")
            incanter.register_by_type(lambda v=bind_value: v, type=bind_type)

        # Use incant to call __call__ with deps injected
        next_node = incanter.compose_and_call(current.__call__, lm=lm)

        trace.append(current)
        current = next_node

    return GraphResult(node=trace[-1] if trace else None, trace=trace)
```

### Pattern 4: Auto-Routing via Return Type Introspection

**What:** Inspect `__call__` return type hint to determine routing strategy: union -> decide, single type -> make, `...` body -> automatic.

**When to use:** Graph.run() dispatch logic.

**Example:**
```python
# Source: Python typing module + bae Node.successors() pattern
import types
from typing import get_type_hints, get_args

def should_auto_route(node_cls: type[Node]) -> bool:
    """Check if __call__ uses ... (Ellipsis) body for auto-routing."""
    if "__call__" not in node_cls.__dict__:
        return True  # Uses base class - auto-route

    # Check if body is just `...`
    import inspect
    source = inspect.getsource(node_cls.__call__)
    # Simple heuristic: body contains only "..." or "pass"
    return "..." in source and "return" not in source

def get_routing_strategy(node_cls: type[Node]) -> str:
    """Determine routing strategy from return type."""
    hints = get_type_hints(node_cls.__call__)
    return_hint = hints.get("return")

    if return_hint is None:
        return "terminal"

    # Check if union (X | Y | None)
    if isinstance(return_hint, types.UnionType):
        args = get_args(return_hint)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) > 1:
            return "decide"  # Multiple types -> LM decides
        elif len(non_none) == 1:
            return "make"    # Single type (+ optional None) -> LM makes

    # Single type
    if isinstance(return_hint, type):
        return "make"

    return "decide"  # Default to decide if unclear
```

### Anti-Patterns to Avoid

- **Using dspy.Assert/Suggest:** Deprecated in DSPy 2.6+. Build custom retry wrapper instead.
- **Mutable Bind registry:** Don't mutate a shared registry across runs. Create fresh Incanter per run.
- **Type collision without validation:** Always check for duplicate Bind types at graph construction or runtime.
- **Passing raw error to LM:** Format `AdapterParseError` message cleanly for LM consumption, don't dump full traceback.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dependency resolution | Manual param matching | incant `compose_and_call()` | Handles transitive deps, caching, type matching |
| Signature creation | `type()` metaclass | `dspy.make_signature()` | Handles field validation, metaclass setup |
| JSON parsing with repair | Manual JSON parsing | `json_repair.loads()` (via DSPy) | Handles malformed JSON from LLM |
| Return type introspection | String parsing | `get_type_hints()` + `types.UnionType` | Handles forward refs, PEP 649 |

**Key insight:** incant's type-based injection and DSPy's adapter parse handling do the heavy lifting. The custom code is glue between these systems.

## Common Pitfalls

### Pitfall 1: AdapterParseError vs Other Exceptions

**What goes wrong:** Catching all exceptions when only parse failures should trigger retry.

**Why it happens:** DSPy raises many exception types - API errors, context window, validation.

**How to avoid:** Catch specifically `AdapterParseError` for parse retries. Let API errors propagate or handle with separate retry logic.

**Warning signs:** Infinite retry loops on non-recoverable errors.

### Pitfall 2: Incant Hook Registration Order

**What goes wrong:** Later registrations don't override earlier ones as expected.

**Why it happens:** incant prepends hooks to registry (most recent first), so last registration wins. But if cache isn't cleared, old composition is used.

**How to avoid:** Call `incanter._call_cache.cache_clear()` after adding hooks at runtime, or create fresh Incanter per run.

**Warning signs:** Deps not being injected despite registration.

### Pitfall 3: Type-Unique Constraint Violation

**What goes wrong:** Two nodes both Bind a value of the same type, causing ambiguous injection.

**Why it happens:** No validation at graph construction time.

**How to avoid:** Validate Bind type uniqueness when graph is constructed, not at runtime.

**Warning signs:** Wrong value injected into Dep param, or silent incorrect behavior.

### Pitfall 4: Signature Mutation with Hints

**What goes wrong:** Original Signature gets mutated when adding correction_hint field.

**Why it happens:** Using `signature.append()` which may or may not return a new signature.

**How to avoid:** Always assign result of `signature.append()` to new variable; don't assume in-place mutation.

**Warning signs:** Subsequent calls have hint field when they shouldn't.

### Pitfall 5: Union Type Detection

**What goes wrong:** Failing to detect `X | Y` syntax (Python 3.10+ union) vs `Union[X, Y]`.

**Why it happens:** Python 3.10+ uses `types.UnionType` for `X | Y`, different from `typing.Union`.

**How to avoid:** Check both `isinstance(hint, types.UnionType)` and `get_origin(hint) is Union`.

**Warning signs:** Auto-routing fails for `A | B` return types but works for `Union[A, B]`.

## Code Examples

Verified patterns from official sources:

### Creating and Calling dspy.Predict
```python
# Source: DSPy predict.py, dspy.ai/api/modules/Predict/
import dspy

# Configure LM globally
dspy.configure(lm=dspy.LM("anthropic/claude-opus-4-6"))

# Create predictor with signature
predictor = dspy.Predict("context, question -> answer")

# Call with keyword args
result = predictor(context="Paris is the capital of France", question="What is the capital?")
print(result.answer)

# With custom config per call
result = predictor(context="...", question="...", config={"temperature": 0.7})
```

### Catching AdapterParseError
```python
# Source: dspy/utils/exceptions.py, dspy/adapters/json_adapter.py
from dspy.utils.exceptions import AdapterParseError

try:
    result = predictor(context="...", question="...")
except AdapterParseError as e:
    print(f"Failed to parse: {e.lm_response}")
    print(f"Expected fields: {list(e.signature.output_fields.keys())}")
    if e.parsed_result:
        print(f"Partial parse: {e.parsed_result}")
```

### Incant Type-Based Registration
```python
# Source: incant/__init__.py register_by_type()
from incant import Incanter

incanter = Incanter()

# Register factory by return type
@incanter.register_by_type
def get_database() -> Database:
    return Database(connection_string="...")

# Or register with explicit type
incanter.register_by_type(lambda: my_cache, type=Cache)

# Call function with deps injected
def process(db: Database, cache: Cache):
    ...

result = incanter.compose_and_call(process)  # db and cache auto-injected
```

### Dynamic Signature Modification
```python
# Source: dspy/signatures/signature.py, dspy/predict/refine.py pattern
from dspy import make_signature, InputField, OutputField

# Original signature
original = make_signature({
    "context": (str, InputField(desc="Context")),
    "answer": (str, OutputField()),
}, "Answer based on context")

# Add a hint field for retry
extended = original.append(
    "hint",
    InputField(desc="Correction hint from previous failed attempt")
)

# extended is a NEW signature class, original unchanged
```

### GraphResult Class Design
```python
# Recommended design (Claude's Discretion item)
from dataclasses import dataclass

@dataclass
class GraphResult:
    """Result of Graph.run() execution."""
    node: Node | None  # Final node (None if terminated)
    trace: list[Node]  # Flat list of nodes in execution order

    def __bool__(self) -> bool:
        """Truthy if execution completed (node is None = terminated normally)."""
        return self.node is None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `dspy.Assert` / `dspy.Suggest` | `dspy.Refine` or custom retry | DSPy 2.6 | Assertions deprecated; Refine is reward-based |
| String signatures `"a -> b"` | Class-based or dict-based signatures | DSPy 2.x | Better type safety, IDE support |
| Manual dep passing | incant type-based injection | Always available | Cleaner code, transitive deps |

**Deprecated/outdated:**
- `dspy.Assert`, `dspy.Suggest`: Deprecated in DSPy 2.6+. Use custom retry or `dspy.Refine`.
- `dspy.TypedPredictor`: Regular Predict now handles Pydantic types natively.

## Open Questions

Things that couldn't be fully resolved:

1. **Exact Bind marker implementation**
   - What we know: Bind marks node fields that should be injectable to downstream Dep params
   - What's unclear: Should Bind be a field annotation like Context, or a ClassVar marker?
   - Recommendation: Make Bind a field annotation (`field: Annotated[T, Bind()]`) for consistency with Context/Dep pattern. Extract at runtime like Context fields.

2. **API failure retry strategy**
   - What we know: Decision is "retry once, then raise" for API failures (timeout, rate limit, network)
   - What's unclear: What backoff strategy? tenacity integration?
   - Recommendation (Claude's Discretion): Simple `time.sleep(1)` between retries. Keep it simple - one retry is not enough to need exponential backoff.

3. **Validation error formatting for LM**
   - What we know: Pass validation error back to LM for self-correction
   - What's unclear: Exact format that helps LM understand the issue
   - Recommendation (Claude's Discretion): Extract key info from AdapterParseError: "Expected fields: X, Y. Got: Z. LM response: [truncated]". Keep it under ~200 chars.

## Sources

### Primary (HIGH confidence)
- `/Users/dzaramelcone/lab/bae/.venv/lib/python3.14/site-packages/dspy/predict/predict.py` - Predict module implementation
- `/Users/dzaramelcone/lab/bae/.venv/lib/python3.14/site-packages/dspy/adapters/json_adapter.py` - Parse error handling
- `/Users/dzaramelcone/lab/bae/.venv/lib/python3.14/site-packages/dspy/utils/exceptions.py` - AdapterParseError class
- `/Users/dzaramelcone/lab/bae/.venv/lib/python3.14/site-packages/incant/__init__.py` - Incanter API
- [DSPy Predict API](https://dspy.ai/api/modules/Predict/) - Official module documentation
- [incant Usage](https://incant.threeofwands.com/en/stable/usage.html) - Official incant docs

### Secondary (MEDIUM confidence)
- [DSPy Refine API](https://dspy.ai/api/modules/Refine/) - Feedback injection pattern (adapted for our retry wrapper)
- [DSPy Cheatsheet](https://dspy.ai/cheatsheet/) - Quick reference patterns
- [GitHub Tinche/incant](https://github.com/Tinche/incant) - Repository examples

### Tertiary (LOW confidence)
- WebSearch results on DSPy error handling - confirmed assertions are deprecated

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Direct source code inspection of installed packages
- Architecture patterns: HIGH - Verified against DSPy source and incant implementation
- Pitfalls: HIGH - Derived from source code analysis of actual error paths

**Research date:** 2026-02-04
**Valid until:** 2026-03-04 (DSPy is actively developed but Predict API is stable; incant API is stable)
