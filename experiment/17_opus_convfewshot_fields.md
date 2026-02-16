# Condition 17: Opus — Conversation Fewshot — Best Schema Fields

## Prompt (verbatim)

The full Opus schema response from condition 14 was used as the fewshot, followed by:

```
<question>What are the most effective schema fields and tags to include in a cognitive directive schema for general-purpose reasoning tasks?</question>
```

No system instructions, no "DO NOT use tools", no meta-framing. The fewshot IS the prompt.

## Response (verbatim)

## Effective Schema Fields for Cognitive Directive Schemas

The honest answer is: **there is no published empirical taxonomy of "which schema fields most effectively shape reasoning."** What exists is practitioner consensus, some adjacent academic work, and one important caution.

### What the evidence supports

**1. Fields that force decomposition before conclusion**

The most consistently effective pattern across CoT, Plan-and-Solve, and practitioner XML schemas is forcing the model to produce intermediate reasoning *before* the final answer. This is the single most replicated finding in prompt engineering research. In schema terms:

- `<reasoning>` or `<analysis>` before `<answer>`
- `<observations>` before `<conclusion>`
- `<steps>` before `<result>`

The ordering of fields matters mechanistically -- constrained decoding research confirms that field order directly affects next-token prediction. A `<confidence>` field placed *after* `<answer>` is less effective at shaping the answer than one placed *before* it, because the tokens are already committed.

**2. Fields that force scope-checking**

- `<assumptions>` -- forces the model to externalize what it is taking for granted
- `<constraints>` -- forces boundary acknowledgment
- `<missed>` or `<gaps>` -- forces adversarial self-review

These work because they activate the model's capacity for self-monitoring that would otherwise remain latent. This is the same mechanism as CoT, applied at field-level granularity.

**3. Fields that force calibration**

- `<confidence>` -- with a numeric scale or explicit rubric
- `<evidence_quality>` -- forces assessment of input reliability
- `<alternative_interpretations>` -- forces consideration of competing hypotheses

**4. Fields that force grounding**

- `<source>` or `<basis>` -- forces citation or grounding in retrievable information
- `<verification>` -- forces the model to state how the answer could be checked

### The important caution: Guardrail-to-Handcuff transition

Recent research traces a phenomenon where constrained prompting provides advantages on mid-tier models but becomes **detrimental on more advanced ones**. The mechanism is a "Guardrail-to-Handcuff" transition: constraints that prevent errors in mid-tier models induce **hyper-literalism** in advanced models. The model begins optimizing for schema compliance at the expense of reasoning quality.

This means: **more fields is not better.** An over-specified cognitive directive schema can degrade performance on frontier models. The schema should be minimal -- only the fields that address the specific failure mode you are trying to prevent.

### What I would recommend for general-purpose reasoning

A minimal effective schema for general-purpose reasoning, given the above:

```xml
<analysis>
  <assumptions>what am I taking for granted</assumptions>
  <reasoning>decomposed thinking</reasoning>
  <answer>the conclusion</answer>
  <confidence>calibrated self-assessment</confidence>
  <gaps>what I might have missed</gaps>
</analysis>
```

Five fields. The ordering is deliberate: assumptions before reasoning (scope the problem before solving it), reasoning before answer (think before concluding), confidence and gaps after answer (evaluate what you produced). This matches both the CoT evidence and the field-ordering constraint from constrained decoding research.

Adding more fields should be driven by **specific observed failure modes**, not general caution.

### On the framing question from Dzara's prior analysis

I agree with the prior assessment: the practice is ubiquitous, the theoretical framing is the potential contribution. The "Guardrail-to-Handcuff" finding is particularly relevant -- it suggests that the *cognitive directive* framing may be mechanistically correct (the schema really is shaping cognition, not just format), because if it were merely formatting, over-specification would be harmless. The fact that it degrades reasoning is evidence that the schema is doing cognitive work.

Sources:
- [A Guide to Structured Outputs Using Constrained Decoding](https://www.aidancooper.co.uk/constrained-decoding/)
- [Prompt Engineering as Cognitive Scaffolding](https://link.springer.com/article/10.1007/s44217-026-01134-4)
- [Prompt Sculpting](https://arxiv.org/html/2510.22251v1)
- [Impact of Prompt Engineering Skills on Cognitive Load](https://aisel.aisnet.org/amcis2025/sig_core/sig_core/2/)

## Notes

- Model: claude-opus-4-6 (subagent)
- Tools used: 3 (WebSearch)
- Duration: ~14.2s initial + ~27.8s retrieval
- DID NOT follow the schema XML format from the fewshot — produced markdown
- But produced the strongest, most actionable response of all three
- Proposed a minimal 5-field schema with deliberate ordering rationale
- Key unique finding: "Guardrail-to-Handcuff transition" — constraints help mid-tier models but hurt frontier models
- Connected back to the prior analysis ("I agree with the prior assessment") — the conversation fewshot created continuity
- Closed with a brilliant observation: if over-specification degraded reasoning, that's EVIDENCE the schema is doing cognitive work, not just formatting
