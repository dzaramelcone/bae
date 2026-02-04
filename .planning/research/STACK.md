# Technology Stack: DSPy Compilation for Bae

**Project:** Bae - Type-driven agent graphs with DSPy optimization
**Researched:** 2026-02-04
**Focus:** DSPy prompt compilation/optimization stack

## Executive Summary

DSPy 3.1.x (current: 3.1.2) provides mature patterns for compiling Pydantic models into optimized prompts. The key integration path: convert Bae's `Node` classes to DSPy `Signature` classes, using class names and docstrings as prompt instructions and field descriptions as hints. Optimizers like `BootstrapFewShot` and `MIPROv2` can then tune these prompts from traced executions.

**Critical insight:** DSPy's `ChatAdapter` (default) already handles Pydantic `BaseModel` types natively. Bae nodes extend `pydantic.BaseModel`, so the integration is structurally aligned.

---

## Recommended Stack

### Core DSPy Components

| Component | Version | Purpose | Why |
|-----------|---------|---------|-----|
| `dspy` | ^3.1.0 | Prompt optimization framework | Current stable, supports Pydantic natively |
| `dspy.Predict` | (core) | LLM invocation with structured output | Replaces deprecated `TypedPredictor` |
| `dspy.Signature` | (core) | Declarative input/output specification | Maps directly to Node class structure |
| `dspy.ChatAdapter` | (default) | Translates signatures to LLM prompts | Handles Pydantic BaseModel automatically |

### Optimizers (Pick Based on Data Availability)

| Optimizer | Data Needed | What it Optimizes | Use Case |
|-----------|-------------|-------------------|----------|
| `BootstrapFewShot` | 10+ examples | Few-shot examples only | Quick iteration, minimal data |
| `MIPROv2(auto="light")` | 50+ examples | Instructions + examples | Production-ready prompts |
| `MIPROv2(auto="medium")` | 200+ examples | Deep optimization | High-stakes deployments |

### Supporting Infrastructure

| Component | Purpose | Notes |
|-----------|---------|-------|
| `cloudpickle` | Serialize compiled programs | Built into DSPy 3.x save/load |
| `litellm` | Multi-provider LLM backend | DSPy's recommended LM abstraction |

---

## Integration Pattern: Node to Signature

### The Core Mapping

Bae `Node` classes map to DSPy `Signature` classes:

```python
# Bae Node (existing)
class AnalyzeRequest(Node):
    """Analyze user request and determine intent."""
    request: str
    context: str = ""

    def __call__(self, lm: LM) -> GenerateCode | Clarify:
        return lm.decide(GenerateCode | Clarify)

# DSPy Signature (generated at compile time)
class AnalyzeRequestSignature(dspy.Signature):
    """Analyze user request and determine intent."""
    request: str = dspy.InputField()
    context: str = dspy.InputField(desc="Additional context")
    next_node_type: str = dspy.OutputField(desc="One of: GenerateCode, Clarify")
    # Plus fields for the chosen output type
```

### Conversion Strategy

1. **Class name** becomes signature name (prompt identity)
2. **Docstring** becomes signature docstring (main instruction)
3. **Node fields** become `InputField` entries (current state)
4. **Return type hint** informs `OutputField` structure (decision + construction)
5. **Field descriptions** from Pydantic `Field(description=...)` transfer to DSPy `desc=`

### Implementation Approach

```python
import dspy
from pydantic.fields import FieldInfo

def node_to_signature(node_cls: type[Node]) -> type[dspy.Signature]:
    """Convert a Node class to a DSPy Signature class."""

    # Build input fields from node's Pydantic fields
    input_fields = {}
    for name, field_info in node_cls.model_fields.items():
        input_fields[name] = dspy.InputField(
            desc=field_info.description or ""
        )

    # Build output fields from return type
    successors = node_cls.successors()
    if len(successors) > 1:
        # Decision node: output is type selection + fields
        output_fields = {
            "next_node_type": dspy.OutputField(
                desc=f"One of: {', '.join(s.__name__ for s in successors)}"
            )
        }
    elif len(successors) == 1:
        # Single successor: output is that node's fields
        successor = next(iter(successors))
        output_fields = _fields_for_node(successor)
    else:
        # Terminal: no output fields (or completion signal)
        output_fields = {}

    # Create signature class dynamically
    return dspy.Signature(
        {**input_fields, **output_fields},
        instructions=node_cls.__doc__ or f"Process {node_cls.__name__}"
    )
```

---

## Traced Execution for Optimization

### Collecting Training Data

DSPy optimizers need `(input, output)` pairs. For Bae:

```python
from dataclasses import dataclass

@dataclass
class TraceStep:
    """One step in graph execution."""
    node: Node           # Input state
    next_node: Node | None  # Output (what LLM produced)

@dataclass
class ExecutionTrace:
    """Complete graph execution."""
    steps: list[TraceStep]
    success: bool        # Did it complete successfully?
    metric_score: float  # Quality metric
```

### Training Set Structure

```python
# DSPy Example format for a single node transition
example = dspy.Example(
    # Inputs (from current node's fields)
    request="Implement a fibonacci function",
    context="Python 3.14, no dependencies",
    # Outputs (the decision + constructed node)
    next_node_type="GenerateCode",
    task="Implement fibonacci function in Python 3.14",
    code=""  # Empty initially, LLM fills
).with_inputs("request", "context")
```

### Metric Function Pattern

```python
def graph_execution_metric(gold: dspy.Example, pred: dspy.Prediction, trace=None) -> float:
    """Evaluate a graph execution step."""
    # Type decision correctness
    type_correct = gold.next_node_type == pred.next_node_type

    # Field quality (if type matches)
    if type_correct:
        # Domain-specific quality checks
        field_score = evaluate_field_quality(gold, pred)
        return 0.5 + (0.5 * field_score)

    return 0.0  # Wrong type = failure
```

---

## Compilation Workflow

### Phase 1: Signature Generation (No Training Data Needed)

```python
def compile_graph_signatures(graph: Graph) -> dict[type[Node], type[dspy.Signature]]:
    """Generate DSPy signatures for all nodes in graph."""
    return {
        node_cls: node_to_signature(node_cls)
        for node_cls in graph.nodes
    }
```

### Phase 2: Unoptimized Execution (Collect Traces)

```python
class DSPyBackend(LM):
    """LM backend using DSPy Predict modules."""

    def __init__(self, signatures: dict[type[Node], type[dspy.Signature]]):
        self.predictors = {
            node_cls: dspy.Predict(sig)
            for node_cls, sig in signatures.items()
        }

    def make(self, node: Node, target: type[Node]) -> Node:
        predictor = self.predictors[type(node)]
        # Convert node fields to predictor inputs
        inputs = {name: getattr(node, name) for name in node.model_fields}
        result = predictor(**inputs)
        # Construct target node from prediction
        return target(**result.toDict())
```

### Phase 3: Optimization (With Training Data)

```python
def optimize_graph(
    graph: Graph,
    trainset: list[dspy.Example],
    metric: Callable,
    optimizer: str = "bootstrap"
) -> dict[type[Node], dspy.Predict]:
    """Optimize all node transitions."""

    signatures = compile_graph_signatures(graph)

    if optimizer == "bootstrap":
        opt = dspy.BootstrapFewShot(
            metric=metric,
            max_bootstrapped_demos=4,
            max_labeled_demos=8
        )
    elif optimizer == "mipro":
        opt = dspy.MIPROv2(
            metric=metric,
            auto="light"
        )

    optimized = {}
    for node_cls, sig in signatures.items():
        student = dspy.Predict(sig)
        # Filter trainset to examples for this node type
        node_examples = [ex for ex in trainset if ex.node_type == node_cls.__name__]
        if node_examples:
            optimized[node_cls] = opt.compile(student, trainset=node_examples)
        else:
            optimized[node_cls] = student

    return optimized
```

### Phase 4: Persistence

```python
def save_compiled_graph(optimized: dict, path: str):
    """Save compiled graph for deployment."""
    for node_cls, predictor in optimized.items():
        predictor.save(f"{path}/{node_cls.__name__}.json")

def load_compiled_graph(graph: Graph, path: str) -> dict:
    """Load previously compiled graph."""
    signatures = compile_graph_signatures(graph)
    loaded = {}
    for node_cls, sig in signatures.items():
        predictor = dspy.Predict(sig)
        predictor.load(f"{path}/{node_cls.__name__}.json")
        loaded[node_cls] = predictor
    return loaded
```

---

## What NOT to Use

| Avoid | Reason | Use Instead |
|-------|--------|-------------|
| `dspy.TypedPredictor` | Deprecated, issues deprecation warnings | `dspy.Predict` with Pydantic types in Signature |
| `dspy.TypedChainOfThought` | Also deprecated | `dspy.ChainOfThought` with typed Signature |
| Manual prompt strings | Defeats DSPy's optimization | Docstrings + field descriptions |
| `JSONAdapter` as default | More restrictive, fails on some models | `ChatAdapter` (default) with fallback |
| Pickle for saving | Security concerns, portability issues | JSON format (`.json` extension) |
| `MIPROv2(auto="heavy")` without 200+ examples | Overfits on small datasets | Start with `"light"`, scale up |

---

## Configuration Patterns

### DSPy Global Configuration

```python
import dspy

# Configure LM (uses litellm under the hood)
dspy.configure(
    lm=dspy.LM("anthropic/claude-sonnet-4-20250514"),
    adapter=dspy.ChatAdapter()  # Default, but explicit is good
)

# For Bae integration, configure per-node if needed
with dspy.context(lm=dspy.LM("anthropic/claude-3-5-haiku-20241022")):
    # Fast model for simple nodes
    result = simple_predictor(...)
```

### Per-Node Model Selection (Aligns with Bae's NodeConfig)

```python
# In Bae's NodeConfig
class NodeConfig(ConfigDict, total=False):
    model: str          # Maps to dspy.LM model name
    temperature: float  # Passed to dspy.LM

# At execution time
def get_lm_for_node(node_cls: type[Node]) -> dspy.LM:
    config = node_cls.model_config
    model = config.get("model", "anthropic/claude-sonnet-4-20250514")
    temp = config.get("temperature", 0.7)
    return dspy.LM(model, temperature=temp)
```

---

## Version Compatibility

| Package | Minimum | Recommended | Notes |
|---------|---------|-------------|-------|
| `dspy` | 3.0.0 | 3.1.2 | 3.x has stable Pydantic support |
| `pydantic` | 2.0 | 2.x (any) | Already in Bae |
| `pydantic-ai` | 0.1 | 0.x (any) | Separate concern, doesn't conflict |
| `litellm` | 1.0 | latest | DSPy's LM backend |
| Python | 3.10 | 3.14 | Bae requires 3.14 for PEP 649 |

---

## Confidence Assessment

| Claim | Confidence | Source |
|-------|------------|--------|
| `dspy.Predict` replaces `TypedPredictor` | HIGH | [DSPy docs](https://dspy.ai), [GitHub issues](https://github.com/stanfordnlp/dspy/issues/724) |
| `ChatAdapter` handles Pydantic BaseModel | HIGH | [DSPy Adapters docs](https://dspy.ai/learn/programming/adapters/) |
| Node-to-Signature conversion pattern | MEDIUM | Synthesized from [gist](https://gist.github.com/seanchatmangpt/7e25b66ebffdedba7310d9c90f377463), [PR #1655](https://github.com/stanfordnlp/dspy/pull/1655) |
| `BootstrapFewShot` for 10+ examples | HIGH | [DSPy Optimizers](https://dspy.ai/learn/optimization/optimizers/) |
| `MIPROv2(auto="light")` for 50+ | HIGH | [MIPROv2 docs](https://dspy.ai/api/optimizers/MIPROv2/) |
| JSON save format recommended | HIGH | [DSPy Saving Tutorial](https://dspy.ai/tutorials/saving/) |
| Multi-step graph optimization works | MEDIUM | [LangGraph+DSPy article](https://www.rajapatnaik.com/blog/2025/10/23/langgraph-dspy-gepa-researcher), [behavioral optimization](https://viksit.substack.com/p/behavioral-optimization-for-multi) |

---

## Open Questions for Implementation

1. **Two-phase decision in Bae:** Current Bae uses `lm.decide()` (pick type) then implicit construction. Does this map to one DSPy module or two?
   - Recommendation: Single module with union output type, let DSPy handle

2. **Trace collection hooks:** Where to inject trace collection in Bae's `Graph.run()`?
   - Recommendation: Decorator or context manager around node execution

3. **Metric design for graph quality:** What makes a "good" graph execution?
   - Recommendation: Start with type correctness, add domain-specific quality later

4. **Cold start problem:** No training data initially
   - Recommendation: Phase 1 uses docstrings only (zero-shot), collect traces, then Phase 2 optimizes

---

## Sources

### Primary (HIGH confidence)
- [DSPy Official Documentation](https://dspy.ai)
- [DSPy GitHub Repository](https://github.com/stanfordnlp/dspy) - v3.1.2 (Jan 2026)
- [DSPy Adapters Documentation](https://dspy.ai/learn/programming/adapters/)
- [DSPy Optimizers Documentation](https://dspy.ai/learn/optimization/optimizers/)
- [DSPy Cheatsheet](https://dspy.ai/cheatsheet/)

### Secondary (MEDIUM confidence)
- [TypedPredictor deprecation discussion](https://github.com/stanfordnlp/dspy/issues/724)
- [TypedPredictorSignature PR](https://github.com/stanfordnlp/dspy/pull/1655)
- [Pydantic to DSPy Signature gist](https://gist.github.com/seanchatmangpt/7e25b66ebffdedba7310d9c90f377463)
- [LangGraph + DSPy integration](https://www.rajapatnaik.com/blog/2025/10/23/langgraph-dspy-gepa-researcher)

### Contextual (LOW confidence - community patterns)
- [Behavioral optimization for multi-step agents](https://viksit.substack.com/p/behavioral-optimization-for-multi)
- [DSPydantic library](https://github.com/davidberenstein1957/dspydantic)
