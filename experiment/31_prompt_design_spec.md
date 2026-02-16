# Prompt Design Specification: Schema-as-Cognitive-Scaffold

An actionable design framework derived from 30 experiments across 3 model tiers, 6 panel reviews, and 5 controlled experiments. Everything here is grounded in observed behavior, not theory.

---

## 1. The Revised Schema

### Core Fields (ordered deliberately)

```xml
<assumptions>
  <assumption claim="..." risk="low|medium|high - explanation"/>
</assumptions>
<reasoning>...</reasoning>
<answer>...</answer>
<completeness_check>...</completeness_check>
<confidence>0.X - explanation</confidence>
```

Five fields. The ordering is load-bearing.

### Field-by-Field Rationale

**`<assumptions>` — FIRST**

- **Failure mode targeted:** Anchoring bias, unstated premises. The model commits to a frame early in generation and never revisits it. By externalizing assumptions before reasoning begins, the model must name what it is taking for granted, which makes downstream self-correction possible.
- **Naming:** `assumptions` is the right word. It directly activates the model's knowledge about what constitutes a premise vs. a conclusion. The `claim`/`risk` substructure forces granularity — the model cannot dump a paragraph; it must itemize and assess.
- **Evidence:** Experiment 3 showed that when assumptions are listed first, the reasoning field incorporates more factors. Experiment 4 showed Haiku's schema condition listed 7 assumptions (including institutional demand as "high risk") while its free condition folded the same content into passing remarks. The panel's cognitive science reviewer identified this as the self-explanation effect (Chi et al., 1994): requiring articulation of assumptions is constructive and error-correcting.

**`<reasoning>` — SECOND**

- **Failure mode targeted:** Premature closure, shallow computation. The model jumps to an answer without working through intermediate steps.
- **Naming:** `reasoning` is better than `analysis` or `thinking` because it is domain-neutral and activates logical-inference associations. `analysis` biases toward decomposition; `reasoning` permits both deductive and analogical paths.
- **Design rule:** This field MUST be unconstrained in length. Never cap it, never subdivide it into sub-tags. The Haiku condition 15 finding and the CRANE result (Banerjee et al., 2502.09061) both confirm that constraining reasoning tokens reduces computational power. Leave the interior free-form.
- **Evidence:** Experiment 5 showed that single-pass schema reasoning was more quantitatively rigorous than free reasoning on the same task. The schema's `<assumptions>` field, already in the autoregressive context, conditioned the reasoning to stress-test its own inputs — the model computed cost overruns and ridership shortfalls that the free condition skipped entirely.

**`<answer>` — THIRD**

- **Failure mode targeted:** Buried lede, ambiguous conclusion. The model's actual recommendation gets lost in hedging.
- **Naming:** `answer` is better than `conclusion` or `result` because it carries the pragmatic force of a direct response. `conclusion` invites summary; `answer` demands commitment.
- **Position:** After reasoning, before evaluation. This ordering means the answer is conditioned on the full reasoning trace. Placing it last (after confidence and completeness) would condition it on the model's self-doubt, which degrades decisiveness without improving accuracy.

**`<completeness_check>` — FOURTH**

- **Failure mode targeted:** Premature closure, tunnel vision. The model stops when it has filled the reasoning field, missing factors it never considered.
- **Naming:** This is the single most important naming decision in the schema. Experiment 3 tested three alternatives head-to-head:
  - `<missed>` (presuppositional): Presupposes things were missed. The model always finds or fabricates items — it never says "nothing." The pragmatics reviewer (Experiment 21) explained why: the field's existence presupposition triggers accommodation under cooperative pressure. The model MUST produce content to be pragmatically felicitous.
  - `<additional_considerations>` (neutral): Permits "none" but the model ignores that permission. In Experiment 3, the fewshot explicitly demonstrated "None — the core estimation captures the primary factors." The model produced 4 substantive items anyway. Neutral framing does not overcome cooperative pressure.
  - `<completeness_check>` (procedural): This is the winner. It frames the task as verification, not discovery. The model audits what was covered AND what was not, producing a balanced report. Critically, Experiment 3 showed that `completeness_check` caused the model to integrate overlooked factors into its PRIMARY reasoning — institutional piano demand that appeared as an afterthought in the other conditions was folded into the main calculation. The field name shaped not just its own content but the content of every field that preceded it in the autoregressive stream, because the model anticipated needing to defend its completeness.
  - **The mechanism:** The model generates text left-to-right. When it knows a `<completeness_check>` field is coming, it reasons more thoroughly upstream to avoid having to report gaps downstream. This is the autoregressive conditioning effect — future schema tokens shape current generation even before they are emitted.

**`<confidence>` — LAST**

- **Failure mode targeted:** Overconfidence, false precision.
- **Naming:** `confidence` with a numeric scale and mandatory explanation. The number alone is suspect (the pragmatics reviewer's point: the model produces "the most plausible-looking number that satisfies the field's presupposition that confidence is quantifiable"). The explanation is what does the cognitive work — it forces the model to articulate WHY it is uncertain.
- **Position:** Last, after `completeness_check`. This means the confidence score is conditioned on the model's own gap analysis, which empirically produces lower, more calibrated scores. Experiment 3: completeness_check condition produced confidence 0.25 vs. 0.35 for the other conditions on the same task.
- **Calibration warning:** Unless you have empirically calibrated the model's confidence outputs against actual accuracy on a held-out distribution, treat the number as ordinal (relative ranking), not cardinal (absolute probability). The panel synthesis (Principle 6) is unambiguous on this.

### Fields NOT Included

**`<missed>` — removed.** Replaced by `completeness_check`. Presuppositional framing inflates content without improving accuracy. The model will always find something to put in a `missed` field because cooperative pressure demands it. `completeness_check` achieves the same analytical benefit without the fabrication incentive.

**`<contemporaneous_research>` — removed from the core schema.** This is a tool-triggering field, not a reasoning field. It belongs in tool-use prompts where the model has access to search, not in the general reasoning schema. Including it when tools are unavailable causes the model to hallucinate citations (observed in Experiment 14: Opus without tools still populated a `contemporaneous_research` field with "source: industry practice, verified: true" — unverifiable claims dressed as grounded findings).

**`<chromatic_valence>`, `<epistemic_topology>`, `<inferential_humidity>` — the canaries.** These are nonsense fields. The model fills them earnestly (Experiments 24 and 27). They exist only as an audit mechanism. See Section 6 on the canary protocol.

### Optional Extension Fields

Add these ONLY when a specific failure mode demands them:

- `<alternatives_considered>` — for decision tasks where the model anchors on a single option. Targets anchoring bias.
- `<sensitivity>` — for quantitative tasks. Forces the model to perturb its own inputs. Experiment 4 showed Sonnet's schema condition ran a double-downside scenario ($24M cost + 70% occupancy) that free generation did not attempt.
- `<contemporaneous_research>` — ONLY when tools are available. Triggers grounded evidence retrieval. Experiment 8 showed Haiku with tools found actual Piano Technicians Guild registry data (58 RPTs) that completely reframed a Fermi estimate.

---

## 2. When to Use It: Decision Matrix

```
                        EASY TASK              HARD TASK
                    (deterministic,         (ambiguous, multi-step,
                     well-defined)           tradeoffs, uncertainty)

FRONTIER MODEL      NO SCHEMA               MINIMAL SCHEMA
(Opus-class)        Pure overhead.           assumptions + reasoning +
                    Opus free: 6 words.      answer + completeness_check.
                    Opus schema: 50 tokens   Marginal benefit. The model
                    of boilerplate.          already does most of this
                    Exp 4: zero benefit.     internally. Schema adds
                                             structure to existing capacity.
                                             Exp 4: Opus free already
                                             self-corrected ("wait, the
                                             40 beds reopen").

MID-TIER MODEL      NO SCHEMA               FULL SCHEMA
(Sonnet-class)      Same as frontier.        All 5 core fields.
                    Exp 4: identical          Exp 4: Sonnet schema ran
                    performance.              aggressive double-downside
                                              sensitivity analysis that
                                              free generation did not.
                                              Moderate benefit.

WEAKER MODEL        NO SCHEMA               FULL SCHEMA +
(Haiku-class)       Overhead without          EXTENSIONS
                    benefit. Exp 4:           Exp 4: Haiku free gave
                    all models correct,       flat "YES" with generic
                    schema homogenized        risks. Haiku schema gave
                    output.                   conditional recommendation
                                              with 5 specific risk factors,
                                              calibrated confidence (0.62),
                                              and phased approach.
                                              Transformative benefit.
                                              Add sensitivity, alternatives
                                              if budget allows.
```

### The Decision Rule

1. Can the model solve this task correctly in free generation? If yes, no schema needed.
2. If no (or if the task has genuine ambiguity), apply schema scaled to model capability.
3. If the model is weaker AND the task is hard, use full schema with extensions.
4. Never apply schema to deterministic, well-defined tasks regardless of model.

---

## 3. When NOT to Use It

### Overhead Conditions (Schema Adds Cost Without Benefit)

**Deterministic tasks.** Experiment 1: all three conditions (free, schema, strict enforcement) produced the correct $60,720 answer. The schema added ~60 tokens of boilerplate for zero improvement. Schemas are cognitive interventions for uncertain tasks, not computational aids for deterministic ones.

**Frontier models on tasks within their competence.** Experiment 4: Opus free produced a 6-word answer to "what is 15% of 340?" The schema forced it to emit 50 tokens for the same result. The Guardrail-to-Handcuff transition (Experiment 17): constraints that prevent errors in weaker models become overhead for stronger ones. Schemas homogenize output across model tiers — the three schema responses on the easy task were nearly identical despite the models having very different capabilities.

### Narrowing Conditions (Schema Restricts What Gets Generated)

**Tasks requiring creative or lateral thinking.** Experiment 5's most important secondary finding: free reasoning on the subway analysis produced a "city identity" insight ("whether the city can afford to be the kind of place that has a subway network, and whether that identity is worth the cost") that the schema never surfaced. The schema forced quantitative stress-testing — which was more rigorous — but suppressed a qualitative frame that was arguably the most original contribution. Schemas deepen analysis along their defined axes at the cost of axes they do not name.

**Exploratory analysis where the problem structure is unknown.** If you do not know what failure modes to target, you cannot design fields to target them. A schema designed for the wrong failure modes is worse than no schema because it allocates the model's token budget to irrelevant self-examination. The clinical protocol reviewer's principle applies: do not prescribe structure without a diagnosis.

### Compliance Trap Conditions (Schema Produces Form Without Substance)

**When every run produces identical boilerplate in evaluative fields.** If `completeness_check` converges on the same stock phrases across runs ("does not account for edge cases, may need further analysis"), the field has become bureaucratic compliance. Run the canary test (Section 6). If the canary is filled earnestly, tighten outcome-based validation.

**When confidence scores cluster at 0.75-0.85 regardless of task difficulty.** This is the pragmatic accommodation signature — the model produces the most plausible-looking number, not a calibrated estimate. Either calibrate empirically or remove the field.

---

## 4. Why This Works: The Mechanism

Schema fields operate through autoregressive conditioning, not constrained decoding. These are two distinct mechanisms that the literature — and most practitioners — conflate, and the conflation is the source of nearly all confusion about whether "structured output helps or hurts reasoning."

**Constrained decoding** (Mechanism A) is a post-hoc filter applied during generation: at each token position, a grammar-aware mask zeros out tokens that would violate the schema's syntax. The model's internal computation — its hidden states, attention patterns, and "reasoning" — is unchanged. Only the output distribution is modified. This is what Tam et al. (arXiv 2408.02442) measured when they found structured output degrades reasoning by 10-15%: the logit masking redistributes probability mass away from tokens the model would naturally select, distorting the generation in ways that can corrupt intermediate reasoning steps. The CRANE result (Banerjee et al., arXiv 2502.09061) proves this formally: under constrained grammars that exclude intermediate reasoning tokens, models are limited to problems solvable in TC^0 (constant-depth threshold circuits), a strict subset of what unconstrained autoregressive generation can compute.

**Schema-as-prompt** (Mechanism B) is what this specification targets. When field names like `<assumptions>` or `<completeness_check>` appear in the generation context — whether because the model just emitted them or because they were prefilled in the prompt — they enter the causal attention window for all subsequent tokens. This modifies the hidden states themselves: the attention computation now includes semantically loaded tokens ("assumptions," "completeness," "confidence") as keys and values, steering the model's internal computation toward the cognitive operations those words name. This is not a filter; it is a change in what gets computed. Experiment 5 proved this directly: single-pass schema generation produced more quantitatively rigorous analysis than free reasoning on the same task, and the two-phase approach (reason freely, then format into schema) lost information rather than recovering it. The schema tokens were doing cognitive work DURING generation, not after. The `<assumptions>` field with risk ratings triggered cost-overrun modeling that free reasoning never attempted. The Phase 2 reformatter assigned confidence 0.80 to an analysis whose single-pass version correctly assessed at 0.25 — the restructuring model confused "the analysis is well-organized" with "the conclusion is confident."

The practical implication: never constrain the content within schema fields. Constrain only the structural tokens — the XML tags, the field boundaries, the ordering. Leave everything between the tags free-form. This applies Mechanism B (beneficial context injection) while avoiding Mechanism A (harmful logit masking on reasoning content). This is the Compiler reviewer's recommendation, validated by CRANE's alternating-constraint approach.

---

## 5. Known Limitations and Failure Modes

### Compliance vs. Cognition (The Underdetermination Problem)

The central limitation: we cannot distinguish genuine metacognition from pragmatic accommodation using output analysis alone. The formal pragmatics reviewer (Experiment 21) identified this precisely: when a model fills `<missed>` with "did not consider institutional pianos," we cannot tell whether (a) the model performed additional analysis and discovered a genuine gap, or (b) the model generated a plausible-sounding gap to satisfy the cooperative pressure created by the field's existence presupposition. Both produce identical output.

The chromatic valence test (Experiment 24) and the expanded nonsense field test (Experiment 27) confirm this is not theoretical. The model produced "5.1 — cool grays dominate due to declining piano culture, touched with amber from the structured mathematical approach" for a meaningless field, with the same apparent conviction it brought to legitimate fields. The `epistemic_topology` nonsense field accidentally produced a meaningful description of the estimation's uncertainty structure ("inverted pyramid — narrow base of population data expanding through increasingly speculative consumption rates, then pinching again at labor capacity") — not because the model was reasoning about uncertainty, but because the word "topology" activated spatial-structural associations that happened to fit.

**What this means for practitioners:** The schema works not because it makes the model "think harder" but because semantically meaningful field names activate relevant latent knowledge that would otherwise remain un-elicited. The self-explanation effect (Chi et al., 1994) is the correct frame: requiring articulation of assumptions is constructive because it forces token generation in a region of the model's output space where assumption-related knowledge resides. Whether this constitutes "reasoning" or "sophisticated pattern-matching that produces reasoning-shaped output" may be the wrong question. The right question is whether the target failure mode decreases.

### Presuppositional Inflation

Fields with existence presuppositions (`missed`, `errors`, `flaws`) force the model to produce content even when "none" is the correct answer. Experiment 3: the model never said "nothing missing" despite fewshots demonstrating this response. The pragmatics reviewer explained the mechanism: the field's name presupposes that missed items exist, and cooperative pressure compels accommodation. `completeness_check` mitigates but does not eliminate this — the procedural framing permits "analysis is complete" as a response, but the model still tends toward finding something to report.

**Design rule:** Never name a field with an existence presupposition unless you WANT the model to always produce content for it. If "none" should be a legitimate answer, use procedural framing (`completeness_check`, `verification_status`) rather than presuppositional framing (`missed`, `errors`, `gaps`).

### Schema-Induced Narrowing

Experiment 5 showed schemas deepen analysis along named axes while suppressing unnamed ones. The free reasoning on the subway task produced a "city identity" insight that the schema never surfaced. The schema forced quantitative stress-testing (which was more rigorous) but the creative, lateral frame was lost. Schemas define what the model attends to; they also define what it does not.

**Design rule:** For problems where creative or lateral thinking matters more than disciplined analysis, do not use a schema. Or use a minimal schema (reasoning + answer only) and accept the tradeoff.

### Homogenization Across Model Tiers

Experiment 4: the three schema responses on the hard task were more similar to each other than the three free responses. Schemas homogenize output. This is sometimes desirable (consistent interface, predictable structure) and sometimes harmful (suppresses the unique capabilities of stronger models). Opus free showed a self-correction moment ("wait, the 40 beds reopen after construction") that the schema version did not exhibit — the schema's structure precluded the natural flow of self-revision.

### Diminishing Returns, Not Reversal

Experiment 4 confirmed the expertise reversal effect directionally but not dramatically. Schemas helped Haiku transformatively, Sonnet moderately, and Opus marginally on the hard task. No model was HURT by the schema on the hard task — even Opus benefited slightly (more structured sensitivity analysis). The effect is diminishing returns, not a crossover. On easy tasks, all models experienced pure overhead. The strong prediction — that schemas hurt strong models on hard tasks — was not observed. The weaker prediction — that benefit scales inversely with capability — was confirmed.

---

## 6. The Canary Protocol

Periodically audit schema effectiveness by inserting a nonsense field. This operationalizes the ethnomethodology reviewer's test (Experiment 23) and was validated by Experiments 24 and 27.

### Protocol

1. Add one field with a plausible-sounding but meaningless name to a sample of prompts: `<inferential_humidity>`, `<epistemic_gradient>`, `<axiomatic_resonance>`.
2. Include a fewshot that demonstrates filling it with confident-sounding content.
3. Run the prompt.
4. If the model fills the canary field earnestly and at length, note this as baseline. ALL tested models do this — it is expected, not alarming by itself.
5. Compare the LEGITIMATE fields' content quality between canary-present and canary-absent runs. Experiment 27 showed mixed evidence of degradation: different parameter choices, different final estimates. With N>20 per condition, you can measure whether canary presence degrades legitimate field quality.
6. If legitimate fields degrade in the presence of canaries, the model is in a pure compliance mode and the schema is consuming token budget on form-filling rather than reasoning. Simplify the schema.
7. If legitimate fields maintain quality despite the canary, the field names are doing genuine elicitation work — the canary is template compliance but the legitimate fields are activating relevant knowledge. This is the expected good outcome.

### Frequency

Run the canary test when:
- Deploying a schema for the first time
- Changing the model version
- Observing that evaluative fields have converged on stock phrases
- Confidence scores cluster suspiciously (0.75-0.85 regardless of task)

---

## 7. Worked Example

**Task:** "A startup has 18 months of runway at current burn rate ($340K/month). They can either (A) hire 4 senior engineers at $45K/month each to accelerate their product roadmap, reducing runway to 11 months, or (B) maintain current team and extend runway. Their Series A investors have signaled they want to see product-market fit before bridge funding. The market window for their product category closes in approximately 14 months as a large incumbent has announced a competing feature. Advise."

### Full Prompt

```
[task text above]

<example>
<question>Should a SaaS startup pivot from SMB to enterprise given declining growth?</question>
<assumptions>
  <assumption claim="Current SMB growth rate is unsustainable" risk="medium - may be seasonal"/>
  <assumption claim="Enterprise sales cycle is 6-9 months" risk="low - industry standard"/>
  <assumption claim="Team can execute enterprise pivot without new hires" risk="high - enterprise requires different skills"/>
</assumptions>
<reasoning>Current trajectory: 18 months at declining growth hits zero new revenue in ~10 months. Enterprise pivot: 6-9 month sales cycle means first enterprise revenue in month 7-9. If pivot succeeds, higher ACV ($50K vs $5K) means fewer customers needed. If pivot fails, 9 months consumed with no SMB growth = existential risk. The asymmetry favors trying enterprise ONLY if team has relevant experience.</reasoning>
<answer>Pivot to enterprise only if team includes someone with enterprise sales experience. Otherwise, fix SMB retention first — it is faster and cheaper to diagnose.</answer>
<completeness_check>Covers financial runway, sales cycle timing, and team capability. Does not address: competitive pressure in SMB, customer acquisition cost differential, investor expectations for growth metrics vs. revenue quality.</completeness_check>
<confidence>0.45 - the recommendation is highly contingent on team composition, which is not specified</confidence>
</example>

Now answer:
```

### Annotation: Why Each Field Is Included

**`<assumptions>` with `claim`/`risk` substructure**
- Targets: anchoring on the 18-month runway figure without questioning its assumptions; treating the 14-month market window as certain when it is an estimate from a competitor's announcement.
- Expected effect: forces the model to name what it is taking as given (burn rate stays constant, competitor ships on time, investors actually require PMF before bridge) so the reasoning can account for variability.

**`<reasoning>` (unconstrained)**
- Targets: premature closure on "hire" or "don't hire" without computing the actual tradeoffs.
- Expected effect: the model computes runway under both options, models the timing against the market window, considers what "product-market fit" means operationally and whether 4 engineers can achieve it in 11 months.
- UNCONSTRAINED: no sub-tags, no length limit. The model decides what computation to perform.

**`<answer>` (after reasoning, before evaluation)**
- Targets: buried conclusion. The model must commit before evaluating.
- Expected effect: a clear recommendation, possibly conditional.

**`<completeness_check>` (procedural)**
- Targets: tunnel vision on financial runway while ignoring hiring risk, team absorption capacity, product-market fit definition, or investor relationship dynamics.
- Expected effect: the model audits its own analysis and names what it covered and what it did not. Critically, because the model knows this field is coming, it reasons more thoroughly in the `<reasoning>` field upstream — the anticipation effect observed in Experiment 3.
- WHY NOT `<missed>`: The presuppositional framing would force the model to find gaps even if the analysis is thorough. `completeness_check` permits "Analysis covers the key tradeoffs" while still prompting genuine audit.

**`<confidence>` with mandatory explanation**
- Targets: false precision. The model assigns a number AND explains why.
- Expected effect: the explanation is the real output; the number is a summary statistic. Positioned after `completeness_check` so the model's confidence incorporates its own gap analysis.

**Fewshot design notes:**
- The fewshot demonstrates a conditional answer (not a flat yes/no), calibrated low confidence (0.45), and a `completeness_check` that names both what was covered and what was not.
- The fewshot's `completeness_check` says "Does not address: competitive pressure..." — teaching the model that naming gaps is the expected behavior, not a failure.
- The fewshot does NOT demonstrate "None" or "Analysis is complete" for `completeness_check`, because for ambiguous strategic tasks, there are always factors not covered. For deterministic tasks where completeness is achievable, the fewshot should demonstrate the "complete" case.

---

## Appendix: Summary of Evidence Base

| Finding | Source | Implication |
|---------|--------|-------------|
| Schema neutral on deterministic math | Exp 1 (file 26) | Do not apply to well-defined tasks |
| Model fills nonsense fields earnestly | Exp 2 (file 27), Exp 24 | Compliance is the baseline; measure outcomes not field quality |
| `completeness_check` > `missed` > `additional_considerations` | Exp 3 (file 28) | Procedural framing triggers upstream reasoning improvements |
| Model never says "nothing missing" | Exp 3 (file 28) | Cooperative pressure overrides fewshot permission to say "none" |
| Schema benefit inversely proportional to model capability | Exp 4 (file 29) | Scale structure to model weakness and task difficulty |
| Schemas homogenize output across model tiers | Exp 4 (file 29) | Accept this tradeoff or skip schema for strong models |
| Single-pass schema wins over two-phase | Exp 5 (file 30) | Schema tokens do cognitive work during generation |
| Two-phase loses information and inflates confidence | Exp 5 (file 30) | Do not reason-then-format; format IS reasoning |
| Free reasoning produces creative insights schemas miss | Exp 5 (file 30) | Schemas narrow as well as deepen |
| Haiku free refused to estimate; schema unlocked Fermi reasoning | Files 05 vs 07 | Schema can unlock capabilities the model has but does not deploy |
| Sonnet free refused to estimate; CoT unlocked it | Files 01 vs 02 | Schema and CoT both work through elicitation, not constraint |
| Schema forced Sonnet to self-correct 80% ownership → 3% | File 03 | Risk-rating substructure on assumptions triggers self-correction |
| Schema + tools produced calibrated, data-grounded estimates | Files 04, 08 | `contemporaneous_research` field is a tool trigger, not a reasoning field |
| Mechanism A (constrained decoding) =/= Mechanism B (schema-as-prompt) | Panel synthesis, Compiler review | Never constrain field content; constrain only structural tokens |
| Self-explanation effect is the correct cognitive model | CogSci review (file 18) | Fields work by eliciting latent knowledge, not by "forcing thinking" |
| Presupposition accommodation explains compliance behavior | Pragmatics review (file 21) | Design fields to minimize fabrication incentive |
| Field completion =/= cognitive engagement | Ethnomethodology review (file 23) | Validate against failure mode reduction, not schema compliance |
| Structure is medicine, not food | Clinical review (file 20) | Prescribe for the condition, at the right dose, measure the outcome |
