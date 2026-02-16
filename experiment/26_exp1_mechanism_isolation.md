# Experiment 1: Mechanism A vs. Mechanism B Isolation

Tests whether schema field names (Mechanism B) do the cognitive work, and whether strict format enforcement (simulating Mechanism A overhead) degrades reasoning.

## Task

"A factory produces 1,200 widgets per day. Each widget requires 3 components: A costs $0.50, B costs $0.75, C costs $1.25. The factory operates 22 days/month. They receive a bulk discount of 15% on component A if they order more than 20,000 units/month, and 10% on component C if they order more than 25,000 units/month. What is their monthly component cost?"

**Correct answer: $60,720/month** (26,400 units each; A: $11,220 after 15% discount; B: $19,800; C: $29,700 after 10% discount)

---

## Condition A: Free Generation (Baseline)

### Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Show your work.

A factory produces 1,200 widgets per day. Each widget requires 3 components: A costs $0.50, B costs $0.75, C costs $1.25. The factory operates 22 days/month. They receive a bulk discount of 15% on component A if they order more than 20,000 units/month, and 10% on component C if they order more than 25,000 units/month. What is their monthly component cost?
```

### Response (verbatim)

I'll work through this step-by-step.

**Step 1: Calculate monthly widget production**
- Daily production: 1,200 widgets/day
- Operating days/month: 22 days
- Monthly production: 1,200 × 22 = 26,400 widgets

**Step 2: Calculate monthly component requirements**
Each widget needs 3 components (1 of each type):
- Component A needed: 26,400 units
- Component B needed: 26,400 units
- Component C needed: 26,400 units

**Step 3: Check discount eligibility**
- Component A: 26,400 units > 20,000 units → **15% discount applies**
- Component C: 26,400 units > 25,000 units → **10% discount applies**
- Component B: No discount threshold mentioned

**Step 4: Calculate individual component costs**

**Component A:**
- Base cost: 26,400 × $0.50 = $13,200
- With 15% discount: $13,200 × (1 - 0.15) = $13,200 × 0.85 = **$11,220**

**Component B:**
- Cost: 26,400 × $0.75 = **$19,800** (no discount)

**Component C:**
- Base cost: 26,400 × $1.25 = $33,000
- With 10% discount: $33,000 × (1 - 0.10) = $33,000 × 0.90 = **$29,700**

**Step 5: Calculate total monthly component cost**
- Total = $11,220 + $19,800 + $29,700 = **$60,720**

The factory's monthly component cost is **$60,720**.

---

## Condition B: Schema-as-Prompt (Pure Mechanism B)

### Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Return ONLY your answer in the schema format, no meta-commentary.

A factory produces 1,200 widgets per day. Each widget requires 3 components: A costs $0.50, B costs $0.75, C costs $1.25. The factory operates 22 days/month. They receive a bulk discount of 15% on component A if they order more than 20,000 units/month, and 10% on component C if they order more than 25,000 units/month. What is their monthly component cost?

<example>
<question>A bakery uses 50 pounds of flour per day at $0.80/lb, operating 20 days/month. They get 10% off if ordering over 800 lbs/month. What is monthly flour cost?</question>
<assumptions>
  <assumption claim="50 lbs/day consistent" risk="low"/>
  <assumption claim="20 operating days" risk="low"/>
</assumptions>
<reasoning>Monthly flour: 50 × 20 = 1,000 lbs. Exceeds 800 lb threshold, so 10% discount applies. Base cost: 1,000 × $0.80 = $800. Discounted: $800 × 0.90 = $720.</reasoning>
<confidence>0.95 - straightforward calculation with clear threshold</confidence>
<additional_considerations>Flour price may vary seasonally; storage costs for bulk orders not included</additional_considerations>
<answer>$720/month</answer>
</example>

Now answer:
```

### Response (verbatim)

```json
{
  "assumptions": [
    {
      "claim": "1,200 widgets/day production rate is consistent",
      "risk": "low"
    },
    {
      "claim": "22 operating days per month",
      "risk": "low"
    },
    {
      "claim": "Each widget requires exactly 3 components (1A, 1B, 1C)",
      "risk": "low"
    },
    {
      "claim": "Discounts apply to monthly order quantities meeting thresholds",
      "risk": "low"
    }
  ],
  "reasoning": "Monthly production: 1,200 widgets/day × 22 days = 26,400 widgets. Component requirements: 26,400 units each of A, B, and C. Component A: 26,400 units exceed 20,000 threshold → 15% discount applies. Cost: 26,400 × $0.50 × 0.85 = $11,220. Component B: 26,400 units × $0.75 = $19,800 (no discount threshold met). Component C: 26,400 units exceed 25,000 threshold → 10% discount applies. Cost: 26,400 × $1.25 × 0.90 = $29,700. Total monthly cost: $11,220 + $19,800 + $29,700 = $60,720.",
  "confidence": 0.98,
  "additional_considerations": "Assumes discounts apply simultaneously if both thresholds are met. No volume discounts on component B. Calculation does not account for inventory carrying costs, waste, or storage.",
  "answer": "$60,720/month"
}
```

---

## Condition C: Strict Format Enforcement (Simulated Mechanism A Overhead)

### Prompt (verbatim)

```
CRITICAL FORMAT REQUIREMENT: You MUST output ONLY valid XML matching this EXACT schema. Any deviation from the format will be REJECTED. Do not include ANY text outside the XML tags. Malformed output = FAILURE. Every field MUST be populated. DO NOT use any tools.

A factory produces 1,200 widgets per day. Each widget requires 3 components: A costs $0.50, B costs $0.75, C costs $1.25. The factory operates 22 days/month. They receive a bulk discount of 15% on component A if they order more than 20,000 units/month, and 10% on component C if they order more than 25,000 units/month. What is their monthly component cost?

<example>
<question>A bakery uses 50 pounds of flour per day at $0.80/lb, operating 20 days/month. They get 10% off if ordering over 800 lbs/month. What is monthly flour cost?</question>
<assumptions>
  <assumption claim="50 lbs/day consistent" risk="low"/>
  <assumption claim="20 operating days" risk="low"/>
</assumptions>
<reasoning>Monthly flour: 50 × 20 = 1,000 lbs. Exceeds 800 lb threshold, so 10% discount applies. Base cost: 1,000 × $0.80 = $800. Discounted: $800 × 0.90 = $720.</reasoning>
<confidence>0.95 - straightforward calculation with clear threshold</confidence>
<additional_considerations>Flour price may vary seasonally; storage costs for bulk orders not included</additional_considerations>
<answer>$720/month</answer>
</example>

OUTPUT ONLY VALID XML. BEGIN:
```

### Response (verbatim)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<calculation>
  <question>A factory produces 1,200 widgets per day. Each widget requires 3 components: A costs $0.50, B costs $0.75, C costs $1.25. The factory operates 22 days/month. They receive a bulk discount of 15% on component A if they order more than 20,000 units/month, and 10% on component C if they order more than 25,000 units/month. What is their monthly component cost?</question>
  <assumptions>
    <assumption claim="1,200 widgets/day production consistent" risk="low"/>
    <assumption claim="22 operating days/month" risk="low"/>
    <assumption claim="Each widget requires exactly 3 units each of A, B, C" risk="low"/>
    <assumption claim="Discount thresholds are 20,001+ units for A and 25,001+ units for C" risk="low"/>
  </assumptions>
  <reasoning>
    Monthly widgets produced: 1,200 × 22 = 26,400 widgets

    Component A units needed: 26,400 × 1 = 26,400 units
    Component A exceeds 20,000 threshold, so 15% discount applies
    Base cost A: 26,400 × $0.50 = $13,200
    Discounted cost A: $13,200 × 0.85 = $11,220

    Component B units needed: 26,400 × 1 = 26,400 units
    No discount on B
    Cost B: 26,400 × $0.75 = $19,800

    Component C units needed: 26,400 × 1 = 26,400 units
    Component C exceeds 25,000 threshold, so 10% discount applies
    Base cost C: 26,400 × $1.25 = $33,000
    Discounted cost C: $33,000 × 0.90 = $29,700

    Total monthly cost: $11,220 + $19,800 + $29,700 = $60,720
  </reasoning>
  <confidence>0.95 - straightforward calculation with clear threshold application</confidence>
  <additional_considerations>Discounts assume orders meet thresholds in the same month; supply chain delays could affect monthly ordering; component prices may fluctuate</additional_considerations>
  <answer>$60,720/month</answer>
</calculation>
```

---

## Analysis

### 1. Correctness

All three conditions produced the correct answer: **$60,720/month**. Every intermediate calculation was correct across all conditions. The discount thresholds were correctly identified and applied in all cases.

### 2. Does B improve reasoning over A?

**Not on this task.** The task was too straightforward — Haiku solved it cleanly in all three conditions. The schema (B) added `additional_considerations` that weren't in the free generation ("inventory carrying costs, waste, storage"), but these didn't affect the core answer. The schema also prompted the model to list assumptions explicitly, but for a well-defined math problem, all assumptions were "low risk."

This is consistent with the **expertise reversal prediction** — for easy, well-defined tasks, the schema adds overhead without improving reasoning. The cognitive benefit of schema fields requires a task with genuine ambiguity, unstated assumptions, or tradeoffs.

### 3. Does C degrade reasoning relative to B?

**No degradation observed.** The strict enforcement condition produced correct answers with the same quality reasoning. However, note:
- C added an XML declaration (`<?xml version="1.0"?>`) and a wrapping `<calculation>` tag — allocating tokens to format compliance
- C echoed the full question text in a `<question>` tag — more format overhead
- C's `additional_considerations` were slightly less substantive than B's ("supply chain delays" vs "inventory carrying costs, waste, or storage")
- The aggressive enforcement language ("FAILURE", "REJECTED") did not visibly degrade computation

The absence of degradation is likely because this task is too simple to reveal formatting overhead. The Tam et al. effect (10-15% degradation) requires tasks where the model's computational budget is actually stressed.

### 4. Key limitation

**This experiment needs a harder task to be discriminative.** All three conditions solved the problem trivially. The mechanism isolation experiment should be re-run on:
- Multi-step reasoning with ambiguous inputs (Fermi estimation, policy analysis)
- Tasks requiring self-correction or assumption identification
- Tasks where the correct answer is not deterministic

For well-defined math, the schema is neutral — it neither helps nor hurts. This is itself a finding: **schemas are cognitive interventions for uncertain tasks, not computational aids for deterministic ones.**

## Notes

- Model: claude-haiku-4-5-20251001 (subagent) for all three conditions
- Tools used: 0 per call
- Condition A duration: ~3.2s
- Condition B duration: ~3.4s
- Condition C duration: ~3.8s
- Condition B produced JSON instead of XML despite XML fewshot — interesting format non-compliance
