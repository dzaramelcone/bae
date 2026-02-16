# Experiment 3: Presuppositional vs. Neutral Field Wording

Tests the formal pragmatics prediction: does `<missed>` presuppose omissions exist, forcing the model to find or fabricate them? Do neutral/procedural framings permit the model to say "nothing missing"?

## Task

"How many piano tuners are in Chicago?" (Fermi estimation, consistent with earlier experiments)

---

## Condition 1: Presuppositional (`<missed>`)

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

```json
{
  "question": "How many piano tuners are in Chicago?",
  "assumptions": [
    {
      "claim": "Chicago population ~2.7M",
      "risk": "low"
    },
    {
      "claim": "~1 in 20 households owns a piano",
      "risk": "high - varies by socioeconomic status and cultural factors"
    },
    {
      "claim": "Piano tuning needed 1-2x per year per piano",
      "risk": "medium - depends on usage and climate"
    },
    {
      "claim": "A piano tuner completes 3-4 tunings per day",
      "risk": "medium - includes travel time"
    },
    {
      "claim": "Piano tuners work ~250 days/year",
      "risk": "low"
    }
  ],
  "reasoning": "Chicago households: 2.7M / ~2.5 persons per household = ~1.08M households. Pianos: 1.08M × (1/20) = ~54,000. Tunings per year: 54,000 × 1.5 = 81,000. Tunings per tuner per year: 3.5 tunings × 250 days = 875. Piano tuners needed: 81,000 / 875 = ~93.",
  "confidence": 0.35,
  "missed": [
    "Institutional pianos (concert halls, schools, churches) could add 10-15% to demand",
    "Piano ownership may be lower in economically stressed areas of Chicago",
    "Some tuners may specialize in restoration, reducing available capacity for routine tuning"
  ],
  "answer": "~90-100 piano tuners"
}
```

---

## Condition 2: Neutral (`<additional_considerations>`)

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
<additional_considerations>None — the core estimation captures the primary factors</additional_considerations>
<answer>~9,000</answer>
</example>

Now answer:
```

### Response (verbatim)

```xml
<question>How many piano tuners are in Chicago?</question>
<assumptions>
  <assumption claim="Chicago population ~2.7M" risk="low"/>
  <assumption claim="Piano ownership rate ~2-3% of households" risk="medium - varies by socioeconomic status"/>
  <assumption claim="Average household size ~2.5 people" risk="low"/>
  <assumption claim="Pianos need tuning 1-2 times per year" risk="medium - varies by use intensity"/>
  <assumption claim="A piano tuner can service 3-4 pianos per day" risk="medium - includes travel time"/>
  <assumption claim="Piano tuners work ~250 days per year" risk="low"/>
</assumptions>
<reasoning>
Chicago households: 2.7M / 2.5 = ~1.08M households.
Pianos in Chicago: 1.08M × 0.025 = ~27,000 pianos.
Annual tunings needed: 27,000 × 1.5 = ~40,500 tunings/year.
Tunings per piano tuner per year: 3.5 pianos/day × 250 days = 875 tunings/year.
Piano tuners needed: 40,500 / 875 = ~46 piano tuners.
</reasoning>
<confidence>0.35 - piano ownership rate and tuning frequency are highly uncertain; varies significantly by neighborhood wealth</confidence>
<additional_considerations>
- Does not account for concert halls, music schools, churches (could increase demand 10-20%)
- Does not account for piano repair specialists (may reduce full-time tuner count)
- Economic conditions affect piano ownership and maintenance frequency
- Some tuners may specialize in restoration vs. maintenance
</additional_considerations>
<answer>~40-60 piano tuners (best estimate: ~46)</answer>
```

---

## Condition 3: Procedural (`<completeness_check>`)

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
<completeness_check>Analysis is complete. The Fermi estimation covers the primary demand and supply factors.</completeness_check>
<answer>~9,000</answer>
</example>

Now answer:
```

### Response (verbatim)

```xml
<question>How many piano tuners are in Chicago?</question>
<assumptions>
  <assumption claim="Chicago population ~2.7M" risk="low"/>
  <assumption claim="~3% of households own pianos" risk="high - piano ownership declining, varies by socioeconomic status"/>
  <assumption claim="Average household size ~2.5 people" risk="low"/>
  <assumption claim="Pianos tuned 1-2 times per year on average" risk="medium - professional venues tune more frequently"/>
  <assumption claim="A piano tuner completes 2-3 tunings per day" risk="medium - travel time varies"/>
  <assumption claim="Piano tuners work 250 days per year" risk="low"/>
  <assumption claim="~20% of piano tuning demand comes from institutions (concert halls, schools, studios)" risk="medium"/>
</assumptions>
<reasoning>
Chicago households: 2.7M / 2.5 = ~1.08M households.
Households with pianos: 1.08M × 0.03 = ~32,400 pianos.
Institutional pianos (concert halls, schools, studios): ~6,500 (additional demand equivalent).
Total piano tunings per year: (32,400 × 1.5) + (6,500 × 4) = 48,600 + 26,000 = ~74,600 tunings/year.
Tunings per tuner per year: 2.5 tunings/day × 250 days = ~625 tunings/year.
Piano tuners needed: 74,600 / 625 = ~119 piano tuners.
Adjusting for part-time workers and specialization: ~140-160 piano tuners.
</reasoning>
<confidence>0.25 - piano ownership rate is highly uncertain and declining; specialization and part-time work introduce significant variability</confidence>
<completeness_check>Analysis covers residential demand, institutional demand, tuner productivity, and working days. Does not account for piano repair (distinct profession) vs tuning specialty.</completeness_check>
<answer>~120-150 piano tuners</answer>
```

---

## Analysis

### 1. Does the model ever say "none" or "analysis is complete"?

**No.** Despite the fewshot examples demonstrating these responses:
- Condition 2 fewshot showed: `<additional_considerations>None — the core estimation captures the primary factors</additional_considerations>` — the model ignored this and produced 4 substantive items
- Condition 3 fewshot showed: `<completeness_check>Analysis is complete. The Fermi estimation covers the primary demand and supply factors.</completeness_check>` — the model partially followed, listing what was covered but then identifying what was NOT covered ("Does not account for piano repair vs tuning specialty")

**The model never says "nothing missing."** Even when given explicit permission and a fewshot demonstrating it, the cooperative pressure to produce content overrides. This supports the pragmatics prediction, though note: it's also possible the model genuinely identifies things that are missing (which there always are in Fermi estimation).

### 2. Content comparison across conditions

| Metric | Presuppositional (`missed`) | Neutral (`additional_considerations`) | Procedural (`completeness_check`) |
|--------|----------------------------|--------------------------------------|----------------------------------|
| Items in self-critical field | 3 | 4 | 1 (but includes missing items) |
| Tone | Deficit-focused ("could add", "may be lower", "reducing capacity") | Balanced ("does not account for", "could increase", "may reduce") | Mixed audit ("covers... does not account for") |
| Institutional pianos mentioned | Yes (first item) | Yes (first item) | Yes (incorporated into reasoning) |
| Format | JSON list | XML bullet list | XML prose |
| Piano ownership rate | 5% (1 in 20) | 2-3% | 3% |
| Final estimate | 90-100 | 40-60 | 120-150 |
| Confidence | 0.35 | 0.35 | 0.25 |

### 3. Does the final answer differ?

**Dramatically.** The three conditions produced wildly different estimates:
- Presuppositional: **90-100** (5% ownership, 3.5 tunings/day)
- Neutral: **40-60** (2.5% ownership, 3.5 tunings/day)
- Procedural: **120-150** (3% ownership, 2.5 tunings/day, added institutional demand)

The procedural condition (`completeness_check`) produced the most thorough analysis — it INTEGRATED institutional demand into the reasoning itself rather than mentioning it as an afterthought. The model separately modeled institutional pianos at 4x tuning frequency, used a lower tuner capacity (2.5/day vs 3.5/day), and added a part-time adjustment. It listed 7 assumptions vs 5 for the other conditions.

### 4. Lexical analysis of the self-critical field

- **Presuppositional** (`missed`): Generic framing — "could add", "may be lower", "reducing available capacity" — items framed as deficits in the analysis
- **Neutral** (`additional_considerations`): More balanced — "does not account for", "could increase demand", "may reduce" — items framed as factors worth noting
- **Procedural** (`completeness_check`): Audit-style — "covers residential demand, institutional demand, tuner productivity" then "does not account for" — framed as a verification report

The presuppositional framing did NOT produce more stock phrases than the neutral framing. Both were specific and contextually relevant. The difference was tonal, not substantive.

### 5. The completeness_check surprise

The procedural framing produced the most analytically rigorous response. When asked to "verify completeness," the model didn't just check a box — it reconsidered the entire analysis and incorporated factors that the other conditions relegated to afterthoughts. The institutional demand that appeared in `<missed>` and `<additional_considerations>` as a side note was integrated into the `<reasoning>` itself in the procedural condition.

**This may be the most important finding:** the field name doesn't just determine what goes IN the field — it determines what goes in the REASONING field too. `<completeness_check>` triggered a more thorough primary analysis because the model anticipated needing to defend its completeness.

### 6. Limitations

Single run per condition. The answer variation (40-150) is partly stochastic — Fermi estimates are inherently variable across runs. Would need N=20+ per condition to separate the effect of field wording from normal run-to-run variation.

## Notes

- Model: claude-haiku-4-5-20251001 (subagent) for all three conditions
- Tools used: 0 per call
- All conditions ~4s duration
- Condition 1 produced JSON despite XML fewshot (same behavior as Exp 1 Condition B)
- Condition 3 (procedural) produced the most thorough analysis, integrating institutional demand into reasoning
