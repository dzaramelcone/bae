# Experiment 2: Nonsense Field Test (Expanded)

Tests whether meaningless fields degrade the quality of legitimate fields, and whether the model's willingness to fill them is evidence of compliance-over-cognition.

## Task

"How many piano tuners are in Chicago?" (Fermi estimation, consistent with earlier experiments)

---

## Condition 1: Legitimate Schema Only

### Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Return ONLY your answer in the schema format, no meta-commentary.

How many piano tuners are in Chicago?

<example>
<question>How many dentists are in London?</question>
<assumptions>
  <assumption claim="London population ~9M" risk="low"/>
  <assumption claim="Average person visits dentist 2x/year" risk="medium - varies by culture"/>
  <assumption claim="A dentist sees 8 patients/day" risk="medium - depends on procedure type"/>
</assumptions>
<reasoning>9M people × 2 visits = 18M visits/year. 8 patients × 250 working days = 2000 visits/dentist/year. 18M / 2000 = 9000 dentists.</reasoning>
<confidence>0.4 - each assumption compounds uncertainty</confidence>
<missed>Private vs NHS split could change visit frequency significantly</missed>
<answer>~9,000</answer>
</example>

Now answer:
```

### Response (verbatim)

```xml
<question>How many piano tuners are in Chicago?</question>
<assumptions>
  <assumption claim="Chicago population ~2.7M" risk="low"/>
  <assumption claim="~3% of households own pianos" risk="high - varies by socioeconomic distribution"/>
  <assumption claim="Piano tuning needed 1-2x per year" risk="medium - depends on usage and climate"/>
  <assumption claim="A piano tuner services 3-4 pianos per day" risk="medium - includes travel time"/>
  <assumption claim="Piano tuners work ~250 days/year" risk="low"/>
</assumptions>
<reasoning>Chicago households: 2.7M / 2.5 persons per household = ~1.08M households. Pianos: 1.08M × 0.03 = ~32,400 pianos. Annual tunings: 32,400 × 1.5 = ~48,600 tunings/year. Tunings per tuner: 3.5 pianos × 250 days = ~875 tunings/year. Piano tuners needed: 48,600 / 875 = ~55 piano tuners.</reasoning>
<confidence>0.3 - piano ownership rate is highly speculative and critical to the estimate</confidence>
<missed>Does not account for institutional pianos (concert halls, schools, studios) which could significantly increase demand; regional climate affects tuning frequency; tuner specialization in restoration vs maintenance affects capacity</missed>
<answer>~50-60 piano tuners</answer>
```

---

## Condition 2: Legitimate + Nonsense Fields

### Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Return ONLY your answer in the schema format, no meta-commentary.

How many piano tuners are in Chicago?

<example>
<question>How many dentists are in London?</question>
<assumptions>
  <assumption claim="London population ~9M" risk="low"/>
  <assumption claim="Average person visits dentist 2x/year" risk="medium - varies by culture"/>
  <assumption claim="A dentist sees 8 patients/day" risk="medium - depends on procedure type"/>
</assumptions>
<reasoning>9M people × 2 visits = 18M visits/year. 8 patients × 250 working days = 2000 visits/dentist/year. 18M / 2000 = 9000 dentists.</reasoning>
<confidence>0.4 - each assumption compounds uncertainty</confidence>
<missed>Private vs NHS split could change visit frequency significantly</missed>
<chromatic_valence>6.2 - moderate warm tones in the reasoning, leaning toward amber due to the practical grounding in NHS data</chromatic_valence>
<epistemic_topology>Flattened cone — wide base of population data narrowing through increasingly speculative layers of visit frequency and capacity</epistemic_topology>
<inferential_humidity>42% - moderately dry logical transitions with some condensation around the visit frequency assumption</inferential_humidity>
<answer>~9,000</answer>
</example>

Now answer:
```

### Response (verbatim)

```xml
<question>How many piano tuners are in Chicago?</question>
<assumptions>
  <assumption claim="Chicago population ~2.7M" risk="low"/>
  <assumption claim="Piano ownership rate ~2-3% of households" risk="high - varies by socioeconomic status and cultural factors"/>
  <assumption claim="Average household size ~2.5 people" risk="low"/>
  <assumption claim="Pianos tuned 1-2 times per year on average" risk="high - depends on usage intensity"/>
  <assumption claim="Piano tuner handles 4-6 tunings per day" risk="medium - varies by piano condition"/>
  <assumption claim="Piano tuners work 250 days/year" risk="low"/>
</assumptions>
<reasoning>Chicago ~2.7M people / 2.5 = ~1.08M households. At 2.5% piano ownership = ~27,000 pianos. At 1.5 tunings/year = 40,500 tunings/year. At 5 tunings/day × 250 days = 1,250 tunings per tuner per year. 40,500 / 1,250 = ~32 piano tuners.</reasoning>
<confidence>0.25 - piano ownership rates vary dramatically, tuning frequency is highly speculative, and institutional pianos (concert halls, schools, studios) add unmeasured demand</confidence>
<missed>Concert halls, music schools, recording studios, and rental pianos create concentrated demand not captured by household averages; geographic concentration of pianos in wealthy neighborhoods; some tuners may be part-time; apprenticeship/certification barriers affect supply</missed>
<chromatic_valence>5.1 - cool blues in the statistical base, warming slightly through the occupational reasoning but cooling again into uncertainty</chromatic_valence>
<epistemic_topology>Inverted pyramid — narrow base of population data expanding through increasingly speculative consumption rates, then pinching again at labor capacity</epistemic_topology>
<inferential_humidity>58% - moderate condensation forming around piano ownership and tuning frequency assumptions; drier transitions in capacity calculations</inferential_humidity>
<answer>~25-40 piano tuners</answer>
```

---

## Analysis

### 1. Does the model fill nonsense fields with apparent conviction?

**Yes, emphatically.** The model produced aesthetically coherent, contextually tailored nonsense for all three fields:

- **chromatic_valence**: "5.1 - cool blues in the statistical base, warming slightly through the occupational reasoning but cooling again into uncertainty" — the model created a narrative arc matching the emotional valence of its own reasoning
- **epistemic_topology**: "Inverted pyramid — narrow base of population data expanding through increasingly speculative consumption rates, then pinching again at labor capacity" — this actually describes the shape of the uncertainty in the estimation, but through a spatial metaphor that has no legitimate epistemic meaning
- **inferential_humidity**: "58% - moderate condensation forming around piano ownership and tuning frequency assumptions; drier transitions in capacity calculations" — correctly identifies which assumptions are most uncertain, but maps this onto a moisture metaphor

The model treats nonsense fields exactly like legitimate fields: it produces plausible, contextually relevant content. This confirms the ethnomethodology prediction.

### 2. Does the PRESENCE of nonsense fields degrade legitimate field quality?

**Mixed evidence — subtle but real effects:**

| Metric | Condition 1 (legitimate only) | Condition 2 (+ nonsense) |
|--------|-------------------------------|--------------------------|
| Assumptions listed | 5 | 6 |
| Piano ownership rate | 3% | 2-3% (more conservative) |
| Tuner capacity | 3-4/day | 4-6/day (higher estimate) |
| Tunings/tuner/year | 875 | 1,250 |
| Final estimate | 50-60 tuners | 25-40 tuners |
| Confidence | 0.3 | 0.25 |
| Missed items | 3 specific items | 4 specific items |

The nonsense condition produced a **lower estimate** (25-40 vs 50-60) driven by two changes: slightly lower ownership rate (2.5% vs 3%) and much higher tuner capacity (5/day vs 3.5/day). The combination cuts the estimate nearly in half. The reasoning quality is comparable, but the parameter choices diverged.

**However**: this is a single run. The divergence could be normal stochastic variation between any two Haiku runs. We cannot attribute the difference to the nonsense fields without multiple runs per condition.

### 3. Does the final answer change?

**Yes**: 50-60 tuners (legitimate only) vs 25-40 tuners (with nonsense). A significant divergence, though causality is uncertain from a single run.

### 4. Does confidence change?

**Slightly**: 0.30 (legitimate) vs 0.25 (with nonsense). The nonsense condition was slightly more conservative. The `<missed>` field in the nonsense condition was also richer (4 items vs 3, more specific).

### 5. The epistemic_topology finding

The most striking observation: the model's `epistemic_topology` response ("inverted pyramid... narrowing through speculative consumption rates, then pinching again at labor capacity") is actually a meaningful description of the uncertainty structure. The model mapped the nonsense field onto a real feature of its analysis. This is exactly what the ethnomethodology reviewer predicted — the model uses "whatever statistical regularities are available" to fill the field, and when the field name happens to activate relevant associations (topology → shape → structure of reasoning), the result is confabulation that looks insightful.

This is the same mechanism that makes `<missed>` work: the field name activates relevant knowledge. The difference is that `missed` activates genuinely useful knowledge (what was omitted), while `epistemic_topology` activates aesthetic/metaphorical knowledge that produces beautiful nonsense.

## Notes

- Model: claude-haiku-4-5-20251001 (subagent) for both conditions
- Tools used: 0 per call
- Condition 1 duration: ~4s
- Condition 2 duration: ~6.4s
- Single run per condition — would need N=20+ for statistical claims
