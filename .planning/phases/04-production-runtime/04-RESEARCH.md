# Phase 4: Production Runtime - Research

**Researched:** 2026-02-05
**Domain:** DSPy production deployment, optimized predictor loading, LM wrapper pattern
**Confidence:** HIGH

## Summary

Phase 4 enables production graphs to use compiled prompts. The existing codebase has:
- `DSPyBackend` with `make()` and `decide()` methods that create fresh `dspy.Predict` instances per call
- `load_optimized()` that loads predictor state from JSON into `dspy.Predict` instances
- `CompiledGraph` that holds optimized predictors in an `optimized` dict after calling `optimize()` or `load()`

The gap: `DSPyBackend` creates fresh predictors each time, discarding any loaded optimization. Phase 4 creates an `OptimizedLM` wrapper that:
1. Receives pre-loaded optimized predictors at construction
2. Uses optimized predictor when available for a node type
3. Falls back to fresh predictor (naive prompts) when no optimized version exists
4. Tracks which path was taken for observability

The implementation is straightforward: modify `DSPyBackend` (or create a subclass/wrapper) to accept a dict of optimized predictors and look them up by node type before creating fresh ones.

**Primary recommendation:** Create `OptimizedLM` that wraps or extends `DSPyBackend`, accepts optimized predictors dict, and provides fallback + observability.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `dspy` | ^3.1.0 | Already in project | Predictor state loading is built-in |
| `bae.dspy_backend.DSPyBackend` | existing | Base LM implementation | Already implements make/decide pattern |
| `bae.optimizer.load_optimized` | existing | Load predictor state | Already creates predictors with loaded state |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `logging` | (stdlib) | Observability | Track optimized vs naive path |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extend DSPyBackend | Wrap DSPyBackend | Extending is cleaner, wrapping allows swapping backends |
| logging module | Custom callback | Logging is simpler, callbacks more flexible |

**Installation:**
```bash
# No new dependencies - uses existing dspy and bae modules
```

## Architecture Patterns

### Recommended Project Structure
```
bae/
|-- dspy_backend.py     # Existing: DSPyBackend with make/decide
|-- optimized_lm.py     # NEW: OptimizedLM wrapper with pre-loaded predictors
|-- optimizer.py        # Existing: load_optimized() function
|-- compiler.py         # Existing: CompiledGraph with optimized dict
```

### Pattern 1: OptimizedLM with Predictor Registry
**What:** An LM implementation that holds pre-loaded optimized predictors and uses them when available.
**When to use:** Production runtime where compiled prompts should be used.
**Example:**
```python
# Source: Pattern derived from DSPy save/load tutorial + existing DSPyBackend
from bae.lm import LM
from bae.node import Node
import dspy

class OptimizedLM:
    """LM backend that uses pre-loaded optimized predictors when available."""

    def __init__(
        self,
        optimized: dict[type[Node], dspy.Predict] | None = None,
    ):
        """Initialize with optional optimized predictors.

        Args:
            optimized: Dict mapping node classes to their optimized predictors.
                       If None or empty, all calls use naive (fresh) predictors.
        """
        self.optimized = optimized or {}
        # Track observability: node_type -> "optimized" | "naive"
        self.usage_log: list[tuple[str, str]] = []

    def _get_predictor(self, node_cls: type[Node]) -> tuple[dspy.Predict, str]:
        """Get predictor for node type, returning (predictor, source)."""
        if node_cls in self.optimized:
            return self.optimized[node_cls], "optimized"

        # Fallback: create fresh predictor
        from bae.compiler import node_to_signature
        signature = node_to_signature(node_cls)
        return dspy.Predict(signature), "naive"

    def make(self, node: Node, target: type[T]) -> T:
        """Produce target using optimized predictor if available."""
        predictor, source = self._get_predictor(target)
        self.usage_log.append((target.__name__, source))

        # Use predictor (same logic as DSPyBackend.make)
        inputs = self._build_inputs(node)
        result = predictor(**inputs)
        return self._parse_output(result.output, target)

    def decide(self, node: Node) -> Node | None:
        """Decide using optimized predictor if available."""
        # ... similar pattern ...
```

### Pattern 2: Factory Function for Production LM
**What:** A function that creates an OptimizedLM from saved state.
**When to use:** Startup of production graphs.
**Example:**
```python
# Source: Combines existing load_optimized with new OptimizedLM
from bae.optimizer import load_optimized
from bae.graph import Graph
from pathlib import Path

def create_optimized_lm(
    graph: Graph,
    compiled_path: str | Path,
) -> OptimizedLM:
    """Create an OptimizedLM with loaded predictors for a graph.

    Args:
        graph: The graph whose nodes need predictors.
        compiled_path: Directory containing compiled predictor JSON files.

    Returns:
        OptimizedLM ready for production use.
    """
    optimized = load_optimized(list(graph.nodes), Path(compiled_path))
    return OptimizedLM(optimized=optimized)
```

### Pattern 3: CompiledGraph.run() Integration
**What:** CompiledGraph can run with its loaded optimized predictors.
**When to use:** When CompiledGraph is the production entry point.
**Example:**
```python
# Source: Extends existing CompiledGraph pattern
class CompiledGraph:
    # ... existing code ...

    def run(self, start_node: Node, **deps) -> GraphResult:
        """Run the compiled graph using optimized predictors."""
        # Create OptimizedLM from loaded predictors
        lm = OptimizedLM(optimized=self.optimized)

        # Delegate to Graph.run() with the optimized LM
        return self.graph.run(start_node, lm=lm, **deps)
```

### Anti-Patterns to Avoid
- **Creating fresh predictors when optimized available:** The whole point of Phase 4 is to USE the loaded predictors. Don't accidentally bypass them.
- **Loading predictors on every call:** Load once at startup, reuse the loaded predictors. Loading is I/O.
- **Silent fallback without logging:** If falling back to naive, log it so users can identify missing optimizations.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Predictor state loading | Custom JSON parsing | `dspy.Predict.load()` | DSPy handles version compat, format |
| Node-to-signature | Manual field extraction | `node_to_signature()` | Already implemented, tested |
| Predictor caching | Custom cache | Dict lookup in OptimizedLM | Simple, predictable |

**Key insight:** The hard work is already done. Phase 3 built the save/load infrastructure. Phase 4 just needs to wire loaded predictors into the LM calls.

## Common Pitfalls

### Pitfall 1: Forgetting to Inherit DSPyBackend Behavior
**What goes wrong:** OptimizedLM missing retry logic, self-correction, two-step decide.
**Why it happens:** Writing OptimizedLM from scratch instead of building on DSPyBackend.
**How to avoid:** Either subclass DSPyBackend and override predictor creation, or delegate to a DSPyBackend instance.
**Warning signs:** Parse errors not retried, API errors not handled, union types not working.

### Pitfall 2: Type Mismatch in Optimized Dict Keys
**What goes wrong:** Lookup fails because dict uses different type reference.
**Why it happens:** Python class identity vs equality. `SomeNode` imported in one module may be different object than `SomeNode` from another.
**How to avoid:** Use consistent imports. Test that loaded keys match expected keys. Consider using class name strings as backup lookup.
**Warning signs:** All calls falling back to naive even though optimized dict is populated.

### Pitfall 3: Missing Nodes in Optimized Dict
**What goes wrong:** No fallback, runtime error when node type not in dict.
**Why it happens:** New node added after optimization, or load_optimized called with incomplete node list.
**How to avoid:** Always have fallback path to fresh predictor. Never KeyError on missing node.
**Warning signs:** KeyError during production graph execution.

### Pitfall 4: Not Logging Fallback Usage
**What goes wrong:** Production seems fine but using naive prompts everywhere.
**Why it happens:** Fallback is silent, no observability.
**How to avoid:** Log every make/decide call with source (optimized/naive). Expose usage stats.
**Warning signs:** Can't answer "which nodes are optimized?" in production.

### Pitfall 5: Mutable State Between Calls
**What goes wrong:** Predictor state mutates, corrupting future calls.
**Why it happens:** DSPy predictors may accumulate traces or modify demos during calls.
**How to avoid:** Research whether `dspy.Predict` mutates on call. If so, consider cloning or resetting.
**Warning signs:** Different results from same input over time.

## Code Examples

Verified patterns from official sources and existing codebase:

### Using Loaded Predictor State
```python
# Source: https://dspy.ai/tutorials/saving/
# The loaded predictor has demos from optimization
loaded_predictor = dspy.Predict(signature)
loaded_predictor.load("./compiled/MyNode.json")

# Call it - uses the loaded few-shot demos
result = loaded_predictor(input="some input")
```

### Checking Predictor Source
```python
# Source: Derived from DSPyBackend pattern
def make_with_observability(
    self,
    node: Node,
    target: type[T],
) -> tuple[T, str]:
    """Make target and return (result, source) tuple."""
    predictor, source = self._get_predictor(target)

    # Log for observability
    logger.info(f"make({target.__name__}): using {source} predictor")

    # ... execute predictor ...
    return result, source
```

### Full OptimizedLM Implementation Skeleton
```python
# Source: Combines DSPyBackend pattern with optimized lookup
from bae.dspy_backend import DSPyBackend
from bae.node import Node
import dspy
import logging

logger = logging.getLogger(__name__)

class OptimizedLM(DSPyBackend):
    """DSPyBackend that uses pre-loaded optimized predictors when available."""

    def __init__(
        self,
        optimized: dict[type[Node], dspy.Predict] | None = None,
        max_retries: int = 1,
    ):
        super().__init__(max_retries=max_retries)
        self.optimized = optimized or {}
        self.stats = {"optimized": 0, "naive": 0}

    def _get_predictor_for_target(self, target: type[Node]) -> dspy.Predict:
        """Get predictor for target type, preferring optimized."""
        if target in self.optimized:
            self.stats["optimized"] += 1
            logger.debug(f"Using optimized predictor for {target.__name__}")
            return self.optimized[target]

        # Fallback to fresh predictor
        self.stats["naive"] += 1
        logger.debug(f"Using naive predictor for {target.__name__}")
        from bae.compiler import node_to_signature
        return dspy.Predict(node_to_signature(target))

    def make(self, node: Node, target: type[T]) -> T:
        """Produce target using optimized predictor if available."""
        predictor = self._get_predictor_for_target(target)
        inputs = self._build_inputs(node)

        # Rest is same as DSPyBackend.make() retry logic
        last_error = None
        for attempt in range(self.max_retries + 1):
            error_hint = str(last_error) if last_error else None
            try:
                result = self._call_with_retry(predictor, inputs, error_hint)
                return self._parse_output(result.output, target)
            except ValueError as e:
                last_error = e
                if attempt < self.max_retries:
                    continue
                from bae.exceptions import BaeParseError
                raise BaeParseError(str(e), cause=e) from e

        raise BaeParseError("Unexpected", cause=last_error)

    def get_stats(self) -> dict[str, int]:
        """Return usage statistics."""
        return self.stats.copy()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fresh predictors per call | Load optimized once, reuse | DSPy 2.6+ | Significant prompt quality improvement |
| Pickle for state | JSON with save_program=False | DSPy 2.6+ | Safer, portable |
| No fallback handling | Graceful degradation | Best practice | More robust production |

**Deprecated/outdated:**
- Creating `dspy.Predict` fresh for every LM call is now suboptimal when optimized versions exist

## Open Questions

Things that couldn't be fully resolved:

1. **Predictor mutation on call**
   - What we know: `dspy.Predict` has `traces` attribute that accumulates
   - What's unclear: Whether production calls mutate state that affects subsequent calls
   - Recommendation: Test behavior. If mutation is a problem, either reset after each call or clone predictors

2. **Choice predictor optimization**
   - What we know: `decide()` uses a separate choice predictor for type selection
   - What's unclear: Whether the choice predictor should also be optimized
   - Recommendation: Start with only target predictors optimized. Add choice optimization later if beneficial.

3. **Observability format**
   - What we know: Need to track optimized vs naive usage
   - What's unclear: Best format for production (metrics, logs, both?)
   - Recommendation: Start with simple dict counter + debug logs. Add structured metrics later.

## Sources

### Primary (HIGH confidence)
- [DSPy Saving Tutorial](https://dspy.ai/tutorials/saving/) - save/load patterns, JSON format
- [DSPy Predict API](https://dspy.ai/api/modules/Predict/) - Predictor interface, demos, state
- [DSPy Cheatsheet](https://dspy.ai/cheatsheet/) - Loading compiled programs pattern
- [DSPy Production Guide](https://dspy.ai/production/) - Production deployment context
- Existing `bae/dspy_backend.py` - Current make/decide implementation
- Existing `bae/optimizer.py` - load_optimized() function

### Secondary (MEDIUM confidence)
- [DSPy Custom Module Tutorial](https://dspy.ai/tutorials/custom_module/) - Integration patterns

### Tertiary (LOW confidence)
- None - research primarily from official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Uses existing bae modules and DSPy patterns from official docs
- Architecture: HIGH - Pattern follows directly from existing DSPyBackend + official save/load
- Pitfalls: MEDIUM - Some inferred from code structure, not explicitly documented

**Research date:** 2026-02-05
**Valid until:** 30 days (DSPy 3.x stable, bae patterns established)
