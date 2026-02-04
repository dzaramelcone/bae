# Architecture Patterns: DSPy Compilation Integration

**Domain:** Agent graph framework with DSPy prompt optimization
**Researched:** 2026-02-04
**Confidence:** MEDIUM (Context7 unavailable for DSPy; verified against official docs at dspy.ai)

## Executive Summary

DSPy is a declarative framework that replaces prompt engineering with programmatic modules and automatic optimization. Integrating DSPy into Bae requires mapping Bae's existing abstractions (Node, Graph, LM protocol) to DSPy's abstractions (Signature, Module, Adapter, Optimizer).

The key insight: **DSPy doesn't replace your execution framework; it optimizes the prompts used during execution.** Bae's Graph runs the agent loop; DSPy optimizes what the LM sees at each step.

## Current Bae Architecture

```
                    +------------------+
                    |      Graph       |
                    | - _discover()    |
                    | - run()          |
                    | - validate()     |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
    +---------v---------+         +---------v---------+
    |       Node        |         |       Node        |
    | - fields (state)  |         | - fields (state)  |
    | - __call__(lm)    |         | - __call__(lm)    |
    | - successors()    |         | - successors()    |
    +---------+---------+         +---------+---------+
              |                             |
              +-------------+---------------+
                            |
                   +--------v--------+
                   |    LM Protocol  |
                   | - make(target)  |
                   | - decide(node)  |
                   +--------+--------+
                            |
              +-------------+-------------+
              |                           |
    +---------v---------+       +---------v---------+
    | PydanticAIBackend |       |  ClaudeCLIBackend |
    +-------------------+       +-------------------+
```

**Bae's strengths:**
- Type-driven topology from return type hints
- Clean separation: Node holds state, LM produces next state
- Pydantic models give automatic JSON schema
- Graph handles execution loop

**Bae's current prompt generation:**
- `_node_to_prompt()` converts node state to naive string
- Docstrings used as context (minimal)
- No few-shot examples
- No instruction optimization

## DSPy Architecture (How It Works)

### Core Abstractions

| DSPy Concept | What It Does | Bae Equivalent |
|--------------|--------------|----------------|
| **Signature** | Declares input/output contract | Node class fields + return type |
| **Module** | Wraps a prompting strategy (CoT, ReAct) | `lm.decide()` / `lm.make()` |
| **Adapter** | Formats signature -> LM messages | `_node_to_prompt()` |
| **Optimizer** | Tunes prompts/demos from examples | (none - this is what we're adding) |

### DSPy Data Flow

```
Signature (what)
     |
     v
Module (how) + dspy.settings.lm
     |
     v
Adapter.format() -> Messages
     |
     v
LiteLLM / LM call
     |
     v
Adapter.parse() -> Prediction
     |
     v
Optimizer evaluates against metric
     |
     v
Optimizer modifies Module parameters (demos, instructions)
```

### How DSPy Optimization Works

1. **Trace Collection:** Run program on training examples, capture I/O at each module
2. **Metric Evaluation:** Score each trace (did we get the right output?)
3. **Bootstrap/Search:** Keep high-scoring traces as few-shot examples OR search for better instructions
4. **Parameter Update:** Store optimized demos/instructions in module state
5. **Repeat:** Until convergence or budget exhausted

## Recommended Integration Architecture

### Layer Diagram

```
                        +---------------------------+
                        |        Graph.run()        |
                        |   (unchanged execution)   |
                        +-------------+-------------+
                                      |
                        +-------------v-------------+
                        |      Node.__call__()      |
                        |   (unchanged interface)   |
                        +-------------+-------------+
                                      |
                        +-------------v-------------+
                        |   OptimizedLM (new)       |
                        | wraps LM with DSPy        |
                        +-------------+-------------+
                                      |
              +-----------------------+-----------------------+
              |                                               |
    +---------v---------+                         +-----------v-----------+
    |   DSPy Module     |                         |   Fallback to raw LM  |
    | (if optimized)    |                         |   (if not optimized)  |
    +---------+---------+                         +-----------+-----------+
              |                                               |
              +-------------------+---------------------------+
                                  |
                        +---------v---------+
                        |  Underlying LM    |
                        | (via LiteLLM or   |
                        |  existing backend)|
                        +-------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `Graph` | Topology discovery, execution loop, validation | Node, LM |
| `Node` | State container, routing logic, type hints | LM (via `__call__`) |
| `LM` (Protocol) | Abstract interface for `make`/`decide` | Backends |
| `OptimizedLM` (NEW) | Wraps LM, routes through DSPy modules if optimized | DSPy modules, underlying LM |
| `NodeSignature` (NEW) | Converts Node class -> DSPy Signature | Node metadata |
| `Compiler` (REWRITE) | Extracts signatures, creates DSPy modules, runs optimizers | Graph, NodeSignature, DSPy |
| `CompiledGraph` (REWRITE) | Holds optimized modules, provides optimized LM | Graph, OptimizedLM |

### Data Flow for Tracing and Optimization

```
COMPILATION PHASE (offline):
============================

1. Graph introspection:
   Graph.nodes -> [NodeClass1, NodeClass2, ...]

2. Signature extraction:
   NodeClass -> NodeSignature -> dspy.Signature

   Fields: NodeClass.model_fields -> InputFields
   Output: NodeClass.successors() -> OutputFields (one per successor type)

3. Module creation:
   For each Node: dspy.Predict(signature) or dspy.ChainOfThought(signature)

4. Training data collection:
   User provides: [(input_node, expected_output_node), ...]

5. Optimization loop:
   optimizer.compile(program, trainset=examples, metric=metric)

   Internally:
   - Runs program on each example
   - Traces I/O through DSPy modules
   - Scores outputs against metric
   - Bootstraps high-scoring traces as demos
   - Searches for better instructions

6. Save optimized modules:
   compiled_graph.save("./optimized_prompts/")


EXECUTION PHASE (online):
=========================

1. Load optimized:
   compiled_graph = CompiledGraph.load("./optimized_prompts/")

2. Create optimized LM:
   lm = compiled_graph.get_optimized_lm(base_backend)

3. Run graph normally:
   graph.run(start_node, lm=lm)

   At each Node.__call__():
   - lm.decide(node) checks if DSPy module exists for this node
   - If yes: routes through DSPy module (with optimized demos/instructions)
   - If no: falls back to naive prompt generation
```

## Suggested Integration Points

### 1. Signature Extraction (Node -> dspy.Signature)

**Location:** `bae/compiler.py` (expand existing `node_to_signature()`)

**Approach:**
```python
def node_to_dspy_signature(node_cls: type[Node]) -> type[dspy.Signature]:
    """Convert a Bae Node class to a DSPy Signature class."""

    # Input fields from node's Pydantic fields
    input_fields = {}
    for name, field in node_cls.model_fields.items():
        input_fields[name] = dspy.InputField(
            desc=field.description or f"The {name}"
        )

    # Output field: which successor type to produce
    successors = node_cls.successors()
    if len(successors) == 1:
        # Single successor: output is that type's fields
        output_fields = _fields_from_node_cls(list(successors)[0])
    else:
        # Multiple successors: output is choice + fields
        output_fields = {
            "next_node_type": dspy.OutputField(desc=f"One of: {[s.__name__ for s in successors]}"),
            "next_node_data": dspy.OutputField(desc="JSON data for the chosen node type")
        }

    # Create dynamic Signature class
    sig_cls = type(
        f"{node_cls.__name__}Signature",
        (dspy.Signature,),
        {
            "__doc__": node_cls.__doc__ or f"Process {node_cls.__name__}",
            **input_fields,
            **output_fields
        }
    )
    return sig_cls
```

**Confidence:** MEDIUM - DSPy docs confirm dynamic Signature creation works, but Bae-specific edge cases (optional fields, complex types) need testing.

### 2. Module Creation Strategy

**Options:**

| Strategy | Pros | Cons | When to Use |
|----------|------|------|-------------|
| `dspy.Predict` | Simple, fast | No reasoning trace | Simple routing decisions |
| `dspy.ChainOfThought` | Better reasoning, more optimizable | Slower, more tokens | Complex decisions |
| `dspy.ProgramOfThought` | Can generate code | Needs execution sandbox | Code-generating nodes |

**Recommendation:** Default to `dspy.ChainOfThought` for nodes with multiple successors (decision points), `dspy.Predict` for nodes with single successor (transforms).

### 3. LM Integration Strategy

**Option A: Replace LM backends entirely with DSPy's LiteLLM**
- Pros: One LM abstraction, full DSPy compatibility
- Cons: Loses Bae's `ClaudeCLIBackend`, breaking change

**Option B: Wrap existing LM backends (RECOMMENDED)**
- Pros: Preserves existing backends, opt-in optimization
- Cons: Two LM abstractions to maintain

**Implementation for Option B:**

```python
class OptimizedLM:
    """LM wrapper that routes through DSPy modules when available."""

    def __init__(self, base_lm: LM, optimized_modules: dict[type[Node], dspy.Module] = None):
        self.base_lm = base_lm
        self.optimized_modules = optimized_modules or {}

    def make(self, node: Node, target: type[T]) -> T:
        # Optimization typically happens at decide(), not make()
        # Fall through to base
        return self.base_lm.make(node, target)

    def decide(self, node: Node) -> Node | None:
        node_cls = type(node)

        if node_cls in self.optimized_modules:
            # Route through DSPy
            module = self.optimized_modules[node_cls]
            inputs = node.model_dump()
            result = module(**inputs)
            return self._result_to_node(result, node_cls)
        else:
            # Fall back to unoptimized
            return self.base_lm.decide(node)
```

### 4. Training Data Format

DSPy expects `dspy.Example` objects. Define a conversion:

```python
def bae_trace_to_dspy_example(
    input_node: Node,
    output_node: Node | None
) -> dspy.Example:
    """Convert a Bae execution trace to a DSPy training example."""

    example = dspy.Example(
        # Inputs from source node
        **input_node.model_dump(),
        # Expected output
        next_node_type=type(output_node).__name__ if output_node else "None",
        next_node_data=output_node.model_dump() if output_node else {}
    ).with_inputs(*input_node.model_fields.keys())

    return example
```

### 5. Metric Definition

DSPy metrics score (example, prediction) pairs. For Bae:

```python
def node_transition_metric(example, prediction, trace=None) -> float:
    """Score whether the predicted node transition is correct."""

    # Did we choose the right successor type?
    type_correct = (
        prediction.next_node_type == example.next_node_type
    )

    if not type_correct:
        return 0.0

    # Did we produce correct field values?
    # (Could be fuzzy match, semantic similarity, etc.)
    if example.next_node_type == "None":
        return 1.0  # Terminal, type match is enough

    # Compare field values
    expected = example.next_node_data
    predicted = prediction.next_node_data

    matching_fields = sum(
        1 for k in expected if predicted.get(k) == expected[k]
    )
    return matching_fields / len(expected) if expected else 1.0
```

## Patterns to Follow

### Pattern 1: Lazy Optimization

**What:** Don't optimize all nodes upfront; optimize on-demand based on usage patterns.

**When:** Large graphs where only some paths are hot.

**Example:**
```python
class CompiledGraph:
    def optimize_node(self, node_cls: type[Node], examples: list) -> None:
        """Optimize a single node's prompts."""
        sig = node_to_dspy_signature(node_cls)
        module = dspy.ChainOfThought(sig)

        optimizer = dspy.BootstrapFewShot(metric=node_transition_metric)
        optimized = optimizer.compile(module, trainset=examples)

        self._optimized_modules[node_cls] = optimized
```

### Pattern 2: Adapter Preservation

**What:** Keep Bae's existing prompt generation as a fallback adapter.

**When:** DSPy optimization fails or isn't available.

**Example:**
```python
class BaeAdapter(dspy.Adapter):
    """Adapter that uses Bae's existing prompt generation."""

    def format(self, signature, demos, inputs):
        # Use Bae's _node_to_prompt() style
        ...

    def parse(self, signature, completion):
        # Use Bae's existing parsing
        ...
```

### Pattern 3: Trace-Based Bootstrapping

**What:** Collect real execution traces as training data, not synthetic examples.

**When:** You have production traffic to learn from.

**Example:**
```python
class TracingLM:
    """LM wrapper that records execution traces for later optimization."""

    def __init__(self, base_lm: LM, trace_store: TraceStore):
        self.base_lm = base_lm
        self.trace_store = trace_store

    def decide(self, node: Node) -> Node | None:
        result = self.base_lm.decide(node)

        # Record trace
        self.trace_store.record(
            input_node=node,
            output_node=result,
            timestamp=datetime.now()
        )

        return result
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Full Graph as Single Module

**What:** Trying to optimize the entire graph as one DSPy module.

**Why bad:** DSPy modules work best as atomic units. Whole-graph optimization loses granularity and makes debugging impossible.

**Instead:** One DSPy module per Node type. Each optimizes independently.

### Anti-Pattern 2: Replacing Pydantic with DSPy Types

**What:** Converting all Node fields to DSPy's built-in types.

**Why bad:** Loses Pydantic's validation, type coercion, and JSON schema generation.

**Instead:** Keep Pydantic for Node definitions. Extract to DSPy Signatures only for optimization.

### Anti-Pattern 3: Synchronous Optimization in Hot Path

**What:** Running `optimizer.compile()` during graph execution.

**Why bad:** Optimization is expensive (many LLM calls). Blocks execution for minutes.

**Instead:** Optimize offline. Load optimized modules at startup.

### Anti-Pattern 4: Ignoring DSPy's Caching

**What:** Disabling DSPy's LM cache or not considering it.

**Why bad:** Optimization makes many repeated calls. Without cache, costs explode.

**Instead:** Ensure cache is enabled during optimization. Clear only when needed.

## Phased Integration Roadmap

### Phase 1: Signature Extraction (Foundation)
- Implement `node_to_dspy_signature()` for all Node classes
- Validate signatures match Bae's type system
- **Deliverable:** Signatures for all nodes, no behavior change

### Phase 2: DSPy Module Creation
- Create `dspy.Predict` or `dspy.ChainOfThought` for each node
- Wire modules to use existing LM backend via custom adapter
- **Deliverable:** Modules that can be called but aren't optimized

### Phase 3: Training Data Pipeline
- Define `bae_trace_to_dspy_example()` conversion
- Implement `TraceStore` for collecting execution traces
- Define `node_transition_metric()`
- **Deliverable:** Ability to collect and score training data

### Phase 4: Optimization Loop
- Integrate `BootstrapFewShot` optimizer
- Implement save/load for optimized modules
- Create `OptimizedLM` wrapper
- **Deliverable:** End-to-end optimization working

### Phase 5: Production Integration
- Add `CompiledGraph.load()` for startup
- Implement fallback behavior for unoptimized nodes
- Add observability (which nodes optimized, cache hit rates)
- **Deliverable:** Production-ready compiled graphs

## Sources

**HIGH confidence (official documentation):**
- [DSPy Signatures](https://dspy.ai/learn/programming/signatures/) - Input/output contract definitions
- [DSPy Modules](https://dspy.ai/learn/programming/modules/) - Module architecture and composition
- [DSPy Adapters](https://dspy.ai/learn/programming/adapters/) - Adapter system for LM formatting
- [DSPy Optimizers](https://dspy.ai/learn/optimization/optimizers/) - Optimization algorithms
- [DSPy Language Models](https://dspy.ai/learn/programming/language_models/) - LM configuration

**MEDIUM confidence (verified secondary sources):**
- [DSPydantic](https://github.com/davidberenstein1957/dspydantic) - Pydantic-to-DSPy bridge pattern
- [DeepWiki DSPy Architecture](https://deepwiki.com/stanfordnlp/dspy) - Internal architecture details
- [MLflow DSPy Tracing](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/dspy/) - Trace capture mechanisms

**LOW confidence (community patterns, needs validation):**
- Custom adapter implementation details - official docs thin on this
- Multi-successor node handling - Bae-specific, no DSPy examples found
