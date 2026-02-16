# Panel Review 1: Cognitive Science of Reasoning

## Prompt (verbatim)

```
You are a reviewer from the domain of Cognitive Science of Reasoning. You study how external structure (scaffolding, checklists, schemas) shapes human cognition. You have access to WebSearch — use it to ground your review in actual research from your field.

Review the following analysis and respond using the schema below.

## Artifact Under Review

An analysis concluded that using structured XML output schemas with evaluative fields (assumptions, confidence, missed, contemporaneous_research) as "single-pass cognitive directives" for LLMs is not novel. The core mechanism is published as Schema-Guided Reasoning (SGR, Abdullin 2025), Cognitive Prompting (Kramer & Baumann, arXiv 2410.02953), and Cognitive Tools (Ebouky et al., arXiv 2506.12115). The analysis claims schemas force models to perform cognitive operations they wouldn't perform unprompted, but concludes this is a composition of existing published ideas. Confidence: 0.80.

Key tension identified: Tam et al. (arXiv 2408.02442) found format constraints degrade reasoning by 10-15%, while the technique claims schemas improve cognition. The analysis did not reconcile this contradiction.

## Schema

[fewshot example of numbered list artifact omitted for brevity — see full prompt in experiment dispatch]
```

## Response (verbatim)

<review_from perspective="cognitive science of reasoning">

<artifact>An analysis concluding that structured XML output schemas with evaluative fields function as "single-pass cognitive directives" for LLMs, and that this is a composition of existing published ideas (SGR, Cognitive Prompting, Cognitive Tools). Confidence 0.80. The analysis left unreconciled the tension between Tam et al.'s finding that format constraints degrade reasoning and the claim that schemas improve cognition.</artifact>

<mechanism_or_metaphor>The analysis is operating with a metaphor it mistakes for a mechanism. Calling schema fields "cognitive directives" borrows from scaffolding theory (Wood, Bruner & Ross, 1976) without importing the theory's actual causal structure. In the original scaffolding framework, the scaffold works through six strategies -- three cognitive (reduction in degrees of freedom, marking critical features, demonstration) and three motivational (recruitment, direction maintenance, frustration control). A schema with fields like "assumptions" and "missed" maps onto exactly two of these: reduction in degrees of freedom (constraining what the model must address) and marking critical features (directing attention to gaps). But the analysis never identifies which scaffolding operations the schema performs and which it does not, treating "schemas force cognitive operations" as a self-evident mechanism rather than a claim requiring decomposition.

More critically, the analysis conflates two distinct computational operations: (1) structured output formatting, where the model must emit tokens conforming to a grammar, and (2) structured elicitation, where field names function as prompts that trigger generation of content the model would not otherwise produce. The Tam et al. finding and the CRANE work (Banerjee et al., arXiv 2502.09061) demonstrate that operation (1) can degrade reasoning because constrained decoding restricts the token-level search space during intermediate reasoning steps. The Deco-G framework (Deng et al., arXiv 2510.03595) confirms this by showing that decoupling format compliance from task-solving yields 1-6% gains. The claimed benefit of schema-as-cognitive-directive is operation (2) -- the self-explanation effect (Chi et al., 1994), where requiring articulation of reasoning improves the reasoning itself. These are not in tension. They are orthogonal forces acting at different levels. The analysis's failure to reconcile the "contradiction" is actually a failure to distinguish formatting constraints (token-level grammar enforcement) from elicitation constraints (semantic field requirements that expand rather than restrict the generation space).</mechanism_or_metaphor>

<empirical_precedent>The self-explanation effect (Chi et al., 1994) is the most direct precedent: prompting students to explain each line of a text to themselves improved comprehension, not because of the format of the explanation, but because the act of generating an explanation is constructive, integrative, and error-correcting. A schema field labeled "assumptions" functions as a self-explanation prompt -- it forces the model to generate content about its own reasoning that it would not produce unprompted. This is distinct from Chain-of-Thought prompting, which elicits serial decomposition but does not direct the model to evaluate specific dimensions of its own output.

The expertise reversal effect (Kalyuga, 2007) provides the critical boundary condition the analysis omits. Kalyuga demonstrated that instructional guidance essential for novices becomes detrimental for experts because experts must reconcile external structure with their own internal schemas, increasing rather than decreasing cognitive load. If structured schemas function as scaffolding, then they should help weaker models more and potentially hurt stronger ones. The analysis assigns 0.80 confidence to "not novel" without testing whether the technique exhibits the signature pattern of genuine scaffolding.

Cognitive Prompting (Kramer & Baumann, arXiv 2410.02953) is a closer analog than the analysis acknowledges. Their self-adaptive variant, where the LLM dynamically selects which cognitive operations to perform, directly tests whether fixed versus flexible scaffolding matters -- and finds that adaptive scaffolding outperforms fixed sequences on larger models. This is the expertise reversal effect in action.</empirical_precedent>

<transfer_conditions>The technique should work under the following conditions and fail under the complementary ones:

(1) It should improve performance when the evaluative dimensions named in the schema (assumptions, missed evidence, confidence) are dimensions the model can compute but does not spontaneously produce. This is the self-explanation condition -- the knowledge is latent but un-elicited.

(2) It should degrade performance when the schema fields are redundant with operations the model already performs internally. A frontier reasoning model (o1-class) that already performs internal self-critique should show no gain or slight degradation from being forced to externalize that critique in a fixed schema. This is the expertise reversal prediction.

(3) The formatting overhead (JSON/XML grammar compliance) should be separable from the elicitation benefit. If the same fields are requested in natural language ("Now state your assumptions, then rate your confidence...") and produce equivalent gains, the mechanism is elicitation, not format. If the structured format outperforms the natural-language version, something about the grammar itself (perhaps deterministic field ordering preventing omission) contributes independently.

(4) The technique should fail on tasks where the model's bottleneck is knowledge retrieval rather than reasoning organization. Scaffolding helps with process, not with missing content.</transfer_conditions>

<prediction>The unreconciled tension in the analysis is actually the most informative signal. If the analysis had distinguished formatting constraints from elicitation constraints, it would have predicted exactly what CRANE (Banerjee et al., 2025) later confirmed: constrained decoding during reasoning steps hurts, but constrained structure around reasoning helps. The falsifiable prediction from cognitive science is this: if you implement the same evaluative fields using (a) constrained decoding that forces JSON/XML token-by-token compliance throughout generation, versus (b) a two-phase approach where the model reasons freely then populates the schema, approach (b) will outperform (a) by roughly the 10-15% that Tam et al. measured as the formatting tax, while both will outperform no-schema baselines by the elicitation bonus. If instead (a) and (b) perform equivalently, then the formatting constraint is not actually degrading reasoning in this case, and the Tam et al. finding does not generalize to schemas with semantically meaningful field names -- which would itself be a novel and publishable finding.

The 0.80 confidence that this is "not novel" is poorly calibrated. The individual ingredients exist (SGR, Cognitive Prompting, self-explanation prompts). But the specific claim that evaluative schema fields function as elicitation scaffolds while format constraints function as reasoning taxes -- and that these two forces coexist in every structured output call -- is not articulated in any of the cited works. Abdullin's SGR treats schemas as engineering methodology for testability, not as cognitive scaffolding. Kramer and Baumann study cognitive operation sequences, not evaluative self-critique fields. Ebouky et al.'s Cognitive Tools are runtime-invoked modules, not output schema fields. The composition may be obvious in retrospect, but the failure to distinguish the two opposing forces within it suggests the composition has not actually been performed.</prediction>

</review_from>

Sources:
- [Schema-Guided Reasoning (SGR) - Abdullin](https://abdullin.com/schema-guided-reasoning/)
- [Let Me Speak Freely? (Tam et al., 2408.02442)](https://arxiv.org/abs/2408.02442)
- [Cognitive Prompting (Kramer & Baumann, 2410.02953)](https://arxiv.org/abs/2410.02953)
- [Cognitive Tools (Ebouky et al., 2506.12115)](https://arxiv.org/abs/2506.12115)
- [CRANE: Reasoning with Constrained LLM Generation (Banerjee et al., 2502.09061)](https://arxiv.org/abs/2502.09061)
- [Decoupling Task-Solving and Output Formatting (Deng et al., 2510.03595)](https://arxiv.org/abs/2510.03595)
- [Expertise Reversal Effect (Kalyuga, 2007)](https://link.springer.com/article/10.1007/s10648-007-9054-3)
- [Eliciting Self-Explanations Improves Understanding (Chi et al., 1994)](https://onlinelibrary.wiley.com/doi/10.1207/s15516709cog1803_3)
- [Scaffolding Theory - Wood, Bruner & Ross (1976)](https://www.simplypsychology.org/zone-of-proximal-development.html)

## Notes

- Model: claude-opus-4-6 (subagent)
- Tools used: 9 (WebSearch)
- Duration: ~104s
- Key contribution: Resolved the Tam et al. "contradiction" — formatting constraints and elicitation constraints are orthogonal forces, not contradictory findings
- Introduced self-explanation effect (Chi et al. 1994) as the direct cognitive science precedent
- Predicted expertise reversal effect: schemas should help weaker models, hurt stronger ones
- Challenged the 0.80 confidence — argues the composition has not actually been performed despite ingredients existing
- Proposed falsifiable experiment: constrained decoding vs two-phase (reason then format)
