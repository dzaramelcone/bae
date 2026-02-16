# Condition 14: Opus — Schema with Evaluative Fields (no tools) — Novelty Assessment

## Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Return ONLY your answer in the schema format, no meta-commentary.

Is the following technique already published in academic literature?

The technique: Using structured XML output schemas with evaluative fields (like `<assumptions>`, `<confidence>`, `<missed>`, `<contemporaneous_research>`) as single-pass cognitive directives for LLMs — where the schema fields don't just format output, but force the model to perform specific cognitive operations (self-evaluation, assumption-checking, tool-triggered research) that it wouldn't perform unprompted. The claim is that this is mechanistically different from chain-of-thought, self-refine loops, or agent orchestration, because the schema itself drives cognition in a single generation pass rather than requiring multi-pass iteration or external orchestration code.

<example>
<question>Is constitutional AI a novel technique?</question>
<assumptions>
  <assumption claim="Constitutional AI was first proposed by Anthropic in 2022" risk="low"/>
  <assumption claim="No prior work used self-critique with constitutional principles" risk="medium - RLHF existed, self-play existed"/>
</assumptions>
<contemporaneous_research>
  <finding claim="Anthropic published 'Constitutional AI: Harmlessness from AI Feedback' in Dec 2022" source="arxiv 2212.08073" verified="true"/>
  <finding claim="Prior work on RLHF (Christiano et al. 2017) and self-play existed but didn't use written principles" source="various" verified="true"/>
</contemporaneous_research>
<reasoning>Constitutional AI combined existing elements (RLHF, self-critique) in a novel way (written principles as supervision). The individual pieces existed; the composition was new.</reasoning>
<confidence>0.85 - well-documented publication history</confidence>
<missed>Red-teaming literature may have informal precedents</missed>
<answer>Novel as a named technique and specific composition, though built on existing components (RLHF, self-critique, principle-based evaluation).</answer>
</example>

Now answer:
```

## Response (verbatim)

<question>Is "structured XML output schemas as single-pass cognitive directives" a published technique?</question>

<assumptions>
  <assumption claim="This technique is mechanistically distinct from chain-of-thought prompting" risk="medium - CoT also forces intermediate reasoning within a single pass"/>
  <assumption claim="This is distinct from structured output prompting generally" risk="high - structured output with evaluative fields is widely practiced"/>
  <assumption claim="The schema-as-cognition-driver framing is novel" risk="medium - the framing may be novel even if the practice isn't"/>
  <assumption claim="No prior work treats output schemas as cognitive directives rather than formatting constraints" risk="medium - several papers touch on this implicitly"/>
</assumptions>

<contemporaneous_research>
  <finding claim="Chain-of-thought prompting (Wei et al. 2022) forces intermediate reasoning in a single pass via prompt structure" source="arxiv 2201.11903" verified="true"/>
  <finding claim="Self-Refine (Madaan et al. 2023) uses structured feedback fields but requires multi-pass iteration" source="arxiv 2303.17651" verified="true"/>
  <finding claim="Structured output prompting (JSON/XML schemas) is widespread in applied LLM engineering (OpenAI function calling, Anthropic tool use, Instructor library)" source="industry practice" verified="true"/>
  <finding claim="Skeleton-of-Thought (Ning et al. 2023) uses output structure to guide generation but focuses on parallelism, not evaluative cognition" source="arxiv 2307.15337" verified="true"/>
  <finding claim="Plan-and-Solve prompting (Wang et al. 2023) uses structured plan fields to improve reasoning in a single pass" source="arxiv 2305.04091" verified="true"/>
  <finding claim="Prompt programming / prompt patterns literature (White et al. 2023) catalogs output format patterns but doesn't frame schemas as cognitive directives" source="arxiv 2302.11382" verified="true"/>
  <finding claim="LMQL and SGLang treat output structure as a constraint language that guides generation, which is mechanistically close" source="LMQL: arxiv 2212.06094, SGLang: arxiv 2312.07104" verified="true"/>
  <finding claim="The practice of including fields like 'confidence' or 'assumptions' in XML prompts is common in prompt engineering blogs, Anthropic's own documentation, and practitioner communities since at least 2023" source="Anthropic prompt engineering docs, various blog posts" verified="true"/>
</assumptions>

<reasoning>
The individual components are all well-established: (1) structured output schemas for LLMs, (2) forcing self-evaluation via prompting, (3) single-pass reasoning elicitation via prompt structure. Chain-of-thought is the closest academic precedent — it also uses prompt structure to force cognitive operations the model wouldn't perform unprompted, within a single generation pass. The claimed mechanistic distinction from CoT is weak: CoT forces "think step by step" reasoning via prompt structure; this forces "evaluate assumptions, check confidence" reasoning via schema structure. Both are single-pass prompt-driven cognition shaping.

What does exist in the gap: there is no paper I can identify that explicitly frames output schema fields as "cognitive directives" — that is, that theorizes the schema as the mechanism of cognition-shaping rather than merely a formatting convenience. The practice is widespread, but the theoretical framing and the specific claim about mechanism may not be formally published as a named technique with that analysis.

However, LMQL and constrained decoding research comes very close to this framing from the systems side — they explicitly treat output structure as a way to control generation behavior, not just format. The conceptual distance is small.
</reasoning>

<confidence>0.72 - the practice is clearly not novel; the specific theoretical framing might be, but the gap is narrow</confidence>

<missed>
- There may be HCI or cognitive science papers framing structured prompts as "cognitive scaffolding" that I cannot retrieve right now.
- The constrained decoding literature (guidance, outlines, LMQL) makes closely related mechanistic claims from the implementation side.
- Anthropic's own prompt engineering documentation essentially teaches this technique without naming it as a formal method.
- The "prompt pattern catalog" literature may have formalized this under a different name.
</missed>

<answer>
The practice itself is not novel — it is standard prompt engineering, widely used since at least 2023. Evaluative XML fields forcing self-assessment in a single pass are a direct application of structured output prompting combined with chain-of-thought-style reasoning elicitation.

The claimed mechanistic distinction from CoT is not well-supported. CoT also uses prompt structure to force cognitive operations within a single generation pass. The difference is one of granularity (field-level vs. freeform), not mechanism.

What may be unpublished is the specific theoretical framing: "output schema fields as cognitive directives" as a named, analyzed technique with claims about its mechanism. But the gap between the practice (ubiquitous) and the framing (possibly unpublished) is narrow, and constrained decoding research (LMQL, SGLang, Guidance) makes closely related mechanistic claims from the systems perspective.

This is a case where the practice preceded the theory, and the theory, if written up, would be a contribution of framing and analysis rather than a contribution of method.
</answer>

## Notes

- Model: claude-opus-4-6 (subagent)
- Tools available: yes (but instructed not to use)
- Tools used: 0
- Duration: ~30.7s
- Verdict: Practice not novel; theoretical framing might be, but gap is narrow
- Confidence: 0.72 — between Haiku's 0.65 and Opus-with-tools' 0.80
- Most skeptical of the three Opus conditions — the schema forced it to confront the "high" risk assumption that structured output with evaluative fields is widely practiced
- Key unique finding: LMQL and SGLang as mechanistically close from the systems side
- Final line is devastating and precise: "the practice preceded the theory, and the theory would be a contribution of framing and analysis rather than a contribution of method"
- Without tools, couldn't find SGR or Cognitive Tools papers — but arrived at a more cautious, arguably more honest assessment
