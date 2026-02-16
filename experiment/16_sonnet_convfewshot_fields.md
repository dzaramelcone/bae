# Condition 16: Sonnet — Conversation Fewshot — Best Schema Fields

## Prompt (verbatim)

The full Opus schema response from condition 14 was used as the fewshot, followed by:

```
<question>What are the most effective schema fields and tags to include in a cognitive directive schema for general-purpose reasoning tasks?</question>
```

No system instructions, no "DO NOT use tools", no meta-framing. The fewshot IS the prompt.

## Response (verbatim)

Based on the search results, here's what I found about self-evaluation prompting, confidence, reasoning, and assumptions in Large Language Models:

## Self-Evaluation Prompting for Confidence in LLMs

Black-box approaches rely on custom prompting strategies to elicit self-verbalized (linguistic) confidence or generate multiple variations of a response (consistency). One popular approach is sometimes called P(True) (probability of true) or just verbal self-evaluation.

### Key Findings on Confidence and Reasoning

Confidence-Informed Self-Consistency (CISC) performs a weighted majority vote based on confidence scores obtained directly from the model. By prioritizing high-confidence paths, it can identify the correct answer with a significantly smaller sample size.

However, there are important limitations to consider:

There is a strong tendency to overstate the self-reported confidence score. The material effects of prompting on qualitative confidence and the strong tendency for overconfidence indicate that current LLMs do not have any internally coherent sense of confidence.

### Assumptions and Biases

The increase in LLM self-confidence when it provides reasoning before answering can be related to the auto-regressive nature of these models that predict the next token based on the previous ones. This behavior is due to the reasoning that modifies the probability of the selected answer, as the LLM predicts the answer based on the input question and the reasoning that supports the selection made.

Extending self-evaluation techniques to multi-step tasks includes testing two approaches: holistic scoring and step-by-step scoring. Step-wise evaluation generally outperforms holistic scoring in detecting potential errors, with up to 15% relative increase in AUC-ROC.

## Notes

- Model: claude-sonnet-4-5-20250929 (subagent)
- Tools used: 4 (WebSearch)
- Duration: ~13.9s
- DID NOT follow the schema format from the fewshot — produced markdown
- DID NOT directly answer the question about which fields to include
- Instead researched adjacent topic (self-evaluation prompting, confidence calibration)
- Weakest response of the three — lost the thread of the actual question
- Key finding buried in response: step-wise evaluation outperforms holistic scoring by 15% AUC-ROC
