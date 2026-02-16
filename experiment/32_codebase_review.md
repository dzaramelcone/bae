# Codebase Review: bae Against the Prompt Design Specification

Analysis of the bae framework (`/Users/dzaramelcone/lab/bae`) against the findings in `experiment/31_prompt_design_spec.md`. Conducted 2026-02-15.

---

## 1. Current State: How bae Aligns With and Diverges From the Spec

### 1.1 The Central Design Decision — Mechanism B, Not A

The spec draws a critical distinction between **Mechanism A** (constrained decoding — logit masking that filters output tokens) and **Mechanism B** (schema-as-prompt — field names entering the autoregressive context window and steering computation). The spec recommends using B while avoiding A's damage to reasoning.

**bae does both simultaneously, and this is correct.**

In `bae/lm.py:441-461`, `ClaudeCLIBackend._run_cli_json()` sends the JSON schema via `--json-schema` to Claude CLI, which uses Claude's native structured output tool. This is constrained decoding (Mechanism A) on the *structural tokens* (field boundaries, JSON syntax). But the schema's field names and descriptions also enter the prompt context, providing Mechanism B's semantic steering.

The spec's recommendation at the end of Section 4 is: "never constrain the content within schema fields. Constrain only the structural tokens — the XML tags, the field boundaries, the ordering. Leave everything between the tags free-form." This is *exactly* what bae does. The JSON schema constrains the structure (which fields exist, their types), but field content is free-form text within those constraints.

**Alignment: Strong.** bae's architecture implements the spec's recommended approach by design.

### 1.2 Field Names as Cognitive Scaffolds

The spec's core finding is that field names do cognitive work — `assumptions`, `reasoning`, `completeness_check` activate relevant latent knowledge during autoregressive generation.

bae treats field names as the primary semantic signal. In `bae/lm.py:202-239`, `_build_fill_prompt()` constructs the prompt from:
1. Source node data (previous node as JSON — field names visible)
2. Resolved dep/recall values (as JSON under "context" key — field names visible)
3. Instruction (class name only)

The output schema (passed via `--json-schema`) also contains field names. So the LM sees field names in both the input context and the output constraint. This is Mechanism B applied twice.

In `bae/graph.py:55-57`, `_build_instruction()` returns only the class name. Docstrings are deliberately inert (phase 10 design decision). This means class names like `AnticipateUsersDay`, `RecommendOOTD`, `ChallengeProject` serve as the high-level instruction, while field names within those classes serve as the detailed cognitive scaffold.

**Alignment: Strong.** bae's "class name = instruction, fields = schema" design is a natural implementation of schema-as-cognitive-scaffold.

### 1.3 Field Ordering

The spec identifies field ordering as load-bearing: `assumptions` first (forces externalization before reasoning), `completeness_check` fourth (creates anticipation effect that improves upstream reasoning), `confidence` last (conditioned on gap analysis).

bae preserves field declaration order throughout. In `bae/lm.py:128-151`, `_build_plain_model()` iterates `target_cls.model_fields` (which preserves Python class declaration order). Pydantic v2 maintains insertion order. The JSON schema passed to the LM preserves this ordering.

However, **bae provides no guidance or enforcement on field ordering within user-defined nodes.** There is no mechanism to tell users that field order matters for LM output quality, and no tooling to help them get it right.

In the existing codebase:

- `examples/ootd.py:230-238` — `RecommendOOTD` declares: `wardrobe` (dep), `overall_vision`, `top`, `bottom`, `footwear`, `accessories`, `final_response`, `inspo`. The `overall_vision` field comes first among plain fields, which is good — it forces the LM to articulate a holistic vision before itemizing garments. But this ordering was intuitive, not principled.

- `bae/work/new_project.py:130-135` — `ExamineProblem` declares: `context` (recall), `probing_questions`, `satisfied`. The `probing_questions` field precedes `satisfied`, meaning the LM generates questions before deciding satisfaction — correct ordering for the same reason `assumptions` precedes `reasoning` in the spec.

**Divergence: Latent.** The ordering works by accident of good design instinct, not by framework guidance.

### 1.4 Presuppositional Field Naming

The spec's finding on presuppositional framing is one of its strongest: fields named `missed`, `errors`, `gaps` force the model to fabricate content because cooperative pressure demands accommodation of the existence presupposition. `completeness_check` (procedural framing) is the recommended alternative.

Scanning the codebase for presuppositional field names:

- `bae/work/execute_phase.py:85` — `VerifyGoal` has `gaps: list[str]`. This is presuppositional: it presupposes gaps exist. The LM will always populate this list.
- `bae/work/map_codebase.py:95` — `VerifyOutput` has `gaps: list[str]`. Same issue.
- `bae/work/execute_phase.py:57` — `SpotCheck` has `issues: list[str]`. Presuppositional.
- `bae/work/plan_phase.py:79` — `CheckPlan` has `issues: list[str]`. Presuppositional.
- `bae/work/plan_phase.py:61` — `ResearchPhase` has `blockers: list[str]`. Presuppositional.

None of these fields would correctly produce an empty list when there are no gaps/issues/blockers. The LM will always find something to report because the field name presupposes items exist.

**Divergence: Concrete.** Several fields in the work graphs use presuppositional framing that the spec identifies as harmful. These should be renamed or restructured (e.g., `verification_status` with a bool + optional detail, or `completeness_assessment: str`).

### 1.5 The Decision Matrix (Schema Complexity Scaled to Task/Model)

The spec provides a 2x2 matrix: easy/hard task x weak/strong model. Schema should be applied only to hard tasks, and scaled to model capability.

bae currently has no mechanism for this. Every node gets the same treatment: full JSON schema with all plain fields constrained. There is no way to say "for this node, use a simpler schema" or "for Opus, skip the schema on this node."

The `NodeConfig` class (`bae/node.py:148-156`) allows per-node LM override, so a user could pin a weaker model to a node that needs more scaffolding. But there is no way to vary the schema complexity — it is always the full set of plain fields.

**Divergence: Structural.** bae has no schema-complexity dial. Every fill call uses the full schema.

### 1.6 The Canary Protocol

The spec recommends periodically inserting nonsense fields to audit whether the LM is in compliance mode vs. genuine reasoning mode.

bae has no canary mechanism. There is no way to inject a temporary field for auditing purposes without modifying the Node class definition.

**Divergence: Missing feature.** Not critical for v1, but the framework could provide this as a testing utility.

### 1.7 Two-Phase vs. Single-Pass

The spec's Experiment 5 finding is unambiguous: single-pass schema generation beats two-phase (reason freely, then format). The two-phase approach loses information and inflates confidence.

bae's `AgenticBackend` (`bae/lm.py:326-391`) uses a two-phase approach: Phase 1 is agentic research (multi-turn tool use), Phase 2 is structured extraction from the research output. This is the exact pattern the spec warns against.

However, the `AgenticBackend` case is different from the spec's experiment. The spec tested *reasoning* tasks where the schema does cognitive work during generation. The `AgenticBackend` is for *research* tasks where the first phase gathers external data via tool use, and the second phase structures it. The research phase genuinely cannot be done in a single constrained-decoding pass because tool use requires free-form generation.

The `ClaudeCLIBackend.fill()` (`bae/lm.py:575-606`) is single-pass: prompt in, structured JSON out. This is the correct default path.

**Alignment: Mostly good.** The default path (ClaudeCLIBackend) is single-pass. The agentic path is two-phase by necessity, not by design mistake. But the spec's warning about confidence inflation in the extraction phase should be noted — the AgenticBackend's Phase 2 extraction could inflate confidence compared to what the research phase actually found.

### 1.8 System Prompt Design

In `bae/lm.py:458-461`, the system prompt for `ClaudeCLIBackend._run_cli_json()` is:

```
You are a structured data generator. Be brief and concise. Respond only with the requested data.
```

This is deliberately minimal — it prevents the Claude CLI from leaking cwd/env/project context. But "Be brief and concise" may conflict with the spec's principle that the `reasoning` field (or any free-text field) should be unconstrained in length. If a user defines a node with a `reasoning: str` field, the system prompt actively suppresses the elaboration that makes schema reasoning work.

**Divergence: Subtle but real.** The system prompt's brevity instruction fights against the spec's recommendation to leave reasoning fields unconstrained. This matters most for fields where elaboration is the mechanism of benefit.

---

## 2. Refactors Suggested by the Research

### 2.1 Field Naming Guidance

**Priority: High. Effort: Documentation only.**

bae should document the spec's findings on field naming:
- Presuppositional names (`missed`, `errors`, `gaps`, `issues`, `blockers`) force fabrication
- Procedural names (`completeness_check`, `verification_status`, `assessment`) permit legitimate "none" responses
- Domain-activating names (`assumptions`, `reasoning`, `sensitivity`) steer the LM's latent knowledge

This could be a short section in user-facing documentation, or a linting rule that warns about known-bad field names.

### 2.2 Fix Presuppositional Fields in Work Graphs

**Priority: Medium. Effort: Small refactor.**

Concrete changes:
- `VerifyGoal.gaps` -> `VerifyGoal.verification_summary: str` + `VerifyGoal.goal_met: bool` (already has `goal_met`)
- `VerifyOutput.gaps` -> `VerifyOutput.coverage_assessment: str`
- `SpotCheck.issues` -> `SpotCheck.assessment: str` (already has `assessment`) — remove the separate `issues` field
- `CheckPlan.issues` -> `CheckPlan.review_notes: str`
- `ResearchPhase.blockers` -> `ResearchPhase.risk_assessment: str`

In each case, the LM should produce a summary string that may or may not identify problems, rather than a list that presupposes problems exist.

### 2.3 System Prompt Tuning

**Priority: Medium. Effort: Trivial.**

Change the system prompt from "Be brief and concise" to something that does not suppress elaboration in reasoning fields. Options:

1. **Remove the brevity instruction entirely.** The JSON schema already constrains the structure; the system prompt does not need to.
2. **Replace with**: "You are a structured data generator. Fill each field thoroughly. Respond only with the requested data." — this preserves the anti-leak intent without suppressing reasoning.

### 2.4 Schema Complexity Dial

**Priority: Low (future). Effort: Medium design work.**

The spec's decision matrix could be implemented as a `schema_mode` on `NodeConfig`:

```python
class NodeConfig(TypedDict, total=False):
    lm: LM
    schema_mode: Literal["full", "minimal", "none"]
```

- `full`: current behavior — all plain fields in the JSON schema
- `minimal`: only required fields, optional fields become free-form in the response
- `none`: no JSON schema constraint, LM generates free-form text and we parse it

This is YAGNI today but becomes important if bae is used with weaker models or on tasks where the overhead/benefit tradeoff matters.

### 2.5 Field Ordering Enforcement or Guidance

**Priority: Low. Effort: Small.**

Options:
- **Documentation**: Explain that field order matters for LM output quality. Recommend "context fields first, reasoning fields in the middle, evaluative fields last."
- **Linting**: A `validate()` method that checks whether evaluative fields (those with names like `confidence`, `assessment`, `status`) come after substantive fields.
- **Framework enforcement**: None recommended. Field ordering is task-dependent and should not be rigidly enforced.

### 2.6 Field Description as Semantic Hint

bae already supports `Field(description=...)` and preserves it through `_build_plain_model()` into the JSON schema. This is the right mechanism for the spec's recommendation that field names and descriptions do cognitive work.

The framework could encourage richer descriptions. For example, `Field(description="specific shoes or boots")` on `RecommendOOTD.footwear` is terse. A description like `Field(description="specific shoes or boots appropriate for the weather, occasion, and outfit")` would activate more relevant knowledge dimensions.

**No code change needed.** This is a documentation and example-quality issue.

---

## 3. Contemporaneous Research

### 3.1 CRANE: Reasoning with Constrained LLM Generation (Banerjee et al., 2025)

[CRANE (arXiv 2502.09061)](https://arxiv.org/abs/2502.09061) provides the formal theoretical foundation the spec relies on. Published February 2025, presented at ICML 2025. Key finding: under constrained grammars that exclude intermediate reasoning tokens, LLMs are limited to problems solvable in TC^0. CRANE's "alternating-constraint" approach — constrain structure but free reasoning within fields — matches bae's architecture exactly. CRANE shows up to 10 percentage points accuracy improvement over standard constrained decoding.

**Relevance to bae:** bae's design of constraining JSON structure while leaving field content free-form is theoretically optimal per CRANE. No changes needed.

### 3.2 Structured Templates and Scaling Laws by Difficulty (August 2025)

["Can Structured Templates Facilitate LLMs in Tackling Harder Tasks?"](https://arxiv.org/html/2508.19069v1) introduces the Structured Solution Template (SST) framework, examining whether structured templates help or hurt across difficulty levels. Key finding: templates help on harder tasks and hurt on easier ones, confirming the spec's decision matrix. The paper additionally finds that curriculum-based fine-tuning with templates improves generalization.

**Relevance to bae:** Validates the spec's claim that schema should scale with task difficulty. Supports the future `schema_mode` dial in Section 2.4.

### 3.3 Fuzzy, Symbolic, and Contextual Cognitive Scaffolding (August 2025)

["Enhancing LLM Instruction via Cognitive Scaffolding"](https://arxiv.org/html/2508.21204v1) proposes a three-layer scaffolded prompting structure with a "structured short-term memory schema" that tracks session variables across turns. The architecture resembles bae's Recall mechanism — state from previous turns (trace nodes) is available to later nodes.

**Relevance to bae:** bae's Recall() is an implementation of structured short-term memory. The paper validates that trace-based state recall is architecturally sound. bae may be ahead of this paper in implementation maturity.

### 3.4 STROT: Structured Prompting for Data Interpretation (May 2025)

[STROT framework (arXiv 2505.01636)](https://arxiv.org/abs/2505.01636) uses schema-aware prompt scaffolds for data analysis tasks, with iterative refinement based on execution feedback. The multi-turn "reasoning agent embedded within a controlled analysis loop" is architecturally similar to bae's `AgenticBackend`.

**Relevance to bae:** Confirms the agentic research-then-extract pattern is used in the literature. STROT's iterative refinement loop is analogous to the plan_phase revision loop in bae's work graphs.

### 3.5 Decoupling Task-Solving and Output Formatting (October 2025)

["Decoupling Task-Solving and Output Formatting in LLM Generation"](https://arxiv.org/html/2510.03595v1) directly addresses the Tam et al. finding. This paper proposes separating the reasoning phase from the formatting phase, which is precisely what the spec warns against (two-phase loses information). However, the paper's approach is different — it uses a lightweight formatting pass that preserves more of the reasoning, unlike the naive "reason then reformat" approach the spec tested.

**Relevance to bae:** Supports bae's default single-pass approach. The AgenticBackend's two-phase approach should be watched — if the extraction phase is lossy, consider whether CRANE-style interleaved constraints could replace it.

### 3.6 Cognitive Foundations for Reasoning in LLMs (November 2025)

["Cognitive Foundations for Reasoning and Their Manifestation in LLMs"](https://arxiv.org/abs/2511.16660) automatically converts problem-type subgraphs into actionable prompts that scaffold reasoning, claiming up to 66.7% improvement. The approach of deriving prompts from graph structure rather than hand-authoring them is relevant to bae's graph-based architecture.

**Relevance to bae:** bae's graph structure already encodes problem decomposition — each node is a reasoning step. The framework could potentially auto-generate richer prompts from the graph topology (e.g., "You have completed steps A and B. Now produce C, considering the following context from A and B..."). Currently bae only passes the class name as instruction and the previous node + resolved context as data.

### 3.7 Pydantic AI and the Structured Output Ecosystem

[Pydantic AI](https://github.com/pydantic/pydantic-ai) is the closest comparable framework. It uses Pydantic models for structured output, supports multiple LLM providers, and has a graph feature. Key differences from bae:

- Pydantic AI registers each output type as a separate tool for union types. bae uses a two-step choose-then-fill approach (`bae/lm.py:502-537`). Both avoid slow oneOf schemas.
- Pydantic AI has built-in retry with validation error feedback. bae currently does not retry on FillError.
- Pydantic AI does not have Dep/Recall/Effect markers — dependency injection is manual.
- Pydantic AI does not have the graph-level trace that enables Recall.

[Instructor](https://github.com/instructor-ai/instructor) is more narrowly focused on structured extraction. It uses Pydantic for validation and supports retry with error feedback. It does not have graph execution, state management, or dependency injection.

Neither framework addresses the spec's findings about field naming, ordering, or presuppositional framing. These are prompt-engineering concerns that live outside the framework abstraction in both Pydantic AI and Instructor.

---

## 4. Strategic Direction Changes

### 4.1 Graph Topology as Prompt Context

The biggest untapped opportunity: bae knows the full graph topology at build time. It knows what nodes came before, what nodes come next, and what the terminal node looks like. None of this information is currently passed to the LM.

The spec's finding on `completeness_check` is that *knowing a future field is coming* changes how the model generates current content. By analogy, knowing what the *next node in the graph* expects could change how the model fills the current node.

Concrete idea: when filling `AnticipateUsersDay`, include in the prompt that the next node is `RecommendOOTD` with fields `top`, `bottom`, `footwear`, `accessories`, `final_response`. This creates an anticipation effect — the model generates a vibe check that is *useful for outfit recommendation*, not just generically descriptive.

This would be the spec's autoregressive conditioning effect applied at the graph level, not just the field level. No other framework does this.

### 4.2 Adaptive Schema Based on Model Capability

bae currently defaults to `claude-opus-4-6` for `ClaudeCLIBackend` and `claude-sonnet-4-20250514` for `AgenticBackend`. The spec shows that schema benefit scales inversely with model capability.

A future direction: when running with Opus, use minimal schemas (fewer constrained fields, more free-form). When running with Haiku, use full schemas with richer descriptions. The model identifier is already available in the backend; the schema construction in `_build_plain_model()` could filter fields based on a "schema depth" parameter derived from model tier.

### 4.3 Integrated Evaluation via Canary Fields

Rather than an external testing utility, canary fields could be a first-class framework feature:

```python
class MyNode(Node):
    reasoning: str
    answer: str
    _canary: str = CanaryField("inferential_humidity")
```

The framework would automatically:
1. Include the canary in the schema for a configurable percentage of runs
2. Compare legitimate field quality between canary-present and canary-absent runs
3. Report degradation as a signal that the schema needs simplification

This turns the spec's audit protocol into an automated quality monitoring system.

### 4.4 Rich Instruction Generation

Currently, `_build_instruction()` returns only the class name (`bae/graph.py:55-57`). The docstring is deliberately inert. But the spec shows that instruction quality matters — the class name alone is minimal context.

A richer instruction could be auto-generated from:
- The class name (current behavior)
- The class docstring (opt-in, not default)
- The graph position (what came before, what comes after)
- The field descriptions (summarized into a task description)

This would not require changing the node API — it would be a framework-internal enhancement to `_build_fill_prompt()`.

---

## 5. What bae Already Does Right

### 5.1 Nodes as Context Frames

The fundamental design — "fields = prompt context, class name = instruction" — is precisely what the spec recommends and what the contemporaneous literature validates. Each node is a cognitive scaffold: its fields define what the LM should attend to, its class name defines the task, and its type annotations define the structure.

This is not an accident. The design principle stated in `examples/ootd.py:155-163` ("Nodes are context frames. Fields assemble the information the LLM needs to construct the next node. Class name is the instruction.") is a direct implementation of schema-as-cognitive-scaffold, arrived at independently of the spec's experiments.

### 5.2 Separation of Concerns via Dep/Recall/Plain

The three field types map cleanly to the spec's model:
- **Dep fields**: External data, resolved before the LM sees them. Not part of the cognitive scaffold — they are pre-computed context.
- **Recall fields**: Graph state, also resolved before the LM sees them. These implement the "structured short-term memory" that the cognitive scaffolding literature recommends.
- **Plain fields**: The actual cognitive scaffold. These are what the LM fills, and their names/descriptions/ordering are the semantic signals that steer generation.

By separating these, bae ensures the LM only generates the fields where semantic steering matters. Dep and Recall fields are shown as context (in the prompt), not as generation targets (in the output schema). This avoids the "token budget consumed on infrastructure" problem.

### 5.3 Constrained Structure, Free Content

As analyzed in Section 1.1, bae's JSON schema constrains field boundaries and types but leaves field content free-form. This is the CRANE-optimal approach. bae arrived at this architecture before CRANE was published, which suggests the design was driven by practical observation of what works.

### 5.4 Single-Pass Default

The default `ClaudeCLIBackend.fill()` is single-pass. The spec's Experiment 5 validates this as superior. bae does not default to the two-phase pattern that degrades quality.

### 5.5 Type-Driven Graph Discovery

bae's graph topology is derived from return type hints. This is a form of type-level documentation that serves both the developer (understanding the graph structure) and potentially the LM (knowing what comes next). The `to_mermaid()` method visualizes this. No other framework in the structured output space derives graph topology from type hints this cleanly.

### 5.6 Class Names as Domain-Level Instructions

The convention of using descriptive class names (`IsTheUserGettingDressed`, `AnticipateUsersDay`, `ChallengeProject`, `ExamineProblem`) as the LM instruction is well-aligned with the spec's finding that field/instruction naming activates relevant latent knowledge. These names are domain-specific and action-oriented, which is better than generic names like `Step1` or `ProcessInput`.

### 5.7 Field(description=...) as Opt-In Semantic Enrichment

The phase 10 design decision to make docstrings inert and use `Field(description=...)` for per-field LLM hints is correct for two reasons:
1. It prevents the LM from compulsively generating/augmenting docstrings
2. It makes semantic enrichment explicit and per-field, matching the spec's recommendation that field names and descriptions are the primary cognitive intervention

The preservation of `FieldInfo` through `_build_plain_model()` into the JSON schema means descriptions reach the LM via constrained decoding metadata — they appear in the schema the LM is asked to fill.

---

## Summary Table

| Aspect | Status | Priority |
|--------|--------|----------|
| Mechanism B (schema-as-prompt) | Aligned | -- |
| Field content unconstrained | Aligned | -- |
| Single-pass default | Aligned | -- |
| Class name as instruction | Aligned | -- |
| Field(description=...) flow-through | Aligned | -- |
| Dep/Recall/Plain separation | Aligned | -- |
| Presuppositional field names | **Divergent** | Medium |
| System prompt brevity instruction | **Divergent** | Medium |
| Field ordering guidance | Missing | Low |
| Decision matrix (schema complexity) | Missing | Low (future) |
| Canary protocol | Missing | Low (future) |
| Graph topology as prompt context | **Untapped opportunity** | High (strategic) |
| Rich instruction generation | **Untapped opportunity** | Medium (strategic) |

---

## Sources

- [CRANE: Reasoning with Constrained LLM Generation](https://arxiv.org/abs/2502.09061) — ICML 2025
- [Can Structured Templates Facilitate LLMs in Tackling Harder Tasks?](https://arxiv.org/html/2508.19069v1) — August 2025
- [Fuzzy, Symbolic, and Contextual: Enhancing LLM Instruction via Cognitive Scaffolding](https://arxiv.org/html/2508.21204v1) — August 2025
- [STROT: Structured Prompting and Feedback-Guided Reasoning](https://arxiv.org/abs/2505.01636) — May 2025
- [Decoupling Task-Solving and Output Formatting in LLM Generation](https://arxiv.org/html/2510.03595v1) — October 2025
- [Cognitive Foundations for Reasoning and Their Manifestation in LLMs](https://arxiv.org/abs/2511.16660) — November 2025
- [Pydantic AI Framework](https://github.com/pydantic/pydantic-ai)
- [Instructor Library](https://github.com/instructor-ai/instructor)
- [Let Me Speak Freely? Impact of Structured Output on LLM Reasoning](https://arxiv.org/abs/2408.02442) — Tam et al.
- [Large Language Models as Cognitive Shortcuts: A Systems-Theoretic Reframing](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2026.1681525/full) — Frontiers in AI, 2026
