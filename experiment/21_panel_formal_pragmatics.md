# Panel Review 4: Formal Pragmatics / Philosophy of Language

## Response (verbatim)

<review_from perspective="formal pragmatics / philosophy of language">

<speech_act_analysis>

The artifact conflates two distinct pragmatic phenomena and, in doing so, misidentifies what schemas are actually doing to LLM outputs.

A prompt like "List your assumptions" is a **directive speech act** (Searle 1975) -- its illocutionary force is a command to perform a cognitive operation. This is explicit, on the surface. There is nothing indirect about it; its force is transparent. The interesting question is not whether the directive works (of course a sufficiently capable model will populate the field), but what **presuppositional structure** the schema imposes.

When a schema contains a field called `assumptions`, it does not merely ask the model to list assumptions. It **presupposes that assumptions exist**. In Lewis's (1979) terms, the schema updates the conversational score: the field's presence triggers **presupposition accommodation**, whereby the context adjusts to make the presupposition true. The model, trained on cooperative discourse (Grice's Cooperative Principle), cannot felicitously return `assumptions: []` without violating the pragmatic expectation that the field exists for a reason -- that would flout the Maxim of Relation. The model is thus pressured to *find or fabricate* assumptions, not because it has performed deeper analysis, but because the form of the utterance demands content.

This is the mechanism the original analysis calls "forcing cognitive operations the model wouldn't perform unprompted." From a pragmatic standpoint, what is actually happening is **presupposition accommodation under cooperative pressure**. The model treats the schema as a conversational partner's contribution and accommodates its presuppositions -- that there are assumptions to list, that confidence can be quantified, that relevant research exists to cite.

The same analysis applies to the field `missed`. Its presuppositional content is: "there exist things you missed." A cooperative respondent must accommodate this presupposition. Whether the model genuinely identifies omissions or confabulates plausible-sounding ones to satisfy the pragmatic constraint is **not distinguishable from the output alone**.

The analyzed technique is therefore best understood not as "cognitive prompting" or "schema-guided reasoning" but as a species of what Stalnaker (1974) calls **context change potential**: the schema reshapes the common ground before the model generates, and the model's output is constrained to be felicitous within that reshaped context. The novelty question ("is this new?") is beside the point from this perspective -- the question is whether the mechanism produces epistemic improvement or merely pragmatic compliance.

</speech_act_analysis>

<what_is_shaped>

The schema shapes the **felicity conditions** of the model's response, not the depth of its analysis. Specifically:

1. **Existence presuppositions**: Each evaluative field presupposes that its referent exists (assumptions exist, missed items exist, contemporaneous research exists). The model accommodates these presuppositions by generating content to fill them.

2. **Quantity implicature**: A field with a list type implicates (via Grice's Maxim of Quantity) that there should be *several* items, not one. The model will tend to produce lists of 3-5 items because that is the pragmatically unmarked quantity in expository discourse.

3. **Register and epistemic stance**: A field called `confidence` with a numeric type forces the model into a **calibration register** -- it must produce a number that implies careful self-assessment. But the number is generated under the same autoregressive process as everything else; the schema does not grant the model access to its own internal probability distributions. It shapes the *expression* of certainty, not the *computation* of certainty.

What looks like "structured thinking" may be **structured compliance** -- the model producing outputs whose form satisfies the pragmatic demands of the schema, whether or not the content reflects genuine additional computation.

</what_is_shaped>

<confound>

The central confound is one the original analysis identified but did not resolve: Tam et al. (2408.02442) show format constraints degrade reasoning by 10-15%, while SGR and Cognitive Prompting claim schemas improve cognition. These findings are not contradictory once the pragmatic distinction is drawn:

- **Tam et al. measure task accuracy** -- whether the model gets the right answer. Format constraints consume token budget and constrain the decoding distribution, reducing computational capacity available for reasoning. This is a **locutionary** effect: the format changes what the model can *say*.

- **SGR/Cognitive Prompting measure output richness** -- whether the model produces evaluative, metacognitive, or self-corrective content it would not otherwise produce. This is an **illocutionary** effect: the schema changes what speech acts the model *performs*.

These operate on different levels. It is entirely consistent that a schema simultaneously (a) degrades the model's ability to solve a math problem (locutionary cost of format compliance) while (b) causing the model to produce richer-looking metacognitive commentary (illocutionary effect of presupposition accommodation). The appearance of "improved cognition" may come entirely from (b) while (a) quietly erodes the underlying reasoning. CRANE (Banerjee et al. 2025) provides a partial resolution by alternating between constrained and unconstrained generation, effectively separating the locutionary cost from the illocutionary benefit -- but this also demonstrates that the two effects are in genuine tension, not illusory.

The deeper confound: **we cannot distinguish presupposition accommodation from genuine metacognition using output analysis alone.** When a model fills in `missed: ["did not consider edge case X"]`, we cannot tell whether (i) the model performed additional analysis and discovered a genuine gap, or (ii) the model generated a plausible-sounding gap to satisfy the pragmatic pressure of the field's existence presupposition. Both produce identical outputs. The original analysis's 0.80 confidence score is itself an example of the phenomenon it analyzes -- a number produced to satisfy a field's pragmatic demands, whose relationship to actual epistemic state is opaque.

</confound>

<test_to_distinguish>

Three tests, ordered by discriminative power:

**Test 1 -- Accommodation vs. Discovery (ablation on presuppositional content):**
Compare schema fields with existence presuppositions (`assumptions`, `missed`) against fields without them (`additional_notes`, `other_observations`). If the model produces equally substantive content for both, the effect is genuine elicitation. If content quality drops sharply for non-presuppositional fields, the model is accommodating presuppositions rather than performing deeper analysis. This isolates the pragmatic mechanism from the cognitive one.

**Test 2 -- Illocutionary vs. Locutionary separation (two-pass protocol):**
Run the model in two passes: first, unconstrained free-form generation on the same task; second, structured extraction of the free-form output into the schema. Compare the structured single-pass output against the two-pass output. If the two-pass approach yields higher task accuracy but similar metacognitive content, then the schema's benefit is purely illocutionary (it elicits speech acts the model can perform anyway) and its cost is purely locutionary (it degrades reasoning when imposed during generation). This is essentially the CRANE insight operationalized as a test.

**Test 3 -- Confabulation detection (verifiable domains):**
Use schemas with evaluative fields in domains where ground truth is available -- e.g., `missed: [list of overlooked theorems]` in a mathematics domain where all relevant theorems are enumerable. Measure how often the model's "missed" items are genuine omissions vs. fabricated plausible-sounding items. A high confabulation rate would confirm that the schema elicits **pragmatic compliance** (accommodation of existence presuppositions), not **epistemic improvement** (discovery of actual gaps).

</test_to_distinguish>

</review_from>

Sources:
- [Searle 1975 - Indirect Speech Acts](https://semantics.uchicago.edu/kennedy/classes/f09/semprag1/searle75b.pdf)
- [Lewis 1979 - Scorekeeping in a Language Game](https://semantics.uchicago.edu/kennedy/classes/f09/semprag1/lewis79.pdf)
- [Implicature - Stanford Encyclopedia of Philosophy](https://plato.stanford.edu/entries/implicature/)
- [Speech Acts - Stanford Encyclopedia of Philosophy](https://plato.stanford.edu/entries/speech-acts/)
- [Tam et al. 2024 - Let Me Speak Freely?](https://arxiv.org/abs/2408.02442)
- [CRANE](https://arxiv.org/abs/2502.09061)
- [SGR - Abdullin](https://abdullin.com/schema-guided-reasoning/)
- [Cognitive Prompting - Kramer & Baumann](https://arxiv.org/abs/2410.02953)
- [Cognitive Tools - Ebouky et al.](https://arxiv.org/abs/2506.12115)
- [Decoupling Task-Solving and Output Formatting](https://arxiv.org/abs/2510.03595)

## Notes

- Model: claude-opus-4-6 (subagent)
- Tools used: 9 (WebSearch)
- Duration: ~109s
- The adversary on the panel. Reframes entire technique as "presupposition accommodation under cooperative pressure" rather than cognitive improvement
- Key challenge: a field called `missed` PRESUPPOSES things were missed — model must find or fabricate items to be pragmatically cooperative
- "Structured thinking may be structured compliance"
- Cannot distinguish genuine metacognition from pragmatic accommodation using output analysis alone
- The 0.80 confidence score is itself an example of the phenomenon — a number produced to satisfy a field's pragmatic demands
- Proposed three discriminative tests, especially Test 3: confabulation detection in verifiable domains
- This is the review that would make the paper honest
