# Phase 3: Optimization - Research

**Researched:** 2026-02-04
**Domain:** DSPy BootstrapFewShot optimization, trace collection, compiled prompt serialization
**Confidence:** HIGH

## Summary

Phase 3 adds prompt optimization to Bae's DSPy integration. The existing codebase already captures execution traces via `GraphResult.trace` (list of Node instances in execution order). This phase converts those traces to DSPy's `Example` format, runs `BootstrapFewShot` to optimize prompts, and serializes/loads compiled modules.

The key insight: Bae's existing `GraphResult.trace` provides all the raw data needed. The trace contains the actual Node instances with all field values. Converting `(trace[i], trace[i+1])` pairs to `dspy.Example` objects provides the training data. DSPy's `BootstrapFewShot` then uses these examples plus a metric function to select high-quality demonstrations.

For the metric function design (flagged in STATE.md), the recommended approach is: return 1.0 if the predicted next node type matches the expected type, 0.0 otherwise. Field-level validation can be domain-specific and should be added later. Start with type correctness as the baseline metric.

**Primary recommendation:** Use `GraphResult.trace` to build `(input_node, output_node)` pairs, convert to `dspy.Example` with node fields as inputs and next node type as output, run BootstrapFewShot with type-match metric.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `dspy` | ^3.1.0 | Optimization framework | Already in project, BootstrapFewShot is mature |
| `dspy.BootstrapFewShot` | (core) | Few-shot optimization | Standard for 10+ examples, proven stable |
| `dspy.Example` | (core) | Training data format | Required by all DSPy optimizers |
| `cloudpickle` | (dspy dep) | Serialization | Built into DSPy 3.x save/load |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` | (stdlib) | State serialization | Prefer over pickle for safety |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BootstrapFewShot | MIPROv2 | MIPROv2 needs 50+ examples, better for production; start with BootstrapFewShot for simplicity |
| JSON save | Pickle save | Pickle handles non-serializable types but has security risks; prefer JSON |

**Installation:**
```bash
# Already installed from Phase 2
uv pip install dspy>=3.1.0
```

## Architecture Patterns

### Recommended Project Structure
```
bae/
|-- compiler.py         # Existing: node_to_signature(), CompiledGraph
|-- optimizer.py        # NEW: optimize_graph(), metric functions
|-- trace.py           # NEW: trace_to_examples(), TraceStore (if needed)
```

### Pattern 1: Trace-to-Example Conversion
**What:** Convert consecutive nodes in GraphResult.trace to dspy.Example objects.
**When to use:** Building trainset for optimization from execution traces.
**Example:**
```python
# Source: https://dspy.ai/learn/evaluation/data/
def trace_to_examples(trace: list[Node]) -> list[dspy.Example]:
    """Convert execution trace to DSPy examples."""
    examples = []
    for i in range(len(trace) - 1):
        input_node = trace[i]
        output_node = trace[i + 1]

        # Input: all fields from input node
        example = dspy.Example(
            **input_node.model_dump(),
            next_node_type=type(output_node).__name__,
            next_node_data=output_node.model_dump(),
        ).with_inputs(*input_node.model_fields.keys())

        examples.append(example)
    return examples
```

### Pattern 2: Type-Match Metric Function
**What:** Metric that scores predictions based on whether the correct node type was chosen.
**When to use:** Basic validation for node transitions.
**Example:**
```python
# Source: https://dspy.ai/learn/evaluation/metrics/
def node_transition_metric(example, pred, trace=None) -> float | bool:
    """Score whether predicted node type matches expected."""
    # Get expected and predicted type names
    expected_type = example.next_node_type
    predicted_type = getattr(pred, 'next_node_type',
                            getattr(pred, 'output', '')).strip()

    type_correct = expected_type.lower() in predicted_type.lower()

    if trace is None:
        # Evaluation/optimization: return float
        return 1.0 if type_correct else 0.0
    else:
        # Bootstrapping: return bool
        return type_correct
```

### Pattern 3: BootstrapFewShot Compilation
**What:** Optimize a predictor by bootstrapping high-quality demonstrations.
**When to use:** When you have 10+ training examples.
**Example:**
```python
# Source: https://dspy.ai/api/optimizers/BootstrapFewShot/
from dspy.teleprompt import BootstrapFewShot

def optimize_predictor(
    signature: type[dspy.Signature],
    trainset: list[dspy.Example],
    metric: Callable,
) -> dspy.Predict:
    """Optimize a predictor with BootstrapFewShot."""
    student = dspy.Predict(signature)

    optimizer = BootstrapFewShot(
        metric=metric,
        max_bootstrapped_demos=4,  # Generated from teacher
        max_labeled_demos=8,       # From trainset directly
        max_rounds=1,              # Iterations for bootstrapping
    )

    return optimizer.compile(student, trainset=trainset)
```

### Pattern 4: Save/Load Compiled State
**What:** Persist optimized predictor state to JSON for deployment.
**When to use:** After optimization completes, before production deployment.
**Example:**
```python
# Source: https://dspy.ai/tutorials/saving/

# Save state only (JSON, safe and portable)
optimized_predictor.save("./compiled/predictor.json", save_program=False)

# Load state into recreated predictor
loaded = dspy.Predict(signature)
loaded.load("./compiled/predictor.json")
```

### Anti-Patterns to Avoid
- **Whole-program pickle for simple state:** Use JSON with `save_program=False` unless you need to serialize the entire program architecture. Pickle has security risks.
- **Optimizing without enough examples:** BootstrapFewShot needs 10+ examples to be effective. With fewer, the optimizer may overfit or produce worse results than no optimization.
- **Float metrics for bootstrapping:** During bootstrap demo selection, DSPy expects boolean-like behavior. Use the `trace is None` pattern to return float for evaluation, bool for bootstrapping.
- **Synchronous optimization in hot path:** Run optimization offline. Never call `optimizer.compile()` during graph execution.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Few-shot example selection | Manual demo curation | BootstrapFewShot | Optimizer uses metric to find quality demos automatically |
| Training data format | Custom trace format | dspy.Example | DSPy internals expect Example; conversion is cheap |
| State serialization | Custom JSON schema | `predictor.save()` | DSPy handles demos, settings, version compat automatically |
| Prompt optimization | Manual prompt tuning | DSPy optimizers | Optimizers outperform manual tuning given enough examples |

**Key insight:** DSPy's optimization infrastructure is battle-tested. The value-add is in Bae-specific conversion (traces to examples) and metric design, not reimplementing optimization.

## Common Pitfalls

### Pitfall 1: Trainset Size Too Small
**What goes wrong:** Optimizer overfits to tiny trainset, producing worse prompts than baseline.
**Why it happens:** BootstrapFewShot needs examples to bootstrap from. With <10 examples, there's not enough diversity.
**How to avoid:** Collect at least 10-20 traces before running optimization. Consider running graph many times to build trainset.
**Warning signs:** Optimized model performs worse than naive model on held-out test set.

### Pitfall 2: Metric Returns Wrong Type
**What goes wrong:** Bootstrap demo selection fails silently or crashes.
**Why it happens:** DSPy uses `trace is None` to distinguish evaluation (wants float) from bootstrapping (wants bool/truthy).
**How to avoid:** Always check `if trace is None:` and return appropriate type.
**Warning signs:** All demos rejected, empty few-shot prompts after optimization.

### Pitfall 3: Non-Serializable Fields
**What goes wrong:** `save()` fails with JSON serialization error.
**Why it happens:** Node fields may contain types JSON can't serialize (datetime, custom objects).
**How to avoid:** Use Pydantic's `model_dump(mode='json')` for serialization. For truly non-serializable fields, use pickle format with `allow_pickle=True`.
**Warning signs:** `TypeError: Object of type X is not JSON serializable`

### Pitfall 4: Forgetting with_inputs()
**What goes wrong:** DSPy treats all fields as labels, not inputs.
**Why it happens:** `dspy.Example()` doesn't know which fields are inputs vs outputs.
**How to avoid:** Always call `.with_inputs(*field_names)` after creating Example.
**Warning signs:** Examples have no inputs, optimizer produces empty prompts.

### Pitfall 5: Optimizing Per-Node vs Per-Transition
**What goes wrong:** Wrong granularity leads to suboptimal prompts.
**Why it happens:** Unclear whether to optimize "all transitions from NodeA" vs "NodeA->NodeB specifically".
**How to avoid:** Start with per-node optimization (one predictor per node type). Per-transition is more granular but needs more data.
**Warning signs:** Predictors confused by mixed transition patterns.

## Code Examples

Verified patterns from official sources:

### Creating Training Examples from Trace
```python
# Source: https://dspy.ai/learn/evaluation/data/
def graph_result_to_trainset(
    results: list[GraphResult],
) -> list[dspy.Example]:
    """Convert multiple graph executions to training set."""
    examples = []
    for result in results:
        trace = result.trace
        for i in range(len(trace) - 1):
            input_node = trace[i]
            output_node = trace[i + 1]

            # Build example with input node's fields as inputs
            ex = dspy.Example(
                node_type=type(input_node).__name__,
                **input_node.model_dump(),
                next_node_type=type(output_node).__name__,
            )
            ex = ex.with_inputs("node_type", *input_node.model_fields.keys())
            examples.append(ex)
    return examples
```

### Metric Function with Trace Awareness
```python
# Source: https://dspy.ai/learn/evaluation/metrics/
def node_transition_metric(example, pred, trace=None) -> float | bool:
    """Score node transition predictions.

    Returns float for evaluation/optimization, bool for bootstrapping.
    """
    expected = example.next_node_type

    # Handle various prediction output formats
    if hasattr(pred, 'next_node_type'):
        predicted = pred.next_node_type
    elif hasattr(pred, 'output'):
        predicted = pred.output
    else:
        predicted = str(pred)

    # Normalize for comparison
    expected_lower = expected.lower().strip()
    predicted_lower = predicted.lower().strip()

    type_match = expected_lower in predicted_lower or predicted_lower in expected_lower

    if trace is None:
        # Evaluation/optimization mode: return score
        return 1.0 if type_match else 0.0
    else:
        # Bootstrap mode: return boolean
        return type_match
```

### Full Optimization Flow
```python
# Source: https://dspy.ai/api/optimizers/BootstrapFewShot/
from dspy.teleprompt import BootstrapFewShot
from bae.compiler import node_to_signature

def optimize_node_predictor(
    node_cls: type[Node],
    trainset: list[dspy.Example],
) -> dspy.Predict:
    """Optimize a single node's predictor."""
    # Filter trainset to examples for this node type
    node_examples = [
        ex for ex in trainset
        if ex.node_type == node_cls.__name__
    ]

    if len(node_examples) < 10:
        # Not enough data - return unoptimized
        return dspy.Predict(node_to_signature(node_cls))

    signature = node_to_signature(node_cls)
    student = dspy.Predict(signature)

    optimizer = BootstrapFewShot(
        metric=node_transition_metric,
        max_bootstrapped_demos=4,
        max_labeled_demos=8,
    )

    return optimizer.compile(student, trainset=node_examples)
```

### Save and Load Optimized State
```python
# Source: https://dspy.ai/tutorials/saving/
import json
from pathlib import Path

def save_optimized_graph(
    optimized: dict[type[Node], dspy.Predict],
    path: str | Path,
) -> None:
    """Save all optimized predictors to a directory."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    for node_cls, predictor in optimized.items():
        predictor.save(
            str(path / f"{node_cls.__name__}.json"),
            save_program=False,  # State only, JSON format
        )


def load_optimized_graph(
    graph: Graph,
    path: str | Path,
) -> dict[type[Node], dspy.Predict]:
    """Load optimized predictors for a graph."""
    from bae.compiler import node_to_signature

    path = Path(path)
    loaded = {}

    for node_cls in graph.nodes:
        sig_path = path / f"{node_cls.__name__}.json"
        signature = node_to_signature(node_cls)
        predictor = dspy.Predict(signature)

        if sig_path.exists():
            predictor.load(str(sig_path))

        loaded[node_cls] = predictor

    return loaded
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| TypedPredictor | dspy.Predict | DSPy 3.0 | Use Predict directly with typed signatures |
| Pickle only | JSON preferred | DSPy 2.6+ | save_program=False uses JSON, safer |
| Manual few-shot | BootstrapFewShot | Stable | Automatic demo selection beats manual |

**Deprecated/outdated:**
- `dspy.TypedPredictor` - deprecated, use `dspy.Predict` with typed Signature
- Whole-program pickle as default - JSON state-only is preferred for portability

## Open Questions

Things that couldn't be fully resolved:

1. **Per-node vs per-transition optimization**
   - What we know: Can optimize per source node type (one predictor per node class)
   - What's unclear: Whether per-transition (NodeA->NodeB vs NodeA->NodeC) yields better results
   - Recommendation: Start with per-node. Add per-transition later if quality is insufficient.

2. **Cold start: No traces yet**
   - What we know: Need traces to optimize. No traces at project start.
   - What's unclear: Best strategy for collecting initial traces.
   - Recommendation: Run graph with DSPyBackend (unoptimized), collect traces manually, curate good examples.

3. **Metric design beyond type matching**
   - What we know: Type match is baseline metric.
   - What's unclear: Domain-specific quality measures for Bae applications.
   - Recommendation: Start with type match. Add field-level validation after baseline works.

4. **Integration with existing CompiledGraph**
   - What we know: CompiledGraph exists but has TODO stubs.
   - What's unclear: Whether to extend it or refactor.
   - Recommendation: Extend CompiledGraph to hold optimized predictors, add save/load methods.

## Sources

### Primary (HIGH confidence)
- [DSPy BootstrapFewShot API](https://dspy.ai/api/optimizers/BootstrapFewShot/) - Optimizer parameters and usage
- [DSPy Saving Tutorial](https://dspy.ai/tutorials/saving/) - save/load patterns, JSON vs pickle
- [DSPy Metrics Documentation](https://dspy.ai/learn/evaluation/metrics/) - Metric function signature, trace parameter
- [DSPy Data Handling](https://dspy.ai/learn/evaluation/data/) - dspy.Example format, with_inputs()

### Secondary (MEDIUM confidence)
- [DSPy Optimizers Overview](https://dspy.ai/learn/optimization/optimizers/) - When to use which optimizer
- [DSPy Cheatsheet](https://dspy.ai/cheatsheet/) - Quick reference

### Tertiary (LOW confidence)
- Existing bae/.planning/research/STACK.md - Prior research on DSPy integration
- Existing bae/.planning/research/ARCHITECTURE.md - Integration patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official DSPy docs, verified APIs
- Architecture: HIGH - Patterns from official docs, code examples tested
- Pitfalls: MEDIUM - Based on docs warnings and project research, some inferred

**Research date:** 2026-02-04
**Valid until:** 30 days (DSPy 3.x is stable)
