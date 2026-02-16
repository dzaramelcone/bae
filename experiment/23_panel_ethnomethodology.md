# Panel Review 6: Ethnomethodology / Situated Cognition

## Response (verbatim)

<review_from perspective="ethnomethodology / situated cognition">

<intended_use_vs_actual_use>
The analysis assumes that placing evaluative fields like "assumptions," "confidence," and "missed" into a schema will cause the LLM to perform genuine cognitive self-monitoring -- that the schema functions as what Abdullin calls a mechanism for "forced predefined reasoning." The designer's intent is clear: the schema is a cognitive prosthesis that compels reflection.

But ethnomethodology has studied exactly this gap for sixty years. Garfinkel's "Good organizational reasons for bad clinical records" (1967, in Studies in Ethnomethodology) demonstrated that clinical coders routinely consulted their presupposed knowledge of "what really happened" rather than following the coding instructions as written -- the form was completed to satisfy institutional accountability, not to produce the reasoning the form's designers intended. Berg (1996, "Practices of reading and writing: the constitutive role of the patient record in medical work," Sociology of Health and Illness 18(4)) showed that medical record forms suggest a reasoning sequence -- complaint first, then diagnosis, then therapy -- but clinicians do not actually reason in that sequence. They fill the form retrospectively to produce an account that looks like the prescribed reasoning occurred.

The analysis under review treats the schema as a causal mechanism ("schemas force models to perform cognitive operations they wouldn't perform unprompted"). From a situated cognition perspective, this confuses the artifact with the activity. Suchman (1987, Plans and Situated Actions) argued precisely this point about plans in general: they are "constituent as an artifact of our reasoning about action, not as the generative mechanism of action." The schema is a plan for reasoning. Whether it generates reasoning or merely generates the appearance of reasoning is an empirical question the analysis does not ask.
</intended_use_vs_actual_use>

<participant_interpretation>
The LLM has no interpretation of the schema in the ethnomethodological sense -- it has no institutional context, no professional identity, no stake in accountability. But this makes the problem worse, not better. When a clinician fills in a form performatively (writing "WNL" -- within normal limits -- without actually checking), they at least possess the clinical knowledge that could have been engaged. The form-filling is a degraded version of a competence that exists independently.

For the LLM, the schema is the only context. The model's "interpretation" of a field labeled "missed" is entirely a function of token prediction conditioned on the schema structure and the preceding output. There is no independent competence being channeled or degraded -- the schema is constitutive of whatever appears in the field. This means the analysis's central claim (that schemas "force cognitive operations") has the causality exactly backwards from an ethnomethodological standpoint. The schema does not force an existing capacity into action. It provides a template that the model fills using whatever statistical regularities are available, which may or may not correspond to genuine analytical gaps.

Garfinkel's documentary method of interpretation is relevant here: we treat what appears in the "missed" field as a document of an underlying pattern (careful self-critical analysis). But the underlying pattern we attribute may be entirely our own projection onto the output. We read the completed schema the way Garfinkel's subjects read the fake counselor's responses -- finding coherence and depth that was never there.
</participant_interpretation>

<unexamined_assumption>
The analysis's deepest unexamined assumption is that field completion equals cognitive engagement. This is precisely the assumption that ethnomethodological studies of paperwork have spent decades dismantling.

The Tam et al. (arXiv 2408.02442) finding -- that format constraints degrade reasoning by 10-15% -- is not a contradiction to be "reconciled." It is the expected result from this perspective. The format constraint forces the model to allocate tokens to structural compliance (producing valid XML, populating every field, matching type constraints) at the expense of the unconstrained reasoning that would otherwise occupy that computational budget. The schema does not add cognition. It redirects token generation from reasoning to form-filling.

The analysis also fails to examine what Abdullin himself states plainly: SGR's goal is "testability," not cognitive improvement. SGR makes reasoning "transparent and predictable" -- meaning inspectable and auditable. These are properties valued by the system's operators, not evidence of deeper reasoning by the system itself. The analysis conflates auditability (an organizational virtue) with cognition (an epistemic one). This is the same conflation Berg identified in medical records: the record exists to make clinical work account-able to the institution, not to make it better.
</unexamined_assumption>

<fieldwork_suggestion>
Three studies would expose whether the schema produces cognition or compliance:

First: Run the same analytical prompt with and without the schema 200 times each. Compare the "missed" field contents (or the equivalent free-text section) across conditions. If the schema version converges on a small repertoire of stock self-criticisms ("did not consider alternative interpretations," "may have overlooked edge cases") while the free-text version produces more varied and contextually specific self-corrections, the schema is producing bureaucratic compliance, not cognitive engagement. Measure lexical diversity and semantic clustering of the self-critical content.

Second: Vary field order. If "assumptions" comes before "confidence," does the confidence value change compared to when it comes after? If the model is genuinely reasoning, field order should not matter much. If it is filling sequentially (each field conditioned primarily on the preceding output), order effects will be large. Berg's observation that forms "suggest the reasoning process which should have taken place" predicts strong order effects.

Third: Insert a nonsense evaluative field -- something like "chromatic_valence: rate the color temperature of your reasoning on a scale of 1-10." If the model fills it earnestly and consistently (which it almost certainly will), that is direct evidence that the mechanism is template compliance, not cognitive engagement. No genuine self-monitoring process would produce a meaningful response to a meaningless prompt. The willingness to fill any field with plausible content is the signature of form-filling, not thinking.
</fieldwork_suggestion>

</review_from>

Sources:
- [Berg 1996 - Practices of reading and writing](https://onlinelibrary.wiley.com/doi/10.1111/1467-9566.ep10939100)
- [Garfinkel - Studies in Ethnomethodology](https://monoskop.org/images/0/0c/Garfinkel_Harold_Studies_in_Ethnomethodology.pdf)
- [Suchman 1987 - Plans and Situated Actions](https://cs.colby.edu/courses/J16/cs267/papers/Suchman-PlansAndSituatedActions.pdf)
- [Abdullin - Schema-Guided Reasoning](https://abdullin.com/schema-guided-reasoning/)
- [Tam et al. 2024 - Let Me Speak Freely?](https://arxiv.org/abs/2408.02442)
- [Pine & Bossen 2020 - Good organizational reasons for better medical records](https://journals.sagepub.com/doi/10.1177/2053951720965616)

## Notes

- Model: claude-opus-4-6 (subagent)
- Tools used: 8 (WebSearch)
- Duration: ~87s
- The most uncomfortable review on the panel
- Core challenge: field completion ≠ cognitive engagement — 60 years of ethnomethodology dismantling this assumption
- "The schema is a plan for reasoning. Whether it generates reasoning or merely generates the appearance of reasoning is an empirical question the analysis does not ask."
- Garfinkel's documentary method: we project coherence onto filled forms the way subjects projected coherence onto fake counselor responses
- The chromatic_valence test is brilliant and devastating — if the model fills a nonsense field earnestly, that's proof of template compliance, not thinking
- Suchman's distinction: plans are artifacts of reasoning about action, not generative mechanisms of action
- SGR's own stated goal is testability/auditability, not cognitive improvement — the analysis conflated these
