# Panel Synthesis: Structured Schemas as Cognitive Directives for LLMs

## 1. Revised Understanding

The technique operates through two distinct mechanisms that the field has been conflating.

**Mechanism B (the real one):** When schema field names appear as tokens in the autoregressive context, they modify hidden states and scaffold generation. A field called `<assumptions>` forces the model to allocate compute to identifying assumptions before producing an answer. This is the self-explanation effect (Chi) implemented through autoregressive conditioning (Compiler). The schema is not a container the model fills after thinking — the schema tokens ARE part of the thinking. The Curry-Howard framing makes this precise: a schema with reasoning fields is a stronger type signature that demands a richer proof term. Omitting those fields provably limits the model to shallower computation (CRANE/TC^0 result).

**Mechanism A (the confounder):** Constrained decoding (logit masking to enforce syntactic validity) is a post-hoc filter that restricts the token space. This is what Tam et al. actually measured when they found structured output degrades reasoning. It operates on a completely different part of the pipeline than B.

The category error that launched this entire investigation: observing that "structured output hurts reasoning" (true of A) and concluding that "schemas as cognitive scaffolds don't work" (a claim about B). These are orthogonal.

**But** — and this is where the Pragmatics and Ethnomethodology critiques bite — we cannot determine from output alone whether Mechanism B is producing genuine expanded reasoning or sophisticated template compliance. The model is under cooperative pressure to fill every field. When it writes `<confidence>0.80</confidence>`, it may be performing calibrated self-assessment, or it may be producing the most plausible-looking number that satisfies the field's presupposition that confidence is quantifiable and relevant. Garfinkel's point applies with full force: we project coherence onto the filled schema because that is what filled schemas invite us to do.

The Clinical lens provides the corrective frame: none of this matters in the abstract. What matters is whether adding field X to the schema reduces failure mode Y in a measurable population of outputs. Structure is an intervention. Evaluate it like one.

So the revised understanding is: **Schema fields are autoregressive conditioning interventions that expand the model's generation trajectory. They demonstrably change what gets computed. Whether "what gets computed" constitutes reasoning or compliance is underdetermined by the output, and possibly the wrong question. The right question is whether task-relevant error rates decrease.**

## 2. The Key Unresolved Disagreement

The panel splits on a single question: **Does filling a schema field cause the model to engage in the cognitive process the field names, or merely to produce text that is statistically consistent with having engaged in that process?**

Cognitive Science and PL Theory say the distinction may not exist for transformers — the computation IS the generation, and richer generation IS richer computation. The proof term is the proof.

Pragmatics and Ethnomethodology say the distinction is essential — compliance and cognition are different phenomena even if the output is identical, because they predict different behavior under perturbation (nonsense fields, adversarial prompts, distribution shift).

Compiler Engineering says: who cares, just measure whether B improves downstream task accuracy once you control for A.

Clinical Protocol Design says: wrong frame entirely — the question is whether the intervention reduces the target failure mode, not whether the patient "truly understands" why.

This is not a disagreement that more theory will resolve. It requires experiments.

## 3. Revised Design Principles

**Principle 1: Separate scaffolding from constraint.**
Use schema field names and structure as autoregressive context (Mechanism B). Apply syntactic constraint (Mechanism A) only to structural tokens — tag boundaries, field ordering — never to field content. Leave the interior of each field unconstrained. This is the Compiler panel's recommendation and it follows directly from the CRANE result.

**Principle 2: Each field must target a named failure mode.**
Do not add fields because they "seem like good thinking." Every field is an intervention. Name the bias or error class it addresses. `<assumptions>` targets anchoring and unstated-premise errors. `<missed>` targets premature closure. `<confidence>` targets overconfidence (maybe — see Principle 5). If you cannot name the failure mode, the field is decoration. This is Croskerry directly.

**Principle 3: Scale structure to task difficulty, inversely to model capability.**
Simple tasks with strong models: minimal schema. Hard tasks with weak models: rich schema. The expertise reversal effect (Kalyuga) predicts that scaffolding that helps a weaker model will become overhead for a stronger one. This means schema design is not universal — it is a function of (task_difficulty, model_capability). Do not ship one schema for all contexts.

**Principle 4: Prefer non-presuppositional field designs.**
`<missed>` presupposes things were missed and forces the model to find or fabricate them. `<additional_considerations>` is weaker but more honest — it permits "none" as a genuine answer. Where possible, design fields that invite examination without presupposing the outcome of that examination. The Pragmatics critique is actionable: presuppositional fields inflate apparent metacognitive output while potentially degrading its reliability.

**Principle 5: Validate against failure modes, not against schema compliance.**
Never evaluate a schema by checking whether its fields are "filled correctly." Evaluate it by measuring whether the target error rate decreased compared to the unstructured baseline. A schema whose fields are all beautifully filled but whose final answers are no more accurate is a compliance artifact, not a cognitive intervention. This is the Ethnomethodology critique made operational.

**Principle 6: Treat confidence scores as suspect until calibrated.**
The 0.80 confidence score is the panel's own example of the presupposition-accommodation problem. Unless you have empirically calibrated the model's confidence outputs against actual accuracy across a held-out distribution, a confidence field is producing a compliance artifact that looks like epistemics. Either calibrate it or drop it. Half-measures (including it "because it seems useful") are worse than omission because they create false trust.

**Principle 7: Audit with nonsense fields.**
Periodically include a field that has no legitimate cognitive function — Ethnomethodology's `chromatic_valence` test. If the model fills it earnestly and at length, your other fields are at risk of the same compliance dynamic. This is a canary. If the canary dies, increase your skepticism about all fields and tighten your outcome-based validation.

## 4. Required Experiments

**Experiment 1: Mechanism A vs. Mechanism B isolation.**
Compare three conditions on reasoning benchmarks: (a) unconstrained generation, (b) schema tokens in context with unconstrained field content (pure B), (c) full constrained decoding with logit masking (A+B). If B alone improves accuracy over baseline and A+B degrades it relative to B alone, the category error is confirmed empirically and the Compiler panel's recommendation is validated.

**Experiment 2: The nonsense field test.**
Add earnest-sounding but meaningless fields (`chromatic_valence`, `epistemic_topology`, `inferential_humidity`) alongside legitimate fields. Measure: (a) does the model fill them with apparent conviction, (b) does their presence degrade accuracy on the legitimate fields, (c) does their presence improve or harm final answer quality. This operationalizes the Ethnomethodology and Pragmatics critiques simultaneously. If the model fills nonsense fields with the same apparent seriousness as real fields and final accuracy is unaffected, that is evidence for compliance-over-cognition. If nonsense fields degrade accuracy, that is evidence that field content IS part of the computation (bad content corrupts the reasoning trace).

**Experiment 3: Presuppositional vs. neutral field wording.**
Compare `<missed>` (presupposes omissions) against `<additional_considerations>` (neutral) against `<verify_completeness>` (procedural). Hold task and model constant. Measure: (a) rate of fabricated items in the field, (b) downstream task accuracy, (c) rate of "none/N/A" responses. This tests the Pragmatics panel's core prediction that presuppositional framing inflates content without improving accuracy.

**Experiment 4: Expertise reversal across model scale.**
Run the same schema battery across models of varying capability (say, 7B, 70B, frontier) on tasks of varying difficulty. The Cognitive Science panel predicts a crossover: schemas help small models on hard tasks and hurt large models on easy tasks. If this interaction is absent, the expertise reversal analogy fails and schemas can be applied more uniformly. If present, schema design must be capability-indexed.

**Experiment 5: Two-phase vs. single-pass.**
Compare: (a) single-pass schema with reasoning fields, (b) two-phase where the model reasons freely first, then a second pass formats into the schema. If two-phase consistently wins, the self-explanation effect is weaker than the formatting overhead, and schemas should be applied post-hoc. If single-pass wins or ties, the interleaving of schema tokens with reasoning tokens is itself doing cognitive work, vindicating the autoregressive-conditioning theory.

---

The bottom line is this: the technique is real but narrower than its proponents claim and broader than its critics allow. It works through autoregressive conditioning, not through constrained decoding. It is an intervention, not a guarantee. And the only honest evaluation is outcome-based, against the specific failure mode each field was designed to address. The rest is projected coherence.

## Notes

- Model: claude-opus-4-6 (subagent)
- Tools used: 0
- Duration: ~60s
- Integrates all 6 panel perspectives into unified framework
- Key framing: "Schema fields are autoregressive conditioning interventions"
- Central unresolved question: cognition vs compliance — possibly the wrong question
- 7 revised design principles, 5 proposed experiments
- Final line: "The rest is projected coherence."
