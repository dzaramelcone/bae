# Panel Review 2: Programming Language Theory / Type Systems

## Response (verbatim)

<review_from perspective="programming language theory / type systems">

<formal_analog>

An output schema -- whether JSON Schema, XML Schema, or a Pydantic model -- is a structural type with refinement predicates on leaves. In the Curry-Howard reading, the schema is a proposition and the model's output is a proof term: the model must *inhabit* the type. A schema with fields like `{assumptions: list[str], confidence: float, missed: list[str]}` is a product type (conjunction): the model must produce evidence for every conjunct.

The critical distinction the artifact fails to make is between two formally different operations:

1. **Constrained decoding** (token-level masking via a grammar or schema automaton). This is analogous to restricting the term language to a sublanguage. Park et al. (NeurIPS 2024) proved this *distorts the probability distribution* over the model's output space -- the resulting distribution is not proportional to the unconstrained one. Formally: let p(x) be the model's distribution and L(S) the language of schema S. Constrained decoding produces p'(x) = p(x) * 1[x in L(S)] / Z, but because the masking operates token-by-token with greedy renormalization rather than globally, the actual distribution q(x) != p'(x). This is the distribution distortion problem. It is why Tam et al. (2408.02442) observe 10-15% reasoning degradation: the schema constraint is applied at the wrong level of abstraction (tokens, not propositions).

2. **Schema-as-prompt** (the schema is included in the prompt as a specification, and the model generates freely or with light post-hoc validation). Here the schema functions as a *specification* in the refinement-type sense: it tells the model what to prove, but does not restrict the proof search. This is closer to how SGR (Abdullin) operates in practice -- the schema is a contract that shapes the reasoning trajectory without distorting the token distribution.

The artifact conflates these two mechanisms. The Tam et al. result applies to mechanism (1). The SGR/Cognitive Prompting claim applies primarily to mechanism (2). There is no contradiction -- they operate at different levels of the type hierarchy.

</formal_analog>

<properties_guaranteed>

**Under constrained decoding (mechanism 1):**
- Well-formedness: output is in L(S), guaranteed by construction.
- Presence: all required fields are populated.
- Leaf-level type safety (string, number, boolean, enum).
- These are purely syntactic properties -- analogous to what a parser or syntax-directed type checker provides.

**Under schema-as-prompt (mechanism 2):**
- None of the above are *guaranteed* (the model may produce malformed output).
- What is provided is a *soft specification* that empirically biases the model toward producing structured reasoning traces. This is not a type-theoretic guarantee; it is a statistical tendency.

</properties_guaranteed>

<properties_not_guaranteed>

By either mechanism:

- **Semantic correctness.** The schema `{confidence: float}` constrains the output to contain a number. It cannot express the refinement predicate "this number is a calibrated probability." In refinement type notation, what we want is `{v: float | v = P(correct | evidence)}`, but what the schema provides is `{v: float | 0.0 <= v <= 1.0}` at best. The semantic gap is unbridgeable by structural typing alone.

- **Internal consistency between fields.** A product type A x B x C guarantees each component is inhabited but says nothing about relationships between components. The schema cannot express that `missed` must be the complement of what `assumptions` covers relative to the input. This would require dependent types: `{missed: list[str] | missed ∩ assumptions = emptyset /\ missed ∪ assumptions = relevant(input)}`.

- **Reasoning quality.** The CRANE paper (Beurer-Kellner et al., ICML 2025) proved that under constrained decoding with restrictive grammars, models are limited to problems solvable in logspace-uniform TC^0 -- constant-depth threshold circuits. Unconstrained autoregressive generation can simulate Turing machines via chain-of-thought. Constraining the output grammar to only permit final answers (no intermediate reasoning tokens) provably reduces computational power. CRANE's solution -- augmenting the grammar with reasoning rules -- is precisely the type-theoretic insight that you must include proof terms (intermediate steps) in the type, not just the final witness.

</properties_not_guaranteed>

<formalization_sketch>

Let S be a schema (structural type), p a prompt, and G a generation function.

**Claim under review:** E[quality(G(p, S))] > E[quality(G(p, emptyset))] -- that schema S improves output quality.

**Decomposition:**

Define two generation functions:
- G_cd(p, S): constrained decoding. Output guaranteed in L(S). Distribution distorted per Park et al.
- G_sp(p, S): schema-in-prompt. Output not guaranteed in L(S). Distribution undistorted.

The artifact's core claim -- that evaluative schema fields act as "cognitive directives" -- is the claim that for G_sp:

  E[quality(G_sp(p, S_evaluative))] > E[quality(G_sp(p, S_minimal))] > E[quality(G_sp(p, emptyset))]

where S_evaluative includes fields like `assumptions`, `confidence`, `missed`, and S_minimal includes only answer fields.

This is an empirical claim about the *pragmatics* of specification, not a type-theoretic one. From PLT, what we can say formally is:

1. S_evaluative has higher *information content* as a type: it demands more witnesses. A product type A x B x C requires strictly more evidence than A alone. If the model's generation process is *proof search* (even approximately), a richer specification forces exploration of more of the evidence space.

2. But richer types also increase the risk of *uninhabited types* -- specifications so demanding that the model produces degenerate witnesses (hallucinated confidence values, vacuous assumption lists). This is the type inhabitation problem: not all types have good inhabitants.

3. The Tam et al. result is explained by the CRANE analysis: when S is enforced via constrained decoding and S does not include space for intermediate reasoning, the computational class of solvable problems shrinks. The fix (CRANE, SGR pattern) is to include reasoning fields in the schema -- making the type include proof terms, not just the proposition's witness.

**The reconciliation the artifact missed:**

Tam et al.'s degradation occurs when: schema constrains output space AND schema excludes reasoning traces. SGR-style improvement occurs when: schema *includes* reasoning fields (effectively embedding chain-of-thought into the type). These are not contradictory findings. They are the same phenomenon viewed from opposite ends: constraining output without providing space for proof terms reduces capability; providing structured space for proof terms (even if constrained) can improve capability.

In type-theoretic terms: the schema `{answer: T}` is a *weak specification* that discards proof-relevant information. The schema `{reasoning: list[Step], assumptions: list[str], answer: T, confidence: float}` is a *strong specification* that preserves it. The difference is analogous to the difference between `exists x. P(x)` (just give me a witness) and the full dependent sum `Sigma(x: T). P(x)` (give me the witness *and* the proof).

**Confidence assessment of the original artifact:** The 0.80 confidence is reasonable for the novelty claim but the analysis has a significant gap. The failure to distinguish constrained decoding from schema-as-prompt, and the failure to reconcile Tam et al. via the CRANE/proof-term analysis, means the artifact is working with an underspecified model of the mechanism. The novelty assessment (not novel, composition of existing ideas) is likely correct, but the *explanation* of why it works is incomplete.

</formalization_sketch>

</review_from>

Sources:
- [Tam et al. - Let Me Speak Freely? (arXiv 2408.02442)](https://arxiv.org/abs/2408.02442)
- [CRANE: Reasoning with constrained LLM generation (arXiv 2502.09061, ICML 2025)](https://arxiv.org/abs/2502.09061)
- [Park et al. - Grammar-Aligned Decoding (NeurIPS 2024)](https://arxiv.org/abs/2405.21047)
- [Abdullin - Schema-Guided Reasoning](https://abdullin.com/schema-guided-reasoning/)
- [Grammar-Constrained Decoding (ACL 2025 Industry)](https://aclanthology.org/2025.acl-industry.34.pdf)
- [Curry-Howard Correspondence](https://en.wikipedia.org/wiki/Curry%E2%80%93Howard_correspondence)

## Notes

- Model: claude-opus-4-6 (subagent)
- Tools used: 7 (WebSearch)
- Duration: ~98s
- Formalized the constrained decoding vs schema-as-prompt distinction using Curry-Howard
- Schema = proposition, model output = proof term, evaluative fields = demanding more witnesses
- Found Park et al. (NeurIPS 2024) proving constrained decoding distorts probability distributions
- Found CRANE's TC^0 result: constrained grammars without reasoning tokens provably reduce computational power
- Key type-theoretic metaphor: `exists x. P(x)` (weak spec, just give me answer) vs `Sigma(x:T). P(x)` (strong spec, give me witness AND proof)
- Agrees 0.80 confidence is reasonable but analysis has "significant gap" in mechanism explanation
