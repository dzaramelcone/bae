# Pitfalls: v3.0 Eval/Optimization DX

**Domain:** Adding eval frameworks, optimization DX, CLI tooling, and compiled artifact management to an existing agent graph framework
**Researched:** 2026-02-08
**Confidence:** HIGH for DX/DSPy pitfalls (grounded in codebase analysis + verified patterns), MEDIUM for LLM-as-judge and dataset pitfalls (WebSearch-verified against multiple sources)

---

## Critical Pitfalls

Mistakes that cause rewrites, misleading eval results, or developer abandonment.

---

### Pitfall 1: "Accessible Evals" That Produce Misleading Results

**What goes wrong:**
The stated goal is to make evals "super accessible and friendly." The most dangerous outcome is eval tooling that's easy to use but gives developers false confidence in their graph's quality. A zero-config eval that reports "92% accuracy" on a bad metric with a tiny dataset is worse than no eval at all -- it tells the developer "ship it" when they shouldn't.

**Why it happens in bae specifically:**
Bae's current only metric is `node_transition_metric` -- it checks whether the LLM predicted the correct *type name* of the next node. This is a structural check, not a quality check. It answers "did the graph take the right path?" but not "did the LLM produce a good outfit recommendation?" or "was the vibe check accurate?" If the zero-config eval defaults to this metric, developers will optimize for routing correctness and mistake it for overall quality.

The `ootd.py` example illustrates this perfectly: `node_transition_metric` would report 100% if the graph always routes `IsTheUserGettingDressed -> AnticipateUsersDay -> RecommendOOTD`. But that tells you nothing about whether the outfit is good, whether the vibe check captured the user's mood, or whether the final response is natural.

**Consequences:**
- Developer thinks graph is "optimized" when only routing is optimized
- Actual output quality (outfit relevance, tone, accuracy) never measured
- False confidence leads to shipping bad product and blaming bae when users complain
- Developer loses trust in the entire eval system and abandons it

**Warning signs:**
- All evals report high scores without custom metrics
- Developers never write domain-specific metrics
- `node_transition_metric` is the only metric used in production
- Eval results don't change when you deliberately make the graph worse at producing good content

**Prevention:**
1. **Make the zero-config tier honest about what it measures.** Default eval output should say "Routing accuracy: 92% (structural only -- does not measure output quality)" with an explicit callout that this is table stakes, not quality.
2. **Force a "metric moment" early.** The first time a developer runs `bae eval`, show a message: "You're using the default routing metric. For meaningful evals, add a quality metric. Run `bae eval --help-metrics` to see how."
3. **Provide a one-liner LLM-as-judge metric** that's easy to adopt as a step up from routing-only. Something like `bae.metrics.llm_judge("Is this a good outfit recommendation?")`. Low friction, meaningfully better than default.
4. **Show metric coverage in eval output.** "3 nodes evaluated. Routing: all. Quality: 0/3 nodes have quality metrics." This creates healthy pressure to add quality metrics without blocking the developer.

**Phase to address:** Phase 1 (eval foundation). The progressive complexity tiers must be designed with this pitfall in mind from day one. The default tier must be honest, and the upgrade path must be frictionless.

---

### Pitfall 2: Metric Design that Optimizes for the Wrong Thing

**What goes wrong:**
DSPy's optimization loop will relentlessly optimize whatever metric you give it. If the metric is poorly designed -- too easy to game, measuring a proxy rather than the real goal, or not discriminating enough between good and bad outputs -- BootstrapFewShot will find demonstrations that maximize the metric without improving actual quality. The optimizer is a perfect employee: it does exactly what you measure, not what you mean.

**Why it happens in bae specifically:**
Bae's `node_transition_metric` uses case-insensitive *substring matching*:

```python
match = expected_norm in predicted_norm or predicted_norm in expected_norm
```

This means `"End"` matches `"EndNode"`, `"The next node should be EndNode"` matches `"EndNode"`, and critically, `"Node"` would match anything containing "Node". The metric is deliberately lenient to handle LLM output variation, but this leniency means BootstrapFewShot can select demonstrations that produce sloppy outputs (like "EndNode maybe?") and still get 100% scores.

When developers write their own metrics for v3.0, they'll face the same trap: metrics that are too easy produce useless optimization, and metrics that are too strict produce no demonstrations (BootstrapFewShot can't bootstrap if the metric never returns True).

**Consequences:**
- Optimization "succeeds" but output quality doesn't improve
- Compiled prompts with demonstrations that game the metric
- Developer confusion: "I optimized but it's not better"
- Over-optimization: prompts become hyper-specialized to the training set

**Warning signs:**
- Optimization completes very quickly with 100% metric scores
- Compiled prompts perform worse on new inputs than uncompiled prompts
- All bootstrapped demonstrations look similar (overfitting)
- Metric returns True for outputs a human would reject

**Prevention:**
1. **Provide metric validation tooling.** Before optimization, run the metric against a few known-good and known-bad examples. If it returns True for known-bad outputs, warn: "Your metric may be too lenient."
2. **Document the trace parameter contract.** DSPy metrics must return `bool` when `trace is not None` (bootstrap mode -- stricter, used for selecting demonstrations) and `float` when `trace is None` (evaluation mode -- more nuanced). Bae should document this and provide a helper: `bae.metrics.dual_mode(strict_fn, score_fn)` that handles the mode switch.
3. **Ship example metrics for common patterns.** "Field completeness" (are all output fields non-empty?), "LLM-as-judge" (does a judge LLM rate the output well?), "Schema conformance" (does the output parse cleanly?). These are better starting points than `node_transition_metric`.
4. **Warn when BootstrapFewShot gets 100%.** If all bootstrapped demos pass the metric, flag: "All demos passed -- consider a stricter metric to differentiate good from great."

**Phase to address:** Phase 1 (eval foundation) for metric helpers and documentation. Phase 2 (optimization DX) for validation tooling.

---

### Pitfall 3: Compiled Artifacts Silently Go Stale

**What goes wrong:**
Compiled artifacts (`.json` files from `save_optimized()`) contain few-shot demonstrations baked from a specific graph structure, specific node field schemas, and a specific LLM model. When any of these change, the compiled artifacts become stale -- they contain demonstrations for fields that no longer exist, or examples from a model that behaves differently. But the system silently loads them anyway, because `load_optimized()` just checks if the file exists.

**Why it happens in bae specifically:**
Bae's current `load_optimized()` creates a fresh predictor with `node_to_signature(node_cls)` and loads state from JSON. If the node class changed (added a field, renamed a field, changed a Dep), the signature has changed but the loaded state is for the old signature. DSPy's `Predict.load()` doesn't validate signature compatibility -- it just overwrites the demos list.

The `save_optimized` format is `{NodeClassName}.json` -- no version, no hash, no metadata about what graph/model/schema produced it. Two months from now, Dzara changes `RecommendOOTD` to add a `style_notes` field. The compiled artifact still has demos without `style_notes`. `OptimizedLM` loads it, the demos show the LLM an old schema, and the LLM gets confused.

**Consequences:**
- Compiled prompts contain demonstrations for stale schemas
- LLM sees old-format examples and produces outputs that don't match current schema
- No error, no warning -- just degraded quality that's hard to diagnose
- Developer blames the LLM or the graph when the real problem is stale compiled artifacts

**Warning signs:**
- Graph changes don't improve (or worsen) eval scores despite re-running evals
- LLM output fields don't match expected schema
- OptimizedLM silently falls back to naive predictor without explanation
- Developer hasn't re-run optimization after schema changes

**Prevention:**
1. **Hash the node signature into the compiled artifact.** When saving, include a hash of the node's field names + types + instruction. When loading, compare hashes. If they don't match, warn loudly: "Compiled artifact for RecommendOOTD is stale (schema changed). Re-run optimization."
2. **Include metadata in compiled artifacts.** Save alongside the demos: `{"bae_version": "3.0", "node_hash": "abc123", "compiled_at": "2026-02-08", "model": "claude-sonnet-4", "dataset_size": 50}`. This makes staleness visible.
3. **`bae compile --check` command.** Validates all compiled artifacts against current graph schemas without re-running optimization. Quick, cheap, run it in CI.
4. **Never silently fall back.** If `OptimizedLM` loads a stale artifact, it should warn, not silently use it. If the artifact is incompatible, raise or fall back to naive with a visible log line.

**Phase to address:** Phase 2 (compiled artifact management). Build hashing and staleness detection into save/load from the start.

---

### Pitfall 4: BootstrapFewShot Selects Suboptimal Demonstrations

**What goes wrong:**
BootstrapFewShot stops searching after finding K demonstrations that pass the metric. These may not be the best K demonstrations -- just the first K that pass. With a lenient metric (like `node_transition_metric`), this means the first 4 examples that produce the right type name become the baked demonstrations, regardless of whether they represent high-quality outputs.

**Why it happens in bae specifically:**
Bae's current BootstrapFewShot config is:
```python
BootstrapFewShot(
    metric=node_transition_metric,
    max_bootstrapped_demos=4,
    max_labeled_demos=8,
    max_rounds=1,
)
```

`max_rounds=1` means one pass through the training data. `max_bootstrapped_demos=4` means it stops at 4. The first 4 passing examples become the demonstrations forever. With a routing-only metric, these could be 4 examples where the LLM happened to output the right type name but gave terrible content.

DSPy offers `BootstrapFewShotWithRandomSearch` and `BootstrapFewShotWithOptuna` that generate many candidate demo sets and search for the best combination. Bae doesn't expose these or provide a path to them.

**Consequences:**
- Compiled prompts contain mediocre demonstrations
- Optimization plateaus quickly
- Developer can't improve beyond initial BootstrapFewShot results
- No path from "basic optimization" to "serious optimization"

**Warning signs:**
- Eval scores plateau after first optimization run
- Changing `max_rounds` or `max_bootstrapped_demos` doesn't improve scores
- Demonstrations in compiled artifacts are of varying quality
- Advanced users ask "how do I use MIPROv2 with bae?"

**Prevention:**
1. **Expose optimizer selection in CLI and API.** `bae optimize --optimizer bootstrap` (default), `bae optimize --optimizer mipro`, `bae optimize --optimizer gepa`. Make it easy to upgrade.
2. **Document the progression.** "Start with BootstrapFewShot (cheap, fast). If you plateau, try MIPROv2 (optimizes instructions too). For production, consider GEPA."
3. **Don't hard-code BootstrapFewShot config.** Let users pass `max_rounds`, `max_bootstrapped_demos`, `max_labeled_demos` as CLI flags or config. The current hard-coded `max_rounds=1` is too conservative for serious use.
4. **Show demo quality in eval output.** After optimization, show the actual demonstrations that were selected. Let the developer inspect them and judge quality.

**Phase to address:** Phase 2 (optimization DX). The optimizer abstraction should make it easy to swap optimizers without changing graph code.

---

### Pitfall 5: Eval Dataset is Too Small or Not Representative

**What goes wrong:**
DSPy recommends "Even 20 input examples can be useful, though 200 goes a long way." But for bae's graphs, each "example" is an entire graph execution trace. Collecting 200 full traces of the OOTD graph means 200 different user messages, weather conditions, calendar states, and outfit recommendations. This is expensive (each trace costs multiple LLM calls) and time-consuming.

Developers will start with 5-10 examples, get mediocre results, and either: (a) conclude optimization doesn't work for their use case, or (b) optimize on too-small data and overfit.

**Why it happens in bae specifically:**
Bae's `trace_to_examples()` converts a graph trace into DSPy Examples -- one per node transition. A 3-node OOTD trace produces 2 examples. To get 20 examples per node type, you need at least 10 full graph executions. With branching graphs (5+ node types), you need more executions to cover all paths.

The current pipeline has no tooling for: generating diverse traces, managing eval datasets, or validating dataset coverage across graph paths.

**Consequences:**
- Optimization on 5 traces overfits to those specific inputs
- Uncommon graph paths never get demonstrated
- Compiled prompts work great for "ugh i just got up" but fail for edge cases
- Developer falsely concludes "optimization didn't help" because they tested on training data

**Warning signs:**
- Training and eval scores are both high, but production quality is low
- All traces in the dataset have similar inputs
- Some node types have 0 examples (branching paths never taken)
- Optimization completes instantly (not enough data to bootstrap)

**Prevention:**
1. **Provide dataset generation helpers.** `bae dataset generate --module examples.ootd --count 50 --vary user_message` runs the graph with varied inputs and saves traces. Even a naive variation strategy (GPT to generate diverse user messages) is better than hand-crafting 5 examples.
2. **Show coverage in eval output.** "Dataset: 20 traces, 40 transitions. StartNode: 20 examples. AnticipateUsersDay: 20 examples. RecommendOOTD: 20 examples." Flag any node type with fewer than 10 examples.
3. **Split train/eval automatically.** When running `bae optimize`, auto-split the dataset (80/20). Show train score AND eval score. If train >> eval, warn: "Possible overfitting."
4. **Document minimum dataset sizes.** "For BootstrapFewShot: minimum 10 examples per node type. For MIPROv2: minimum 50 per node type. For GEPA: minimum 200 per node type." Give developers a target.
5. **Persistent dataset storage.** `my_domain/evals/dataset.json` with append-on-run capability. Every `bae run` can optionally save its trace to the dataset.

**Phase to address:** Phase 1 (eval foundation) for dataset format and storage. Phase 2 (optimization DX) for generation helpers and coverage reporting.

---

## Moderate Pitfalls

Mistakes that cause delays, frustrating DX, or technical debt.

---

### Pitfall 6: LLM-as-Judge Bias and Cost Explosion

**What goes wrong:**
LLM-as-judge is the natural "step up" from structural metrics for evaluating output quality. But LLM judges have well-documented biases: position bias (~40% decision flips when answer order swaps), verbosity bias (~15% score inflation for longer outputs), and self-enhancement bias (5-7% boost for outputs from the same model family). Additionally, running a judge LLM on every eval example adds significant cost -- if the eval dataset has 200 examples and each judge call costs $0.01, that's $2 per eval run, which adds up during iteration.

**Why it happens in bae specifically:**
Bae's graphs produce rich, multi-field outputs (OOTD has 6 fields including lists and URLs). A judge LLM needs to evaluate multiple dimensions -- is the outfit weather-appropriate? Is the tone right? Are the accessories coherent? A single "rate 1-5" prompt conflates all dimensions. But separate prompts per dimension multiply cost.

If bae ships a default `llm_judge` metric, developers will use it without understanding the biases. They'll see "Judge score: 4.2/5" and trust it, not realizing the judge inflates scores for verbose responses or penalizes concise ones.

**Consequences:**
- Judge scores are systematically biased in ways developers don't see
- Cost of eval runs discourages frequent evaluation
- Developers optimize for "what the judge likes" rather than "what users want"
- Judge model updates silently change evaluation standards (drift)

**Warning signs:**
- Judge scores are consistently high (4+/5) even for mediocre outputs
- Adding more text to outputs always improves scores
- Switching judge models changes scores significantly
- Eval runs are expensive enough that developers skip them

**Prevention:**
1. **Document biases explicitly.** When the LLM-as-judge metric is used, show: "Note: LLM judges have known biases (verbosity, position). Use for relative comparisons, not absolute quality."
2. **Provide multi-criteria judging.** Instead of one "rate overall quality" prompt, decompose: `relevance`, `coherence`, `tone`. Score each separately. This reduces conflation and makes biases more visible.
3. **Cache judge results aggressively.** Same output + same judge prompt = same score. Don't re-judge unchanged outputs. This reduces cost during iteration.
4. **Make judge cost visible.** After eval, show: "Judge cost: $0.47 (23 LLM calls). Cached: 177 results reused." Transparency prevents surprise bills.
5. **Offer a free alternative.** For quick iteration, provide heuristic metrics that don't call an LLM: field completeness, output length bounds, regex checks. These are free, fast, and useful as guardrails alongside the judge.

**Phase to address:** Phase 2 (metric library). Ship heuristic metrics first, LLM-as-judge second.

---

### Pitfall 7: CLI Config File Hell

**What goes wrong:**
Eval frameworks are notorious for config complexity. Promptfoo's YAML-heavy workflow "makes it hard to customize or scale" and "adds friction for developers." If bae's CLI requires a `bae.yaml` or `bae.toml` with deeply nested configuration for eval datasets, metrics, optimizers, and output formats, developers will bounce at the setup step.

**Why it happens in bae specifically:**
Bae's v3.0 goal includes CLI commands for "create, run, eval, optimize, inspect." Each command needs configuration: which graph module, which dataset, which metric, which optimizer, which output format, where to save artifacts. If all of this requires a config file, the developer has to learn the config schema before running their first eval.

The existing CLI already has a good pattern: `bae graph show examples.ootd` -- module path as argument, sensible defaults. But eval is more complex than visualization. The temptation is to add a config file for the complex parts.

**Consequences:**
- Developer has to create a config file before running first eval
- Config file format becomes an API surface to maintain
- Config validation errors are a new class of bug
- Migration pain when config format changes between bae versions

**Warning signs:**
- `bae eval` requires a config file (no zero-config path)
- Config file has more than 20 options
- Developers copy-paste config files from examples without understanding them
- Config file format changes between minor versions

**Prevention:**
1. **CLI arguments first, config file optional.** `bae eval examples.ootd` should work with zero config. Every option should be a CLI flag before it's a config key. Config file is for power users who want to save their CLI args.
2. **Convention over configuration.** If the module is `examples.ootd`, look for `examples/ootd_evals/` for eval data by convention. Don't require explicit paths.
3. **`bae init` generates minimal config.** If the developer wants a config file, `bae init` generates one with comments explaining each option. But it's never required.
4. **Progressive config complexity.** Start with zero config, add flags as needed: `bae eval examples.ootd --metric quality --dataset evals/ootd.json --optimizer mipro`. Each flag adds one dimension. Never require all dimensions at once.

**Phase to address:** Phase 1 (CLI foundation). Design the CLI argument structure before touching config files.

---

### Pitfall 8: Progressive Complexity Tiers With Cliff Effects

**What goes wrong:**
Progressive complexity means "start simple, add sophistication as needed." The pitfall is cliff effects -- sharp jumps in complexity between tiers. Tier 0 (zero-config) is trivial, but to get to Tier 1 (custom metrics), the developer has to learn DSPy Examples, understand the `trace` parameter, write a function with a specific signature, and figure out how to pass it to the optimizer. The gap between "just works" and "slightly customized" is a cliff.

**Why it happens in bae specifically:**
Bae's optimization pipeline is tightly coupled to DSPy internals. Writing a custom metric requires understanding:
1. `dspy.Example` structure (which fields, `with_inputs()`)
2. The `pred` object shape (which attribute has the prediction?)
3. The `trace` parameter convention (None = eval mode, not None = bootstrap mode)
4. How `node_to_signature()` maps node fields to signature fields

None of this is bae-specific knowledge -- it's DSPy plumbing. If bae doesn't abstract these details, the tier jump requires learning a second framework.

**Consequences:**
- Developers use zero-config tier forever because the next tier is too hard
- Developers who attempt custom metrics make subtle errors (wrong return type, wrong field names)
- The "progressive" complexity isn't progressive -- it's binary (zero-config or DSPy expert)
- Documentation for the custom tier is actually DSPy documentation, creating a maintenance burden

**Warning signs:**
- No one uses custom metrics despite the feature existing
- Developer questions are about DSPy internals, not bae concepts
- Custom metric examples are 20+ lines of boilerplate
- Error messages from custom metrics reference DSPy types the developer hasn't seen

**Prevention:**
1. **Abstract DSPy from the metric interface.** Bae metrics should take bae types, not DSPy types. `def my_metric(node: Node, output: Node, trace: list[Node]) -> float` is understandable. `def my_metric(example: dspy.Example, pred, trace=None) -> float | bool` is not.
2. **Provide a metric builder.** `bae.metrics.field_score("final_response", judge="Is this a helpful response?")` creates a metric without the developer writing a function.
3. **Small step between tiers.** Zero-config -> add one line (`metric = bae.metrics.llm_judge("Is this good?")`) -> write a custom function (`def my_metric(output: RecommendOOTD) -> float`). Each step adds one concept.
4. **Error messages at the bae level.** If a custom metric returns the wrong type, say "Metric must return float (got str). See `bae eval --help-metrics`." Don't let DSPy's error messages leak through.

**Phase to address:** Phase 1 (eval foundation). The metric abstraction layer is the most important design decision.

---

### Pitfall 9: Mermaid Diagrams as Write-Only Artifacts

**What goes wrong:**
Auto-generated mermaid diagrams (`graph.to_mermaid()`) are useful for initial understanding but become stale documentation. The existing CLI (`bae graph show`) generates diagrams, but if the v3.0 scaffolding auto-generates `graph.md` files with embedded mermaid, those files will drift from the actual graph code. Developers won't update them because they're auto-generated, but they also won't re-generate them because they forgot the diagram exists.

**Why it happens in bae specifically:**
Bae's `to_mermaid()` generates structural diagrams showing nodes and edges. But for eval DX, developers also want to see: which nodes have quality metrics, which have compiled artifacts, which paths have eval coverage. If the diagram only shows structure, it's useful once (at graph creation) and never again.

The v3.0 goal includes "autogenerated mermaid diagrams" in scaffolded packages. If these are static files committed to git, they're stale the moment a node is added.

**Consequences:**
- Diagrams in docs don't match actual graph structure
- Developers distrust auto-generated docs
- Maintenance burden: "update the diagram" becomes a chore
- Diagrams show structure but not the eval/optimization state developers care about

**Warning signs:**
- `graph.md` shows 3 nodes but the graph actually has 5
- No one runs `bae graph mermaid` after initial setup
- Diagrams don't include eval-relevant information
- PRs with node changes don't update diagrams

**Prevention:**
1. **Generate on demand, don't persist.** `bae graph show` generates live from code. Don't save `.md` files with embedded diagrams. If a developer wants a diagram in their docs, they run a command and paste.
2. **If persisting, include a freshness check.** Add a comment: `<!-- Generated from examples.ootd on 2026-02-08. Run 'bae graph mermaid examples.ootd' to regenerate. -->` and optionally `bae graph check` that compares generated vs stored.
3. **Make diagrams eval-aware.** Show eval state on the diagram: nodes with quality metrics get a green border, nodes with only routing metrics get yellow, nodes with no metrics get red. This makes the diagram useful beyond initial setup.
4. **Keep diagrams minimal.** Don't try to show every field, every dep, every recall. Node names and edges are enough for the diagram. Details go in `bae inspect`.

**Phase to address:** Phase 3 (scaffolding/DX). Don't invest in diagram persistence until the eval system is stable.

---

### Pitfall 10: Package Scaffolding That Creates Migration Pain

**What goes wrong:**
Scaffolding tools (like `bae init my_domain`) generate project structures with specific file layouts, naming conventions, and configuration patterns. If the scaffolded structure is over-opinionated -- requiring specific directory names, specific file patterns, or specific import structures -- developers can't adopt bae incrementally. They either scaffold a fresh project or fight the conventions.

**Why it happens in bae specifically:**
The v3.0 goal includes "package scaffolding: `my_domain/graph.py` + `graph.md`." If `bae init` generates a rigid structure:
```
my_domain/
  graph.py      # must export `graph`
  evals/
    dataset.json
    metrics.py
  compiled/
    *.json
  graph.md
```
...then developers with existing code must reorganize to fit. And if the convention changes in v3.1, all scaffolded projects break.

**Consequences:**
- Developers with existing graphs can't adopt the eval DX without restructuring
- Scaffold conventions become an API surface that's hard to change
- Too many generated files overwhelm developers ("I just wanted to eval my graph")
- Convention disagreements (is it `evals/` or `eval/`? `compiled/` or `.compiled/`?)

**Warning signs:**
- `bae init` generates more than 3 files
- Developers need to move existing code to fit the scaffold
- CLI commands fail because files aren't in expected locations
- Scaffold conventions change between versions

**Prevention:**
1. **Scaffolding should be additive, not prescriptive.** `bae init` creates the minimum: an eval config pointing to the developer's existing graph module. It doesn't move code or create directory structures.
2. **Convention discovery, not convention enforcement.** The CLI should look for graphs by module path (already works: `bae graph show examples.ootd`), not by file location. If the developer puts their eval dataset in `tests/eval_data.json` instead of `evals/dataset.json`, that should work.
3. **Scaffold minimal, document maximal.** Generate one file with comments explaining the recommended structure. Don't generate the structure itself.
4. **No scaffold at all for v3.0.** Start with the CLI commands working on arbitrary module paths. Add scaffolding later if developers ask for it. YAGNI.

**Phase to address:** Phase 3 (DX polish). Don't build scaffolding until the eval/optimize workflow is proven without it.

---

### Pitfall 11: Eval Framework Disconnected from the Compile Loop

**What goes wrong:**
If eval and optimization are separate workflows -- `bae eval` reports scores, `bae optimize` runs BootstrapFewShot, but there's no connection between them -- developers don't know when to re-optimize, how optimization affected eval scores, or whether their latest code change regressed quality.

**Why it happens in bae specifically:**
Bae's current architecture has `optimize_node()` and `node_transition_metric()` in the same file but they're not part of an integrated workflow. The developer must manually: (1) collect traces, (2) convert to examples, (3) run optimization, (4) save artifacts, (5) load artifacts, (6) run evals to see if optimization helped. Each step is a separate function call with no orchestration.

**Consequences:**
- Developer optimizes once, never again
- No baseline comparison: "was this optimization actually better?"
- No regression detection: "did my last code change break things?"
- Eval and optimization feel like separate tools instead of one workflow

**Warning signs:**
- Developer runs `bae optimize` once and never again
- No before/after comparison in optimization output
- Eval scores aren't saved or tracked over time
- Developer can't answer "is my graph better than yesterday?"

**Prevention:**
1. **`bae optimize` should eval before and after.** Run eval with current compiled artifacts (baseline), optimize, run eval again, show delta: "Routing: 85% -> 93% (+8%). Quality: 3.2 -> 3.8 (+0.6)."
2. **Save eval results with timestamps.** `my_domain/evals/history.json` with timestamped eval runs. `bae eval --history` shows trend.
3. **`bae eval --compare compiled naive` shows the value of optimization.** Run the graph with and without compiled artifacts, compare scores.
4. **Integrate eval into `bae run`.** After a graph run, optionally score it: `bae run examples.ootd --eval`. This makes eval part of the development loop, not a separate chore.

**Phase to address:** Phase 2 (optimization DX). The eval-optimize loop should be a single command with before/after reporting.

---

### Pitfall 12: Node-Level vs Graph-Level Eval Confusion

**What goes wrong:**
Bae's optimization is node-level (each node gets its own predictor, its own demonstrations). But quality is often graph-level -- "was the overall output good?" Developers think in graph-level terms ("is my outfit recommendation pipeline good?") but the eval infrastructure works at node-level. This creates a mismatch where developers write graph-level metrics but the optimizer needs node-level metrics.

**Why it happens in bae specifically:**
`optimize_node()` takes a single `node_cls` and filters the trainset to examples for that node type. The metric evaluates one node transition at a time. But the developer's quality question -- "is the final outfit recommendation good?" -- depends on all nodes working together. The vibe check quality affects the outfit quality, but they're evaluated independently.

**Consequences:**
- Node-level metrics miss cross-node quality issues
- Developer writes a metric for the terminal node only, ignoring intermediate quality
- Optimizing one node degrades another (no joint optimization)
- Eval scores per-node are high but end-to-end quality is low

**Warning signs:**
- All node-level metrics are high but users complain about output quality
- Developer only writes metrics for the terminal node
- Optimizing one node changes another node's behavior unexpectedly
- No end-to-end eval exists

**Prevention:**
1. **Provide both node-level and graph-level eval.** `bae eval examples.ootd` evaluates end-to-end (graph-level). `bae eval examples.ootd --per-node` breaks it down. Default to graph-level because that's what developers care about.
2. **Graph-level metrics that inspect the trace.** A graph-level metric receives the full trace and the terminal node. It can check: "was the vibe check good AND the outfit appropriate AND the tone right?"
3. **Document the relationship.** "Node-level optimization improves individual transitions. Graph-level eval measures overall quality. Use both: optimize per-node, evaluate per-graph."
4. **Show cross-node effects.** After optimization, show: "Optimized AnticipateUsersDay. Graph-level eval changed from 3.5 to 3.8. RecommendOOTD node-level changed from 4.0 to 4.2." This surfaces cross-node effects.

**Phase to address:** Phase 1 (eval foundation). The eval framework should support both levels from the start, defaulting to graph-level.

---

## Minor Pitfalls

Mistakes that cause annoyance but are fixable.

---

### Pitfall 13: Eval Output That's Hard to Read

**What goes wrong:**
Eval output is either too verbose (raw JSON of every example) or too sparse (a single number). Developers need a middle ground: summary scores, worst-performing examples, and actionable next steps.

**Why it happens in bae specifically:**
The current CLI output for `bae run` is minimal: trace list and final node. For eval, there's no CLI output at all -- it's all programmatic. When v3.0 adds `bae eval`, the first version will likely dump all results, overwhelming the developer.

**Prevention:**
1. **Summary first, details on request.** Default: "Eval: 85% routing, 3.8/5 quality (23 examples). Worst: example #7 (quality: 1.2)." Add `--verbose` for per-example detail.
2. **Show actionable next steps.** "To improve: add quality metrics for AnticipateUsersDay (currently routing-only). Run `bae optimize` to compile."
3. **Color-code results.** Green for passing, yellow for marginal, red for failing. Make it visually scannable.

**Phase to address:** Phase 2 (CLI polish).

---

### Pitfall 14: Ignoring the Cost of Eval Runs

**What goes wrong:**
Each eval run that involves LLM calls costs money. During rapid iteration, a developer might run `bae eval` 20 times in an hour, each time making 50+ LLM calls. Without cost tracking or caching, the eval bill surprises them.

**Prevention:**
1. **Show estimated cost before running.** "This eval will make ~50 LLM calls (~$0.50). Proceed? [Y/n]" (or `--yes` to skip).
2. **Cache aggressively.** If the input and graph haven't changed, reuse cached traces. Only re-eval changed nodes.
3. **Offer a dry-run mode.** `bae eval --dry-run` shows what would be evaluated without making LLM calls.
4. **Track cumulative cost.** `bae eval --cost-report` shows total spend across all eval runs.

**Phase to address:** Phase 2 (optimization DX).

---

### Pitfall 15: DSPy Version Coupling

**What goes wrong:**
DSPy is actively developed and has breaking changes between versions. If bae's eval/optimization DX tightly couples to DSPy internals (Example format, Predict API, optimizer class signatures), DSPy updates break bae.

**Why it happens in bae specifically:**
Bae already imports `dspy.teleprompt.BootstrapFewShot`, `dspy.Predict`, `dspy.Example`, and `dspy.make_signature`. The v3.0 eval DX will add more DSPy surface area: `MIPROv2`, `GEPA`, metric conventions. Each import is a coupling point. DSPy moved from `dspy.teleprompt` to `dspy.optimizers` at some point, and class signatures evolve.

**Prevention:**
1. **Wrap DSPy imports in a single adapter module.** `bae._dspy_compat` handles all DSPy imports and provides stable internal APIs. If DSPy changes, only one module needs updating.
2. **Pin DSPy version in requirements.** Don't float. Test against specific DSPy versions.
3. **Abstract optimizer creation.** `bae.optimizers.create("bootstrap", ...)` instead of direct `BootstrapFewShot(...)` construction. The factory handles version differences.

**Phase to address:** Phase 1 (foundation). Establish the adapter pattern before adding more DSPy surface area.

---

## Phase-Specific Warning Summary

| Phase | Pitfall | Risk | Mitigation Priority |
|-------|---------|------|---------------------|
| Phase 1 (Eval Foundation) | #1: Accessible evals that mislead | CRITICAL | Honest default metrics, forced "metric moment" |
| Phase 1 (Eval Foundation) | #2: Metric design that optimizes wrong thing | CRITICAL | Metric validation, dual-mode helpers |
| Phase 1 (Eval Foundation) | #5: Dataset too small or not representative | HIGH | Dataset helpers, coverage reporting |
| Phase 1 (Eval Foundation) | #7: CLI config file hell | HIGH | CLI args first, config optional |
| Phase 1 (Eval Foundation) | #8: Progressive complexity cliff effects | HIGH | Abstract DSPy from metric interface |
| Phase 1 (Eval Foundation) | #12: Node-level vs graph-level confusion | HIGH | Support both, default to graph-level |
| Phase 1 (Eval Foundation) | #15: DSPy version coupling | MEDIUM | Adapter module, pinned version |
| Phase 2 (Optimization DX) | #3: Compiled artifacts go stale | HIGH | Signature hashing, staleness check |
| Phase 2 (Optimization DX) | #4: BootstrapFewShot suboptimal demos | MEDIUM | Expose optimizer selection, configurable params |
| Phase 2 (Optimization DX) | #6: LLM-as-judge bias and cost | MEDIUM | Document biases, cache results, show cost |
| Phase 2 (Optimization DX) | #11: Eval disconnected from compile loop | HIGH | Before/after in optimize command |
| Phase 2 (Optimization DX) | #13: Hard-to-read eval output | MEDIUM | Summary-first output |
| Phase 2 (Optimization DX) | #14: Eval run cost surprises | LOW | Cost tracking, caching |
| Phase 3 (DX Polish) | #9: Mermaid diagrams as write-only | LOW | Generate on demand, eval-aware |
| Phase 3 (DX Polish) | #10: Scaffolding migration pain | MEDIUM | Additive not prescriptive, YAGNI |

## Key Design Decisions Forced by Pitfalls

These pitfalls force design decisions that should be made before coding starts:

1. **What does the default eval measure, and how honest is it about what it doesn't measure?** (Pitfall #1)
   The zero-config tier must be transparent about its limitations. This is a UX decision, not a technical one.

2. **What is the metric interface -- DSPy types or bae types?** (Pitfall #8)
   If metrics take `(example: dspy.Example, pred, trace=None)`, developers need to learn DSPy. If metrics take `(output: Node, trace: list[Node]) -> float`, the abstraction is clean but bae must translate internally. This is the most consequential API design decision in v3.0.

3. **Are compiled artifacts self-describing or opaque?** (Pitfall #3)
   Adding metadata (hash, model, date, dataset size) to compiled artifacts costs almost nothing at save time but prevents an entire class of staleness bugs. Decide this before the first artifact is saved.

4. **Is eval graph-level or node-level by default?** (Pitfall #12)
   Developers think in graph-level terms. DSPy optimizes node-level. The eval framework must bridge this gap.

5. **Is configuration via CLI args or files?** (Pitfall #7)
   CLI-first is simpler and follows the existing `bae graph show` pattern. Config files are optional extras. This should be a firm design principle.

## The Central Risk: False Confidence

Pitfalls #1, #2, #5, #6, and #12 all point to the same root risk: **the eval system tells the developer their graph is good when it isn't.** This happens through:

- Metrics that measure the wrong thing (#1, #2)
- Datasets too small to catch edge cases (#5)
- Biased judges that inflate scores (#6)
- Node-level evals that miss graph-level failures (#12)

The mitigation is consistent: **be honest about what the eval measures and what it doesn't.** Every eval output should answer: "What did we measure? What didn't we measure? How confident are we?"

## Sources

**HIGH confidence (official documentation, codebase analysis):**
- [DSPy Metrics documentation](https://dspy.ai/learn/evaluation/metrics/) -- metric design, trace parameter contract
- [DSPy Evaluation Overview](https://dspy.ai/learn/evaluation/overview/) -- dataset requirements, evaluation best practices
- [DSPy Optimizers](https://dspy.ai/learn/optimization/optimizers/) -- BootstrapFewShot limitations, optimizer progression
- [DSPy BootstrapFewShot API](https://dspy.ai/api/optimizers/BootstrapFewShot/) -- configuration options
- Bae codebase analysis (optimizer.py, optimized_lm.py, compiler.py, cli.py, resolver.py, examples/ootd.py)

**MEDIUM confidence (WebSearch verified against multiple sources):**
- [HoneyHive: Avoiding Common Pitfalls in LLM Evaluation](https://www.honeyhive.ai/post/avoiding-common-pitfalls-in-llm-evaluation) -- 5 pitfall categories with solutions
- [Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge](https://arxiv.org/abs/2410.02736) -- 12 bias types, position/verbosity/self-enhancement quantified
- [Confident AI: LLM Evaluation Metrics](https://www.confident-ai.com/blog/llm-evaluation-metrics-everything-you-need-for-llm-evaluation) -- false confidence, metric limitations
- [Braintrust: Best Prompt Evaluation Tools 2025](https://www.braintrust.dev/articles/best-prompt-evaluation-tools-2025) -- promptfoo DX limitations, dataset management
- [Langfuse: LLM Evaluation 101](https://langfuse.com/blog/2025-03-04-llm-evaluation-101-best-practices-and-challenges) -- continuous evaluation practices
- [Weaviate: DSPy Optimizers](https://weaviate.io/blog/dspy-optimizers) -- BootstrapFewShot suboptimal selection
- [The Data Quarry: Working with DSPy Optimizers](https://thedataquarry.com/blog/learning-dspy-3-working-with-optimizers/) -- practical optimizer experiences
- [UX Patterns for CLI Tools](https://www.lucasfcosta.com/blog/ux-patterns-cli-tools) -- progressive disclosure, time to value

**LOW confidence (inferred from patterns, not directly verified):**
- DSPy `Predict.load()` signature compatibility behavior -- inferred from code inspection, not verified with DSPy tests
- Cross-node optimization effects -- logical inference, not empirically verified
- GEPA optimizer availability and API -- referenced in DSPy docs but not verified via Context7

---
*Pitfalls research for: Bae v3.0 Eval/Optimization DX*
*Researched: 2026-02-08*
