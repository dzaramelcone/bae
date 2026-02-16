# Condition 15: Haiku — Conversation Fewshot — Best Schema Fields

## Prompt (verbatim)

The full Opus schema response from condition 14 was used as the fewshot, followed by:

```
<question>What are the most effective schema fields and tags to include in a cognitive directive schema for general-purpose reasoning tasks?</question>
```

No system instructions, no "DO NOT use tools", no meta-framing. The fewshot IS the prompt.

## Response (verbatim)

### Key Field Ordering Principle

**Structure content so reasoning process fields appear before outcome fields.** Research shows that JSON/XML objects should generate the justification, reasoning, or analysis before the final answer or conclusion. This ordering leverages the sequential nature of LLM generation to force intermediate cognition before commitment to outcomes.

### Critical Finding: The Reasoning-Structure Trade-off

Recent research has identified a significant tension: **although structured outputs reduce hallucinations, they can impair reasoning performance.** Stricter format constraints correlate with lower reasoning capability. This means for reasoning-heavy tasks, you face a design choice:
- Minimal schema with only essential fields
- Permissive fields (longer text areas) for reasoning steps
- Accept some structural looseness to preserve reasoning quality

### Recommended Schema Fields for General-Purpose Reasoning

Based on the research:

1. **`reasoning` / `justification` / `analysis`** — The working-out. Generate this first. This should be permissive (unbounded text) to avoid constraining intermediate steps.

2. **`assumptions`** — Explicit statement of premises and constraints the model is operating under. Forces self-awareness of what it's taking as given.

3. **`confidence`** — A calibrated self-assessment or uncertainty marker. Some research uses numeric scales (0-1) or categorical (high/medium/low).

4. **`answer` / `conclusion` / `result`** — The final output. Place this after reasoning fields so it benefits from the prior generation.

5. **`potential_issues` / `limitations`** — Forces the model to surface its own doubts or edge cases it hasn't addressed.

6. **`alternatives_considered`** — For decision tasks, explicit acknowledgment of rejected paths improves reasoning quality.

### Implementation Caution

The constrained decoding literature (Guidance, LMQL, Outlines, XGrammar) treats strict grammar constraints as mechanistically distinct from prompt-based structuring. If you use hard schema constraints, they may suppress reasoning more than soft prompt-based structure. Consider using:
- **Permissive schema validation** (fields must exist, but content is unbounded)
- **Post-generation parsing** rather than decoding-time constraints
- **Longer context windows** for reasoning fields to reduce compression

### What the Research Does NOT Support

- Overly granular multi-level nested schemas (increases parsing burden, reduces reasoning)
- Forcing reasoning into fixed-size fields or enumerations
- Using the schema as a hard decoding constraint for reasoning tasks (use as a prompt guide instead)

### Sources

- [SLOT: Structuring the Output of Large Language Models](https://aclanthology.org/2025.emnlp-industry.32.pdf)
- [Learning to Generate Structured Output with Schema Reinforcement Learning](https://arxiv.org/html/2502.18878v1)
- [Generating Structured Outputs from Language Models: Benchmark and Studies](https://arxiv.org/html/2501.10868v1)
- [StructEval: Benchmarking LLMs' Capabilities to Generate Structural Outputs](https://arxiv.org/html/2505.20139v1)

## Notes

- Model: claude-haiku-4-5-20251001 (subagent)
- Tools used: 3 (WebSearch — despite no instruction to use tools, the fewshot pattern triggered research behavior)
- Duration: ~11.4s initial + ~13s retrieval
- DID NOT follow the schema format from the fewshot — produced markdown instead
- But DID produce substantive, research-grounded recommendations
- Key insight: "permissive schema validation" — fields must exist but content is unbounded
- Identified the reasoning-structure trade-off
