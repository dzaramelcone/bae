# Panel Review 3: Clinical Protocol Design

## Response (verbatim)

<review_from perspective="clinical protocol design">

<comparable_protocol>
Cognitive Forcing Strategies (CFS) in clinical decision-making -- specifically Croskerry's three-tier framework (universal, generic, specific) published in Annals of Emergency Medicine (2003). A CFS is a structured intervention imposed at the point of decision that forces the clinician to engage System 2 (analytical) reasoning before acting on System 1 (intuitive) pattern recognition. The XML schema with fields like "assumptions," "confidence," "missed," and "contemporaneous_research" maps almost perfectly onto a specific-level CFS: it forces the reasoner to enumerate competing hypotheses, quantify uncertainty, and check for premature closure -- all before producing a final answer. We have been doing this in medicine for over two decades.
</comparable_protocol>

<when_structure_helps>
Structure helps LLMs in the same conditions where it helps clinicians: when the failure mode is premature closure. Croskerry (2009) documented that the most common cognitive error in diagnostic reasoning is premature closure -- accepting a diagnosis before verification is complete. An LLM generating free-form text is the cognitive equivalent of a clinician pattern-matching under time pressure: it produces the most probable completion and stops. A schema field like "missed" is a forced differential diagnosis. A "confidence" field is a calibration check. An "assumptions" field is an explicit surfacing of anchoring biases. These are not novel cognitive science -- they are direct translations of cognitive debiasing interventions that have been validated in clinical settings (Graber et al., 2012; Croskerry, 2003). The analysis at confidence 0.80 that this is "a composition of existing published ideas" is, from the clinical protocol perspective, correct. We would say the confidence should be higher -- 0.90 or above. This is established practice with a new substrate.
</when_structure_helps>

<when_structure_harms>
The Tam et al. (2408.02442) finding that format constraints degrade reasoning by 10-15% is not contradictory to the claim that schemas improve cognition. It is the exact same tension we observe in clinical protocol design, and it has a known resolution.

The CRANE paper (Banerjee et al., ICML 2025) provides the mechanistic explanation for LLMs specifically: constraining output tokens to a strict grammar reduces the model's effective reasoning space. The solution CRANE proposes -- adaptively switching between unconstrained and constrained generation -- mirrors what we have known in clinical protocols for years.

In medicine, the documented harms of structure are:

1. Checklist tunnel vision. Hales & Pronovost (2006) and subsequent work on "smarter clinical checklists" (Hales et al., 2015) showed that rigid checklists cause clinicians to follow the form mechanically and miss atypical presentations that do not map to any checklist item. The LLM equivalent: a schema that forces the model to fill every field may cause it to allocate tokens to low-value boilerplate instead of reasoning about the hard part of the problem.

2. Cognitive load displacement. The structure itself consumes cognitive resources. In an LLM, token budget spent formatting JSON/XML is token budget not spent reasoning. This is precisely what Tam et al. measured. It is not a contradiction -- it is the cost side of a cost-benefit equation.

3. False confidence from completion. When a clinician fills out every field on a structured form, the completeness of the form creates an illusion of thoroughness. A filled "missed" field that says "None identified" is not evidence that nothing was missed -- it is evidence that the structured form was completed. The same applies to LLMs: a populated schema can look more rigorous than it is.
</when_structure_harms>

<design_recommendation>
The analysis under review correctly identifies that schema-as-cognitive-directive is not novel. But it fails to reconcile the Tam et al. tension, and that failure matters because the reconciliation is where the actual design insight lives.

From clinical protocol design, the recommendation is the same one we give for clinical decision support: adaptive, complexity-matched structure.

1. Separate reasoning from formatting. CRANE's approach of allowing unconstrained reasoning followed by constrained output is the LLM equivalent of the clinical "think aloud, then document" protocol. The schema should scaffold the final output, not cage the intermediate reasoning. This means: chain-of-thought first, structured extraction second. Not a single-pass schema fill.

2. Scale structure to task difficulty. Simple factual retrieval needs minimal structure (a clinician triaging a clearly broken arm does not need a full differential diagnosis protocol). Complex reasoning under uncertainty benefits from forced cognitive operations (an ambiguous chest pain presentation warrants the full CFS). A single-pass schema applied uniformly to all queries is the equivalent of running Manchester Triage on a patient presenting for a flu shot -- it adds cost without benefit.

3. Treat schema fields as interventions, not containers. Each field in the schema (assumptions, missed, confidence) is a cognitive forcing function. Design each one deliberately: What bias does it debias? What error does it prevent? If you cannot answer that for a field, remove it. Checklist fatigue (Hales et al., 2015) is real and the LLM equivalent -- token budget waste -- is measurable.

4. Validate the schema against the failure mode, not the success case. The artifact under review shows no evidence that anyone measured whether the "missed" field actually catches errors the model would otherwise make, or whether the "confidence" field is calibrated. In clinical protocol design, we would never deploy a checklist without measuring its impact on the error rate it targets. The same standard should apply here.

The overall assessment: the analysis is correct that this is not novel (I would raise confidence to 0.90). The unreconciled Tam et al. tension is not a contradiction but a well-characterized cost-benefit tradeoff that clinical protocol design resolved years ago. The resolution is: structure is medicine, not food. Prescribe it for the condition, at the right dose, and measure the outcome.
</design_recommendation>

</review_from>

Sources:
- [Cognitive Forcing Strategies in Clinical Decisionmaking - Croskerry 2003](https://www.annemergmed.com/article/S0196-0644(02)84945-9/fulltext)
- [Clinical Cognition and Diagnostic Error: Dual Process Model - Croskerry 2009](https://pubmed.ncbi.nlm.nih.gov/19669918/)
- [Schema-Guided Reasoning - Abdullin 2025](https://abdullin.com/schema-guided-reasoning/)
- [Let Me Speak Freely? - Tam et al. 2024](https://arxiv.org/abs/2408.02442)
- [CRANE - Banerjee et al., ICML 2025](https://arxiv.org/abs/2502.09061)
- [Smarter Clinical Checklists - Hales et al. 2015](https://pubmed.ncbi.nlm.nih.gov/26197378/)
- [MDAgents: Adaptive Collaboration of LLMs for Medical Decision-Making](https://arxiv.org/html/2404.15155v2)
- [DECLARE: Comprehensive Cognitive Forcing Strategy](https://pmc.ncbi.nlm.nih.gov/articles/PMC10149772/)

## Notes

- Model: claude-opus-4-6 (subagent)
- Tools used: 7 (WebSearch)
- Duration: ~86s
- "Structure is medicine, not food. Prescribe it for the condition, at the right dose, and measure the outcome."
- Would raise confidence to 0.90 — this is established practice with a new substrate
- Mapped schema fields directly to clinical cognitive debiasing: missed = forced differential, confidence = calibration check, assumptions = anchoring bias surfacing
- Resolved Tam et al. tension same way as cognitive science reviewer but from different angle: cost-benefit, not orthogonal forces
- Key warning: false confidence from completion — a filled "missed" field saying "None identified" proves the form was filled, not that nothing was missed
