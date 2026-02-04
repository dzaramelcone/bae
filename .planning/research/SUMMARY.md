# Project Research Summary

**Project:** Bae - Type-driven agent graphs with DSPy optimization
**Domain:** LLM agent framework with prompt compilation
**Researched:** 2026-02-04
**Confidence:** MEDIUM-HIGH

## Executive Summary

Bae integrates DSPy's prompt optimization framework into an existing type-driven agent graph system. The core insight from research: DSPy doesn't replace Bae's execution framework—it optimizes the prompts used during execution. Bae's existing Node-based architecture (Pydantic models with type hints) maps cleanly to DSPy's Signature-based approach. Class names become task descriptions, field annotations become input/output specs, and DSPy's optimizers tune these prompts from traced executions.

The recommended approach is incremental integration. Phase 1 establishes the Node-to-Signature conversion and validates that Bae's two-step decide pattern (pick type, then fill fields) works with DSPy. Phase 2 adds trace collection during normal graph execution. Phase 3 wires optimizers (starting with BootstrapFewShot for simplicity). Phase 4 handles deployment of optimized prompts. This phasing avoids the critical pitfall of integration complexity underestimation—treating DSPy as a complete solution rather than a prompt optimization layer.

Key risks center on architectural mismatches: the two-step decide pattern needs explicit validation with DSPy, adapter selection must match model capabilities (ChatAdapter default, JSONAdapter only for models with response_format support), and Bae's make/decide abstraction may become redundant once DSPy modules handle LM calls. The mitigation strategy is to prototype these integration points in Phase 1 before committing to larger architectural changes, and be willing to refactor redundant layers rather than maintaining duplicate abstractions.

## Key Findings

### Recommended Stack

DSPy 3.1.x (current stable: 3.1.2) provides mature Pydantic integration that aligns perfectly with Bae's BaseModel-based nodes. The critical discovery: DSPy's ChatAdapter handles Pydantic types natively, and `dspy.Predict` replaces the deprecated `TypedPredictor`. The integration path is straightforward—convert Node classes to Signature classes at compile time, use class names and docstrings as instructions, and let DSPy's optimizers tune from there.

**Core technologies:**
- **dspy ^3.1.0**: Prompt optimization framework — current stable with full Pydantic support, avoid deprecated TypedPredictor
- **dspy.Predict**: LLM invocation with structured output — core module for Node-to-LLM translation
- **dspy.ChatAdapter**: Signature-to-prompt translation — default adapter, handles Pydantic BaseModel automatically (use JSONAdapter only for models with response_format)
- **BootstrapFewShot optimizer**: Few-shot optimization from traces — start here (needs 10+ examples), graduate to MIPROv2 later (needs 50+)
- **litellm**: Multi-provider LLM backend — DSPy's recommended abstraction, may replace existing backends

**Critical versions:**
- DSPy 3.x required (2.5.30+ has threading issues)
- Python 3.14 already required by Bae for PEP 649
- Pydantic 2.x compatibility confirmed

### Expected Features

**Must have (table stakes):**
- **Signature generation from class names** — Core DSPy pattern; class name becomes task description, field names become I/O spec
- **Typed output parsing** — DSPy's value prop; Pydantic validation without manual parsing
- **Trace capture during execution** — Required for all optimizers; capture (input_node, output_node) pairs during graph.run()
- **Few-shot example collection** — BootstrapFewShot baseline; needs metric function to score outputs
- **Compiled program serialization** — Users need save/load for optimized prompts

**Should have (competitive differentiators):**
- **Class name as primary signal** — Make docstrings optional, let descriptive names like "AnalyzeUserIntent" drive prompts
- **Graph topology from type hints** — Unique to Bae; derive successor types from __call__ return hints
- **Node field descriptions from Pydantic** — Leverage Field(description=...) for DSPy field hints
- **Zero-config compilation** — Good DX: compile_graph(graph) works out of box
- **Per-node signature customization** — NodeConfigDict allows per-node prompt/optimization overrides

**Defer (v2+):**
- **MIPROv2 integration** — More complex, needs 50+ training examples
- **Graph-aware optimization** — Novel idea (optimize nodes considering predecessors/successors) but complex
- **Incremental compilation** — Nice for iteration speed but not essential
- **Async interface** — DSPy's async support is limited; start sync-only

**Anti-features (explicitly avoid):**
- Manual prompt templates — defeats DSPy's automation
- Custom optimizer implementations — use DSPy's battle-tested optimizers
- Real-time optimization — compile offline, run optimized program in production

### Architecture Approach

DSPy operates as a prompt optimization layer, not a replacement for Bae's execution framework. The integration preserves Bae's Graph execution loop and Node-based state management while routing LM calls through DSPy modules when optimized prompts exist. The key architectural decision: wrap existing LM backends with OptimizedLM that checks for DSPy modules per node type and falls back to naive prompts if not optimized.

**Major components:**
1. **NodeSignature converter** — Maps Node class (fields, docstring, successors) to dspy.Signature class dynamically
2. **OptimizedLM wrapper** — Implements LM protocol, routes decide() through DSPy modules when available, preserves make() fallback
3. **Compiler (rewritten)** — Extracts signatures from Graph, creates dspy.Predict modules, runs BootstrapFewShot optimizer, saves optimized modules
4. **CompiledGraph** — Holds optimized modules per node type, provides OptimizedLM configured with these modules
5. **TraceStore** — Collects (input_node, output_node) pairs during graph.run() for training data

**Data flow:**
- Compilation phase (offline): Graph → NodeSignature → dspy.Signature → dspy.Predict → optimizer.compile() → save optimized modules
- Execution phase (online): load optimized modules → OptimizedLM → graph.run() routes through DSPy when modules exist

**Critical integration point:** Bae's two-step decide (pick successor type, then fill fields) must map to DSPy signatures. Two approaches possible: (1) single signature with union output type, or (2) chained modules. Needs prototype validation in Phase 1.

### Critical Pitfalls

1. **Adapter format mismatch** — Using JSONAdapter without verifying model supports response_format causes silent failures. Start with ChatAdapter (default), switch to JSONAdapter only after confirming model compatibility. Add validation tests with actual model calls.

2. **Async/threading confusion** — DSPy 2.5.30+ has threading issues, dspy.asyncify doesn't enable true parallelism, underlying calls remain synchronous. Start sync-only, avoid Python threading with predictors. Add timing tests if async needed later.

3. **Premature signature optimization** — Hand-tuning keywords/field names before seeing failures. DSPy docs warn: "don't prematurely tune... optimizers will do better." Start with minimal signatures (simple class names, basic descriptions), let optimizers handle tuning.

4. **Statelessness surprise** — DSPy doesn't manage multi-turn context automatically. Design explicit state management from Phase 1. For Bae's two-step decide, chain prompts or use custom state container.

5. **Integration complexity underestimation** — DSPy enhances LM backbone but doesn't replace orchestration. Bae's make/decide abstraction may become redundant with DSPy modules. Budget time for integration work, evaluate architectural redundancy, be willing to refactor.

6. **Two-step decide validation gap** — Bae's pattern (pick type, then fill) may not align naturally with DSPy. Prototype both approaches (single signature vs. chained modules) in Phase 1 before committing. Be willing to restructure if DSPy suggests better architecture.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation (Signature Extraction & Validation)
**Rationale:** Must validate core integration assumptions before building on them. The two-step decide pattern and Node-to-Signature conversion are architectural foundations that need proof-of-concept.

**Delivers:**
- node_to_dspy_signature() implementation for all Node classes
- Validation that signatures match Bae's type system
- Prototype proving two-step decide works with DSPy (single signature vs. chained modules)
- Adapter selection strategy (ChatAdapter default, validation tests)
- Sync-only interface confirmed

**Addresses:**
- Signature generation from class names (table stakes)
- Class name as primary signal (differentiator)
- Node field descriptions from Pydantic (differentiator)

**Avoids:**
- Two-step decide validation gap (critical pitfall #6)
- Integration complexity underestimation (critical pitfall #5)
- Adapter format mismatch (critical pitfall #1)
- Async/threading confusion (critical pitfall #2)

**No behavior change:** Signatures generated but not used yet. Existing graph execution unchanged.

### Phase 2: Trace Collection Pipeline
**Rationale:** Optimizers need training data. Must collect real execution traces before optimization can happen. This is pure infrastructure—no optimization behavior yet.

**Delivers:**
- TraceStore implementation for recording (input_node, output_node) pairs
- Trace capture hooks in Graph.run()
- bae_trace_to_dspy_example() conversion
- node_transition_metric() function
- Storage/retrieval for training examples

**Uses:**
- dspy.Example format (from STACK.md)
- Trace-based bootstrapping pattern (from ARCHITECTURE.md)

**Implements:**
- TraceStore component (from Architecture)

**Addresses:**
- Trace capture during execution (table stakes)
- Few-shot example collection (table stakes)

**Avoids:**
- Premature optimization (critical pitfall #3) — collecting data, not tuning yet

### Phase 3: Optimization Integration
**Rationale:** With traces collected, wire optimizers to tune prompts. Start simple (BootstrapFewShot) before graduating to complex optimizers.

**Delivers:**
- dspy.Predict module creation for each node type
- BootstrapFewShot optimizer integration
- Compiled program save/load
- OptimizedLM wrapper implementing LM protocol
- CompiledGraph container for optimized modules

**Uses:**
- BootstrapFewShot optimizer (from STACK.md)
- Wrapper pattern for LM integration (from ARCHITECTURE.md)

**Implements:**
- Compiler (rewritten), CompiledGraph, OptimizedLM components

**Addresses:**
- Typed output parsing (table stakes)
- Compiled program serialization (table stakes)
- Zero-config compilation (differentiator)

**Avoids:**
- Statelessness surprise (critical pitfall #4) — explicit state management established in Phase 1

### Phase 4: Production Deployment
**Rationale:** Optimized prompts need deployment infrastructure. This phase makes compilation production-ready.

**Delivers:**
- Load optimized modules at graph startup
- Fallback behavior for unoptimized nodes
- Observability (which nodes optimized, cache hit rates)
- Prompt versioning/storage strategy
- Error wrapping for user-facing DSPy errors

**Addresses:**
- Per-node signature customization (differentiator)

**Avoids:**
- Integration complexity underestimation (critical pitfall #5) — deployment planned upfront

### Phase 5: Advanced Features (Post-MVP)
**Rationale:** Nice-to-haves that aren't essential for proving the concept.

**Delivers:**
- MIPROv2 integration (needs 50+ examples)
- Graph-aware optimization (novel, complex)
- Incremental compilation (iteration speed)
- Per-node config overrides (NodeConfigDict)

**Deferred from v1:** Advanced optimizers, graph-level awareness, performance optimizations

### Phase Ordering Rationale

- **Phase 1 first:** Validates core assumptions (two-step decide, Node-to-Signature mapping) before building infrastructure. Failure here means architectural pivot needed.
- **Phase 2 before 3:** Can't optimize without training data. Trace collection is pure infrastructure that doesn't depend on optimization logic.
- **Phase 3 before 4:** Must prove optimization works before investing in deployment infrastructure.
- **Dependencies:** 1 → 2 → 3 → 4 are strictly sequential. Phase 5 is independent enhancements.
- **Risk mitigation:** Front-loads validation (Phase 1) to catch integration mismatches early. Defers complex features (Phase 5) until core value proven.

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 1:** Two-step decide validation — no existing DSPy examples found for Bae's pattern. Needs prototyping to determine single signature vs. chained modules approach.
- **Phase 3:** Metric function design — Domain-specific quality evaluation for node transitions. What makes a "good" graph execution? Needs design research.

**Phases with standard patterns (skip research-phase):**
- **Phase 2:** Trace collection — Well-documented pattern in DSPy observability docs
- **Phase 4:** Save/load compiled programs — DSPy has built-in serialization, just needs integration
- **Phase 5:** Advanced features — Documentation exists for MIPROv2, just complex to implement

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Official DSPy 3.1.2 docs, verified Pydantic integration, clear version requirements |
| Features | MEDIUM-HIGH | Table stakes well-documented, differentiators synthesized from Bae context, anti-features based on DSPy design philosophy |
| Architecture | MEDIUM | Integration pattern synthesized from multiple sources, Node-to-Signature mapping inferred (needs validation), two-step decide needs prototyping |
| Pitfalls | HIGH | Based on official docs warnings, DSPy 2.5.30+ release notes, community discussions, and Bae architecture analysis |

**Overall confidence:** MEDIUM-HIGH

Research is solid on DSPy fundamentals and Bae's existing architecture. Medium confidence on integration specifics—particularly the two-step decide pattern mapping—because no direct examples exist. The phased approach with Phase 1 validation mitigates this by proving integration patterns before committing to full implementation.

### Gaps to Address

- **Two-step decide pattern:** No DSPy examples found for Bae's pick-type-then-fill-fields pattern. Phase 1 must prototype both single signature (union output type) and chained modules approaches to determine which works better.

- **make/decide abstraction redundancy:** Once DSPy modules handle LM calls, Bae's make/decide protocol may be unnecessary duplication. Phase 1 should evaluate if OptimizedLM can simplify or replace this abstraction. Don't maintain duplicate layers for backward compatibility—refactor if redundant.

- **Metric function design:** What makes a "good" node transition? Type correctness is obvious, but field quality evaluation is domain-specific. Phase 3 needs design work on metric functions beyond simple type matching.

- **ChatAdapter vs JSONAdapter performance:** Research shows JSONAdapter has lower latency but requires response_format support. Need production profiling to determine if ChatAdapter token overhead is acceptable or if model-specific adapter selection is worth the complexity.

- **Optimizer data requirements:** BootstrapFewShot needs 10+ examples, MIPROv2 needs 50+. No guidance on how to collect this much training data for a new graph. Phase 2 needs strategy for cold-start problem (zero-shot with docstrings only, then collect traces, then optimize).

## Sources

### Primary (HIGH confidence)
- [DSPy Official Documentation](https://dspy.ai) — Signatures, Modules, Optimizers, Adapters
- [DSPy GitHub Repository](https://github.com/stanfordnlp/dspy) v3.1.2 (Jan 2026) — Code examples, issue discussions
- [DSPy Cheatsheet](https://dspy.ai/cheatsheet/) — Quick reference for API patterns
- [MIPROv2 API Documentation](https://dspy.ai/api/optimizers/MIPROv2/) — Optimizer parameters and data requirements

### Secondary (MEDIUM confidence)
- [TypedPredictor deprecation discussion](https://github.com/stanfordnlp/dspy/issues/724) — Use dspy.Predict instead
- [Pydantic to DSPy Signature gist](https://gist.github.com/seanchatmangpt/7e25b66ebffdedba7310d9c90f377463) — Community pattern for conversion
- [DSPydantic library](https://github.com/davidberenstein1957/dspydantic) — Pydantic-first wrapper showing integration patterns
- [LangGraph + DSPy integration article](https://www.rajapatnaik.com/blog/2025/10/23/langgraph-dspy-gepa-researcher) — Hybrid framework approach

### Tertiary (LOW confidence - needs validation)
- [Behavioral optimization for multi-step agents](https://viksit.substack.com/p/behavioral-optimization-for-multi) — Graph-aware optimization concept
- Community discussions on statelessness and async limitations — Consistent pattern but no official documentation

---
*Research completed: 2026-02-04*
*Ready for roadmap: yes*
