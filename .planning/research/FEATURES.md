# Feature Landscape: DSPy Compilation for Bae

**Domain:** DSPy-based prompt optimization for type-driven agent graphs
**Researched:** 2026-02-04
**Confidence:** MEDIUM (based on official DSPy documentation and verified sources)

## Table Stakes

Features users expect from any DSPy compilation system. Missing = feels incomplete/broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Signature generation from class names** | Core DSPy pattern - class names become task descriptions | Low | DSPy uses class docstrings as Instructions, field names as I/O specification |
| **Typed output parsing** | DSPy's core value prop - structured outputs without manual parsing | Low | ChatAdapter/JSONAdapter handle this; Pydantic types natively supported |
| **Few-shot example collection** | BootstrapFewShot is the basic DSPy optimizer | Med | Requires tracing execution to collect input/output pairs that pass metric |
| **Custom metric support** | All DSPy optimizers require a metric function | Low | `def metric(example, pred, trace=None) -> float/bool` pattern |
| **Trace capture during execution** | Optimizers need traces to bootstrap demonstrations | Med | Capture LM calls, inputs, outputs per node execution |
| **Compiled program serialization** | Users need to save/load optimized programs | Med | DSPy supports save/load; need to integrate with bae's Graph |
| **Basic instruction optimization** | COPRO/MIPROv2 optimize instructions beyond just few-shot | Med | Requires integration with DSPy optimizer API |

## Differentiators

Features that make bae's DSPy approach unique. Not expected but highly valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Class name as primary signal** | No docstrings required - `ProcessUserQuery` is enough | Low | Most DSPy examples rely on docstrings; class names alone is cleaner |
| **Graph topology from type hints** | Signature successor types derived from `__call__` return hints | Low | Unique to bae - DSPy doesn't do graph discovery from types |
| **Node field descriptions from Pydantic** | Leverage Pydantic Field(description=...) for DSPy field hints | Low | Natural integration - bae nodes are already Pydantic models |
| **Per-node signature customization** | NodeConfigDict allows per-node prompt/optimization overrides | Med | Finer control than graph-level config |
| **Automatic decide() signature** | Generate signatures for multi-successor routing decisions | Med | LLM picks from union types; needs signature that includes all options |
| **Zero-config compilation** | `compile_graph(graph)` with sensible defaults | Low | Good DX - works out of box, customize later |
| **Graph-aware optimization** | Optimize nodes considering their position in the graph | High | Novel: predecessors/successors as context for optimization |
| **Incremental compilation** | Re-compile only changed nodes, cache unchanged | High | Important for iteration speed in development |

## Anti-Features

Features to explicitly NOT build. Common mistakes in this domain.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Manual prompt templates** | Defeats DSPy's core value - automation | Let DSPy generate prompts from signatures; expose customization via field descriptions only |
| **Async compilation API** | Bae is sync-only; adding async compilation creates API inconsistency | Keep compile() sync; optimization runs can be long but blocking is fine |
| **Built-in training data management** | Scope creep - not bae's job | Accept examples as input; let users manage their own datasets |
| **Custom optimizer implementations** | DSPy optimizers are battle-tested | Use DSPy's optimizers (BootstrapFewShot, MIPROv2); don't reinvent |
| **Prompt caching/versioning system** | Scope creep into MLOps territory | Save/load compiled programs; let external tools handle versioning |
| **Multi-model optimization** | Complex; not needed for MVP | Optimize for single model; model switching is orthogonal concern |
| **Real-time optimization** | DSPy compilation is batch; real-time doesn't make sense | Compile offline, run optimized program in production |
| **Retry/validation loops in compiler** | DSPy optimization may solve validation naturally | Let DSPy's structured output handling deal with parse failures |
| **Abstract optimizer interface** | Over-engineering for hypothetical future needs | Use DSPy's optimizer API directly; wrap later if needed |

## Feature Dependencies

```
Signature generation (from class names)
    |
    v
Typed output parsing (Pydantic -> DSPy)
    |
    v
Trace capture (during graph execution)
    |
    +---> Few-shot collection (BootstrapFewShot)
    |
    +---> Instruction optimization (MIPROv2/COPRO)
    |
    v
Compiled program (save/load)
```

Key dependency chain:
1. Must generate DSPy Signatures from Node classes before anything else
2. Trace capture enables all optimization strategies
3. Optimization strategies are independent of each other (can do few-shot only, or instruction only, or both)

## DSPy Feature Matrix

What DSPy provides vs what bae must implement:

| Capability | DSPy Provides | Bae Must Implement |
|------------|---------------|-------------------|
| Signature definition | Class-based signatures with docstrings | Convert Node class names/fields to Signature |
| TypedPredictor | Pydantic-typed outputs | Already using Pydantic; wire through |
| ChatAdapter/JSONAdapter | Prompt formatting, output parsing | Select appropriate adapter |
| BootstrapFewShot | Few-shot optimization | Provide trainset, metric, wire to optimizer |
| MIPROv2 | Instruction + demo optimization | Same as above; more sophisticated |
| Trace collection | Callbacks, MLflow integration | Implement trace capture during graph.run() |
| Compiled program save/load | Built-in serialization | Integrate with Graph serialization |

## MVP Recommendation

For MVP, prioritize these features:

1. **Signature generation from class names** (table stakes)
   - Extract class name as task description
   - Map Pydantic fields to DSPy input/output fields
   - Use field descriptions as DSPy field hints

2. **Typed output with Pydantic** (table stakes)
   - Use DSPy's TypedPredictor or JSONAdapter
   - Validate outputs against Node subclass schema

3. **Trace capture during execution** (table stakes)
   - Capture (input_node, output_node) pairs during graph.run()
   - Store traces for later optimization

4. **Basic few-shot optimization** (table stakes + differentiator)
   - Wire BootstrapFewShot with captured traces
   - Simple metric: did output parse correctly?

5. **Class name as primary signal** (differentiator)
   - Make docstrings optional enhancement, not required
   - Good defaults from descriptive class names

Defer to post-MVP:
- **MIPROv2 integration**: More complex, needs more training data
- **Graph-aware optimization**: Novel but complex
- **Incremental compilation**: Nice for DX but not essential
- **Per-node config overrides**: Start with graph-level defaults

## Key Insights from Research

### DSPy's Core Model

DSPy treats prompts as "programs" not "templates":
- **Signatures** declare I/O behavior (like function signatures)
- **Modules** implement strategies (Predict, ChainOfThought, ReAct)
- **Optimizers** tune prompts/demos based on metrics
- **Compilation** = running optimizers on your program

### Class Names and Docstrings

From [DSPy Signatures](https://dspy.ai/learn/programming/signatures/):
- Docstring becomes "Instructions" in the prompt
- Field names should be "semantically meaningful"
- DSPy says: "don't prematurely tune keywords - let the optimizer do it"

**Implication for bae:** Class name IS the docstring. A class named `AnalyzeUserIntent` with no docstring works fine - DSPy will use the class name. Field names from Pydantic provide the I/O spec.

### Pydantic Integration

From [DSPy Adapters](https://dspy.ai/learn/programming/adapters/):
- ChatAdapter and JSONAdapter both support Pydantic types
- JSONAdapter is better for models supporting `response_format`
- Field descriptions in Pydantic map to DSPy field descriptions

**Implication for bae:** Direct mapping possible. `Field(description="...")` in Pydantic becomes `dspy.OutputField(desc="...")`.

### Optimization Approaches

From [DSPy Optimizers](https://dspy.ai/learn/optimization/optimizers/):
- **BootstrapFewShot**: 10-50 examples, simple metric, fast
- **MIPROv2**: 50-200+ examples, better quality, slower/costlier
- **COPRO**: Instruction-only optimization

**Recommendation:** Start with BootstrapFewShot. It's simple, fast, and works well for getting started. Graduate to MIPROv2 when you have more data and need higher quality.

### Tracing and Observability

From [DSPy Debugging & Observability](https://dspy.ai/tutorials/observability/):
- DSPy has callback system: `dspy.configure(callbacks=[...])`
- MLflow integration: `mlflow.dspy.autolog()`
- By default, traces are NOT generated during compilation (too many calls)

**Implication for bae:** Need custom callback to capture traces during normal execution. Optimization runs will generate their own traces internally.

## Confidence Assessment

| Claim | Confidence | Reasoning |
|-------|------------|-----------|
| DSPy Signature from class name works | HIGH | Verified in official docs - docstring becomes Instructions |
| Pydantic types supported in DSPy | HIGH | Official docs show Pydantic BaseModel integration |
| BootstrapFewShot is appropriate starting optimizer | HIGH | Official recommendation for 10-50 examples |
| Class name alone sufficient (no docstring) | MEDIUM | Docs suggest docstring, but class name should work - needs validation |
| Graph topology optimization is novel | MEDIUM | Haven't found existing examples; may be unexplored territory |
| JSONAdapter better than ChatAdapter for Anthropic | LOW | Needs testing; depends on model capabilities |

## Sources

**Official DSPy Documentation:**
- [DSPy Signatures](https://dspy.ai/learn/programming/signatures/) - Signature definition patterns
- [DSPy Optimizers](https://dspy.ai/learn/optimization/optimizers/) - Optimizer comparison
- [DSPy Adapters](https://dspy.ai/learn/programming/adapters/) - Pydantic integration
- [DSPy Modules](https://dspy.ai/learn/programming/modules/) - Custom module patterns
- [DSPy Debugging & Observability](https://dspy.ai/tutorials/observability/) - Tracing approaches

**Research and Comparisons:**
- [DSPy GitHub](https://github.com/stanfordnlp/dspy) - 28k+ stars, active development
- [MIPROv2 API](https://dspy.ai/api/optimizers/MIPROv2/) - Advanced optimizer details
- [DSPy vs TextGrad comparison](https://staslebedenko.medium.com/prompt-autopilot-tools-comparison-ed4dbbddad57) - Framework comparison

**Related Tools:**
- [DSPydantic](https://github.com/davidberenstein1957/dspydantic) - Pydantic-first DSPy wrapper
- [Langfuse DSPy integration](https://langfuse.com/docs/integrations/dspy) - Observability

---

*Research conducted: 2026-02-04*
