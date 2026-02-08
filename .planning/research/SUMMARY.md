# Research Synthesis: Bae v3.0 Eval/Optimization DX

**Synthesized:** 2026-02-08
**Project:** Bae - Type-driven agent graphs with DSPy optimization
**Milestone:** v3.0 - "Super accessible and friendly" eval/optimization developer experience
**Goal:** Users creating agentic graphs within 1 minute

---

## Executive Summary

Bae v3.0 needs to make eval and optimization feel native, not bolted-on. The research converges on a clear insight: **DSPy already has everything needed** -- `dspy.Evaluate`, three optimizer tiers (BootstrapFewShot → MIPROv2 → SIMBA), and LLM-as-judge via `dspy.Predict(Assess)`. Bae's job is not to build eval infrastructure but to **wrap DSPy's primitives in a zero-friction CLI** that converts bae graph concepts to DSPy concepts transparently. No external eval framework needed.

The architecture adds three new modules (package.py, eval.py, dataset.py) that project Graph's existing topology introspection into developer-facing workflows. The domain package (`my_domain/graph.py` + `datasets/` + `compiled/`) becomes the organizational primitive. Progressive complexity tiers (0: structural checks → 1: example-based → 2: LLM-as-judge → 3: custom metrics) let developers start with zero config and add sophistication incrementally.

The central risk is **false confidence**: eval tooling that's easy to use but measures the wrong thing. The current `node_transition_metric` (type-check only) would report 92% accuracy on a graph with terrible output quality. Mitigations: honest default metrics, forced "metric moment" on first eval, and auto-generated LLM-as-judge from Field descriptions.

**Stack changes:** Add `rich` (explicit, was transitive), bump `dspy>=3.1` (for MIPROv2/SIMBA), bump `typer>=0.15` (Rich markup). No external eval framework. Copier (dev tool, not dependency) for optional scaffolding.

**Build order:** Phase 1 (package discovery + eval foundation) → Phase 2 (dataset + optimize CLI) → Phase 3 (LLM-as-judge + polish). Phase 1 is critical -- it establishes the metric abstraction and progressive complexity tiers that everything else depends on.

---

## Convergence: What All Researchers Agree On

### 1. DSPy Is Sufficient -- No External Framework Needed

All four research files converge: **DSPy 3.1.3 has everything bae needs**. External frameworks (DeepEval, RAGAS, Braintrust, Inspect AI) add dependency bloat and impedance mismatches. The killer advantage of DSPy-native LLM-as-judge: when your metric uses `dspy.Predict`, DSPy can optimize the judge itself. External frameworks evaluate but don't participate in the optimization loop.

**STACK.md:** "DSPy already has everything needed for evals and optimization -- `dspy.Evaluate`, `EvaluationResult`, and three optimizer tiers."

**FEATURES.md:** "DSPy metric functions (plain Python)" instead of DeepEval's 50+ metrics or RAGAS's RAG-specific focus.

**ARCHITECTURE.md:** "Bae's `evaluate()` is intentionally **not** a wrapper around `dspy.Evaluate`. The bridge is at the optimizer boundary, not the eval boundary."

**PITFALLS.md:** "If bae ships a default `llm_judge` metric, developers will use it without understanding the biases."

**Implication:** Ship DSPy-native patterns. Don't add eval framework dependencies. When developers outgrow bae's built-in metrics, guide them to DSPy's docs, not a third framework.

---

### 2. Progressive Complexity Tiers Are the Core DX Design

All researchers identify the same 4-tier progression:

| Tier | What It Measures | Setup Time | STACK | FEATURES | ARCHITECTURE | PITFALLS |
|------|------------------|------------|-------|----------|--------------|----------|
| 0 | Structural (graph completes, types correct, fields populated) | 0 min | "Zero-config quality" | "Does it even work?" | "Default completion metric" | "Honest about what it measures" |
| 1 | Example-based (expected output matching) | 5-10 min | "Field comparison metric" | "Regression testing" | "Golden dataset (input + expected)" | "Dataset too small or not representative" |
| 2 | LLM-as-judge (quality rubric evaluation) | 15-30 min | "LLM-as-judge metric" | "Quality measurement" | "Custom metrics via DSPy" | "Judge bias and cost explosion" |
| 3 | Custom (user-defined Python functions) | As long as needed | "Custom metric function" | "Full control" | "User writes arbitrary scoring logic" | "DSPy plumbing leaks through" |

**FEATURES.md:** "No other framework explicitly designs for progressive complexity. They dump you into 'write a metric' immediately."

**ARCHITECTURE.md:** "The tiers are **not** architecturally separate modules. They are **levels of configuration** within the same modules."

**PITFALLS.md:** "The pitfall is cliff effects -- sharp jumps in complexity between tiers. The gap between 'just works' and 'slightly customized' is a cliff."

**Implication:** Each tier must be independently useful. Zero-config must be honest about limitations. Tier 0→1 and 1→2 transitions must add one concept, not five. The metric abstraction layer is the most consequential API design.

---

### 3. Graph Structure Is an Eval Superpower

Bae's typed graph topology is rich metadata that no competitor can match. All researchers identify opportunities here:

**FEATURES.md:** "No other framework has typed graph topology to introspect. Promptfoo evaluates prompts. DSPy evaluates programs. None of them can say 'the graph should visit nodes A, B, C in order.'"

**ARCHITECTURE.md:** "Graph already knows everything -- nodes, edges, field types, routing strategy. The eval/optimization DX is a projection of Graph's introspection."

**PITFALLS.md:** "Node-level metrics miss cross-node quality issues. Developer writes a metric for the terminal node only, ignoring intermediate quality."

**Opportunities:**
- **Zero-config structural eval** from `Graph.nodes`, `Graph.edges`, `Graph.terminal_nodes`
- **Auto-generated judge rubric** from `Field(description=...)` on node fields
- **Graph-aware metrics** that understand paths and branching
- **Eval overlay on mermaid diagrams** (green nodes passed, red failed)

**Implication:** Don't treat eval as generic. Leverage graph structure for zero-config checks and auto-generated quality metrics.

---

### 4. Compiled Artifacts Need Conventions and Staleness Detection

All researchers flag artifact management as critical:

**STACK.md:** "DSPy version compatibility: same version for save and load (DSPy <3.0 doesn't guarantee backward compat)."

**FEATURES.md:** "Standard directory layout: `<domain>/.compiled/` with timestamped artifacts, metadata, and a `latest` symlink."

**ARCHITECTURE.md:** "The compiled directory lives inside the domain package: `my_domain/compiled/`."

**PITFALLS.md:** "Compiled artifacts contain few-shot demonstrations baked from a specific graph structure, specific node field schemas, and a specific LLM model. When any of these change, the artifacts become stale."

**Staleness risk:** Node schema changes (added field, renamed field, changed Dep) invalidate compiled artifacts. `load_optimized()` doesn't detect this -- it just loads stale demos. Result: LLM sees old-format examples, produces outputs that don't match current schema. No error, just degraded quality.

**Implication:** Phase 2 must build staleness detection into save/load from day one. Hash node signatures (field names + types + instruction). Save metadata (model, dataset size, timestamp, node hash). Warn on load if hash mismatch.

---

### 5. The Central Risk Is False Confidence

All four researchers identify this as the critical pitfall:

**STACK.md:** "Current metric only checks 'did you pick the right type?' -- says nothing about output quality."

**FEATURES.md:** "A zero-config eval that reports '92% accuracy' on a bad metric with a tiny dataset is worse than no eval at all."

**ARCHITECTURE.md:** "Metrics that understand graph structure: 'Did the graph take the expected path?'"

**PITFALLS.md:** "The stated goal is to make evals 'super accessible and friendly.' The most dangerous outcome is eval tooling that's easy to use but gives developers false confidence."

**False confidence happens through:**
- Metrics that measure the wrong thing (routing correctness ≠ output quality)
- Datasets too small to catch edge cases (5 traces is not 200 traces)
- Biased judges that inflate scores (verbosity bias, position bias)
- Node-level evals that miss graph-level failures (all nodes score high but end-to-end fails)

**Mitigation strategy:** Be honest about what the eval measures and what it doesn't. Every eval output should answer: "What did we measure? What didn't we measure? How confident are we?"

---

## Tensions: Where Researchers Disagree

### Tension 1: Metric Signature -- DSPy Types or Bae Types?

**ARCHITECTURE.md proposes two options:**
- **Option A:** `Callable[[GraphResult], float]` -- metric only sees the result. Golden comparison happens outside the metric.
- **Option B:** `Callable[[dict, GraphResult], float]` -- metric sees both input and result. Cleaner for golden trace comparison.

**ARCHITECTURE.md recommends Option B.** The input dict is cheap to pass and enables golden-trace metrics.

**But PITFALLS.md warns:** "DSPy metrics must return `bool` when `trace is not None` (bootstrap mode) and `float` when `trace is None` (evaluation mode). Bae should document this and provide a helper."

**Resolution needed:** The metric interface must hide DSPy's (example, pred, trace) signature from developers while still supporting BootstrapFewShot's bool/float mode switching. Proposed wrapper:

```python
# Developer writes this (bae-native):
def my_metric(input: dict, output: Node) -> float:
    return 1.0 if output.field else 0.0

# Bae translates to DSPy format internally:
def _dspy_adapter(example, pred, trace=None):
    score = my_metric(example.inputs, pred)
    return score if trace is None else score > 0.8  # threshold for bootstrap
```

**Decision:** Metrics should take bae types, not DSPy types. Provide a `bae.metrics.from_fn(my_metric, bootstrap_threshold=0.8)` adapter.

---

### Tension 2: Package Scaffolding -- Required or Optional?

**ARCHITECTURE.md:** "The 'domain package' is the organizational unit that ties a graph definition to its eval data, compiled artifacts, and documentation."

**Proposed layout:**
```
my_domain/
  __init__.py
  graph.py
  graph.md (auto-generated)
  eval.py (optional)
  datasets/
  compiled/
```

**But PITFALLS.md warns:** "If `bae init` generates a rigid structure, developers with existing code must reorganize to fit. Convention disagreements become breaking changes."

**PITFALLS.md recommends:** "Convention discovery, not convention enforcement. The CLI should look for graphs by module path, not by file location. No scaffold at all for v3.0."

**Resolution needed:** The CLI must work with arbitrary module paths (already works: `bae graph show examples.ootd`). Package discovery should be heuristic-based:
1. Load graph from module path
2. Look for `datasets/` in same directory (optional)
3. Look for `compiled/` in same directory (optional)
4. Look for `eval.py` in same directory (optional)

**Scaffolding should be additive:** `bae init` generates minimal starter files but never required. Existing projects work without scaffolding.

**Decision:** Phase 1 builds CLI with zero scaffolding. Phase 3 adds optional `bae init` if developers ask for it. YAGNI.

---

### Tension 3: Graph-Level vs Node-Level Eval Default

**ARCHITECTURE.md:** "Developers think in graph-level terms ('is my outfit recommendation pipeline good?') but the eval infrastructure works at node-level."

**PITFALLS.md:** "Node-level metrics miss cross-node quality issues. Optimizing one node degrades another (no joint optimization)."

**But bae's optimizer is node-level** (`optimize_node(node_cls, trainset)`). DSPy doesn't have joint multi-predictor optimization.

**Resolution needed:** Support both, default to graph-level for developer intuition.

```bash
bae eval my_domain              # Graph-level (default): evaluates full traces
bae eval my_domain --per-node   # Node-level: breaks down scores per node
```

Graph-level metrics receive `GraphResult` (full trace + terminal node). Node-level metrics receive individual nodes from the trace. Both feed the optimizer after being translated to DSPy format.

**Decision:** Graph-level is the default. Node-level is accessible but not the happy path.

---

## Key Design Decisions (Must Resolve Before Coding)

### Decision 1: What Does Tier 0 (Zero-Config) Measure?

**Current state:** `node_transition_metric` checks type correctness only.

**Problem:** This measures routing, not quality. 100% type-check score tells you nothing about whether the outfit is good.

**Proposal:** Tier 0 measures **structural correctness** with honest labeling:
- Graph completes without exception
- Terminal node is reached
- All fields on terminal node are populated (non-null, non-empty)
- Trace visits expected node types
- Node transitions match graph edges

**Output explicitly says:**
```
STRUCTURAL EVAL (checks correctness, not quality)
  [PASS] Graph completed (3 nodes)
  [PASS] Terminal node reached (RecommendOOTD)
  [PASS] All fields populated (6/6)
  [WARN] Quality metrics: 0/3 nodes

This eval checks structure, not output quality.
To measure quality, add a dataset: bae eval my_domain --dataset examples.jsonl
```

**Decision:** Tier 0 is honest about being a smoke test. It catches crashes and routing errors. It does not measure quality.

---

### Decision 2: Metric Interface -- What Signature Do Developers Write?

**Option A: DSPy-native**
```python
def my_metric(example: dspy.Example, pred, trace=None) -> float | bool:
    ...
```
Pros: Direct DSPy integration. Cons: Exposes DSPy internals, steep learning curve.

**Option B: Bae-native**
```python
def my_metric(input: dict, output: Node) -> float:
    ...
```
Pros: Clean abstraction. Cons: Requires adapter layer.

**PITFALLS.md warns:** "If metrics take `(example: dspy.Example, pred, trace=None)`, developers need to learn DSPy. The gap between 'just works' and 'slightly customized' is a cliff."

**Recommendation:** **Option B with adapter layer.** Developers write bae-native metrics. Bae translates to DSPy format internally. Provide helpers:
- `bae.metrics.from_fn(fn, bootstrap_threshold=0.8)` -- wraps a bae-native function
- `bae.metrics.llm_judge(question: str)` -- auto-generates LLM-as-judge metric
- `bae.metrics.field_completeness()` -- default Tier 1 metric

**Decision:** Metrics are bae-native by default. Advanced users can drop down to DSPy format if needed.

---

### Decision 3: Are Compiled Artifacts Self-Describing?

**Current state:** `{NodeClassName}.json` with DSPy predictor state. No version, no hash, no metadata.

**Risk:** When node schema changes, compiled artifact becomes stale but loads silently. LLM sees old-format demos and gets confused.

**Proposal:** Save metadata alongside predictor state:
```json
{
  "node_class": "RecommendOOTD",
  "node_hash": "abc123def456",
  "field_signature": ["top: str", "bottom: str", "footwear: str", "..."],
  "bae_version": "3.0.0",
  "dspy_version": "3.1.3",
  "model": "claude-sonnet-4",
  "compiled_at": "2026-02-08T14:30:00Z",
  "dataset_size": 50,
  "metric_score": 0.87,
  "predictor_state": { ... }
}
```

On load, check `node_hash`. If mismatch, warn: "Compiled artifact for RecommendOOTD is stale (schema changed). Re-run `bae optimize`."

**Decision:** Phase 2 adds metadata and staleness detection from day one. Never silently load stale artifacts.

---

### Decision 4: CLI Config Via Args or Files?

**FEATURES.md surveyed frameworks:** Promptfoo's YAML-heavy workflow "adds friction for developers." DSPy is code-first.

**PITFALLS.md warns:** "If bae's CLI requires a `bae.yaml` with deeply nested configuration, developers will bounce at the setup step."

**Existing pattern:** `bae graph show examples.ootd` -- module path as argument, sensible defaults.

**Proposal:** CLI arguments first, config file optional.
```bash
bae eval my_domain                        # Uses defaults (datasets/seed.jsonl, completion metric)
bae eval my_domain --dataset golden.jsonl --metric quality
bae eval my_domain --config eval.toml     # Optional config file for power users
```

**Convention-based discovery:** If no `--dataset` flag, look for `my_domain/datasets/seed.jsonl`. If no `--metric` flag, use default completion metric. If `my_domain/eval.py` exists, auto-import metrics from it.

**Decision:** Zero config required. CLI args for customization. Config files for power users who want to save their args.

---

### Decision 5: Is Scaffolding Required?

**ARCHITECTURE.md:** "Domain package structure is the organizational primitive."

**PITFALLS.md:** "Developers with existing graphs can't adopt the eval DX without restructuring."

**Tension:** Structured packages aid discovery. But requiring structure blocks adoption.

**Resolution:** Discovery is heuristic, not enforcement.
```python
# This works (structured):
my_domain/
  graph.py
  datasets/
  compiled/

# This also works (unstructured):
my_stuff/
  ootd_graph.py
  ootd_data.jsonl
  ootd_compiled/
```

CLI uses module path + convention-based hints:
```bash
bae eval my_stuff.ootd_graph --dataset my_stuff/ootd_data.jsonl --output my_stuff/ootd_compiled/
```

**Decision:** No scaffolding in Phase 1 or 2. Optional `bae init` in Phase 3 if developers ask for it. Structure aids but never blocks.

---

## Roadmap Implications: Suggested Build Order

### Phase 1: Eval Foundation (Weeks 1-2)

**Why first:** Eval is the feedback loop. You need to measure before you can optimize. This is the highest-value feature.

**Deliverables:**
- `bae/eval.py` -- `evaluate()` function, `EvalResult` dataclass, default metrics
- `bae/dataset.py` -- `EvalDataset` class, JSONL load/save
- `bae/cli.py` extension -- `bae eval <module>` command
- Metric abstraction layer (bae-native signature with DSPy adapter)
- Tier 0 (structural) and Tier 1 (example-based) working

**Critical decisions resolved:**
- Metric interface (bae-native with adapter)
- Tier 0 measures structural correctness, not quality
- CLI args first, no config file
- No scaffolding required

**Features from FEATURES.md:**
- Zero-config structural eval
- Dataset format (JSONL with input/output pairs)
- Eval results display (pass/fail + scores)
- Multiple examples per eval run
- Clear error messages

**Pitfalls addressed:**
- #1: Accessible evals that mislead (honest default metrics)
- #7: CLI config file hell (args first)
- #8: Progressive complexity cliffs (abstract DSPy)
- #12: Node vs graph-level confusion (support both, default graph-level)
- #15: DSPy version coupling (adapter module)

**Success criteria:**
- Developer runs `bae eval examples.ootd --input '{"user_message": "..."}'` with zero setup
- Output shows structural checks with honest "does not measure quality" warning
- Adding `--dataset examples.jsonl` runs example-based eval
- No DSPy types visible in metric interface

---

### Phase 2: Optimize Integration (Weeks 3-4)

**Why second:** Optimization depends on having eval data and metrics. The optimization primitives already exist -- this phase wires them into the CLI.

**Deliverables:**
- `bae/cli.py` extension -- `bae optimize <module>` command
- `bae/optimizer.py` enhancement -- parameterize optimizer type (bootstrap/mipro/simba)
- Compiled artifact metadata and staleness detection
- `bae run <module> --optimized` flag
- Before/after eval comparison in optimize output

**Critical decisions resolved:**
- Compiled artifacts are self-describing (metadata + hash)
- Optimizer selection is configurable
- Optimize runs eval before and after, shows delta

**Features from FEATURES.md:**
- Save/load compiled artifacts (enhanced with metadata)
- Optimization from CLI (wraps existing `CompiledGraph.optimize()`)
- Compiled artifact conventions (metadata JSON, staleness check)
- Eval diff (before/after comparison)

**Pitfalls addressed:**
- #2: Metric design that optimizes wrong thing (validation tooling)
- #3: Compiled artifacts go stale (signature hashing)
- #4: BootstrapFewShot suboptimal demos (expose optimizer selection)
- #5: Dataset too small (coverage reporting)
- #11: Eval disconnected from compile loop (before/after in optimize)

**Success criteria:**
- `bae optimize examples.ootd` runs BootstrapFewShot, saves to `examples/compiled/`
- Output shows before/after eval scores: "Routing: 85% → 93%, Quality: 3.2 → 3.8"
- `bae run examples.ootd --optimized` loads artifacts and runs
- Loading stale artifact warns: "Schema changed, re-optimize"

---

### Phase 3: LLM-as-Judge + Polish (Weeks 5-6)

**Why last:** Polish after core workflow works end-to-end. LLM-as-judge is Tier 2, which depends on Tier 0 and 1 being solid.

**Deliverables:**
- Auto-generated judge rubric from `Field(description=...)`
- `bae eval <module> --judge` command
- `bae.metrics.llm_judge(question)` helper
- Eval result caching (avoid re-judging unchanged outputs)
- Cost tracking and display
- Optional `bae init <name>` scaffolding
- Mermaid diagram enhancements (eval overlay)

**Critical decisions resolved:**
- Judge rubric is auto-generated from field descriptions
- Judge results are cached aggressively
- Scaffolding is optional, not required

**Features from FEATURES.md:**
- Auto-generated judge rubric from Field descriptions
- LLM-as-judge metric helpers
- Eval result persistence and comparison
- Tier 4 config surface (optional)

**Pitfalls addressed:**
- #6: LLM-as-judge bias and cost (document biases, cache, show cost)
- #9: Mermaid diagrams as write-only (eval overlay, on-demand generation)
- #10: Scaffolding migration pain (additive not prescriptive, YAGNI)
- #13: Hard-to-read eval output (summary-first, color-coded)
- #14: Eval run cost surprises (cost tracking)

**Success criteria:**
- `bae eval examples.ootd --judge` auto-generates rubric from field descriptions
- Judge evaluates quality per field: "top: specific garment? YES. bottom: specific garment? YES."
- Output shows: "Judge cost: $0.47 (23 LLM calls). Cached: 177 results reused."
- Optional `bae init my_domain` scaffolds minimal starter package

---

## Research Flags: Which Phases Need Deeper Research?

### Phase 1: Well-Documented Patterns (Skip Research)
- Dataset loading (JSONL is standard)
- Metric functions (plain Python callables, DSPy docs are sufficient)
- CLI with Typer (existing pattern in bae works)

### Phase 2: Needs Validation Research
- **Staleness detection heuristics** -- what hash algorithm? SHA256 of field names + types? Include instruction string?
- **Optimizer comparison** -- BootstrapFewShot vs MIPROv2 vs SIMBA. When to recommend each? Need empirical data on cost/quality tradeoffs.
- **Dataset size heuristics** -- "20 examples minimum" is from DSPy docs, but bae's graphs produce 2+ examples per trace. Research: how many traces needed to cover all paths?

### Phase 3: Research During Implementation
- **LLM-as-judge bias mitigation** -- position bias, verbosity bias documented. Research: which biases matter most for bae's use case? Test with real graph outputs.
- **Caching strategy** -- cache key should be (input, graph hash, metric hash). Research: does DSPy provide predictor hash? If not, how to compute?

**Overall assessment:** Phase 1 is well-understood. Phase 2 needs targeted validation. Phase 3 can research during implementation.

---

## Confidence Assessment

| Area | Confidence | Reasoning |
|------|------------|-----------|
| **Stack (DSPy sufficiency)** | HIGH | DSPy 3.1.3 docs verified. MIPROv2/SIMBA APIs confirmed. No external framework needed. |
| **Features (progressive tiers)** | HIGH | Pattern is sound and validated across 6 frameworks. Tier structure is proven. |
| **Architecture (module boundaries)** | MEDIUM-HIGH | Graph introspection is solid. Eval wrapper design is clean. Metric abstraction needs validation. |
| **Pitfalls (false confidence risk)** | HIGH | Validated against multiple sources (HoneyHive, Confident AI, arxiv). Central risk is real and documented. |
| **LLM-as-judge auto-generation** | MEDIUM | Novel approach (no precedent). Field descriptions as rubric is logical but untested. |
| **Build order** | HIGH | Dependency chain is clear: package discovery → eval → optimize. Progressive reveals dependencies naturally. |

**Gaps to address during planning:**
1. **Metric abstraction API** -- bae-native vs DSPy-native signature. Needs design review with Dzara.
2. **Staleness detection algorithm** -- hashing strategy for node schemas. Needs prototype.
3. **Dataset generation helpers** -- how to auto-generate diverse traces? Needs experimentation.
4. **Cost tracking integration** -- does PydanticAI backend expose token counts? Needs investigation.

---

## Sources (Aggregated)

### PRIMARY SOURCES (HIGH confidence)
- [DSPy Evaluate API](https://dspy.ai/api/evaluation/Evaluate/)
- [DSPy EvaluationResult](https://dspy.ai/api/evaluation/EvaluationResult/)
- [DSPy Metrics](https://dspy.ai/learn/evaluation/metrics/)
- [DSPy MIPROv2 API](https://dspy.ai/api/optimizers/MIPROv2/)
- [DSPy SIMBA API](https://dspy.ai/api/optimizers/SIMBA/)
- [DSPy Optimizers Overview](https://dspy.ai/learn/optimization/optimizers/)
- [DSPy Cheatsheet](https://dspy.ai/cheatsheet/)
- [DSPy PyPI](https://pypi.org/project/dspy/) (v3.1.3)
- [Typer PyPI](https://pypi.org/project/typer/) (v0.21.1)
- [Rich PyPI](https://pypi.org/project/rich/) (v14.3.2)
- [Copier PyPI](https://pypi.org/project/copier/) (v9.11.3)
- Bae codebase analysis (all modules in bae/)

### SECONDARY SOURCES (MEDIUM confidence)
- [Braintrust How to Eval](https://www.braintrust.dev/articles/how-to-eval)
- [Braintrust CI/CD Tools](https://www.braintrust.dev/articles/best-ai-evals-tools-cicd-2025)
- [Promptfoo CLI](https://www.promptfoo.dev/docs/usage/command-line/)
- [DeepEval Getting Started](https://deepeval.com/docs/getting-started)
- [Inspect AI](https://inspect.aisi.org.uk/)
- [Monte Carlo: LLM-as-Judge Best Practices](https://www.montecarlodata.com/blog-llm-as-judge/)
- [Evidently AI: LLM-as-Judge Guide](https://www.evidentlyai.com/llm-guide/llm-as-a-judge)
- [HoneyHive: Avoiding Common Pitfalls](https://www.honeyhive.ai/post/avoiding-common-pitfalls-in-llm-evaluation)
- [arXiv: Justice or Prejudice?](https://arxiv.org/abs/2410.02736) (LLM-as-judge biases)
- [Copier vs Cookiecutter comparison](https://medium.com/@gema.correa/from-cookiecutter-to-copier-uv-and-just-the-new-python-project-stack-90fb4ba247a9)

### ECOSYSTEM SURVEYS (LOW confidence, landscape awareness)
- [AI Multiply: LLM Eval Landscape 2026](https://research.aimultiple.com/llm-eval-tools/)
- [Confident AI: Top LLM Eval Tools 2025](https://www.confident-ai.com/blog/greatest-llm-evaluation-tools-in-2025)

---

## Ready for Requirements

All 4 research files have been synthesized. Key findings extracted. Roadmap implications derived with phase structure. Confidence assessed. Research flags identified.

**Next step:** Orchestrator can proceed to requirements definition (feature breakdown, acceptance criteria, implementation tasks).

**Critical handoffs to roadmapper:**
1. **Phase structure** is dependency-driven: eval foundation → optimize integration → polish
2. **Metric abstraction** is the most consequential API design decision
3. **False confidence mitigation** must be baked into Tier 0 from day one
4. **No scaffolding** in Phase 1/2 (YAGNI until proven needed)
5. **DSPy sufficiency** means no external framework dependencies

---

*Research synthesis complete: 2026-02-08*
*Source files: STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*
