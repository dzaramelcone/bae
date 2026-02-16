# Condition 7: Haiku — Schema with Evaluative Fields (no tools)

## Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Return ONLY your answer, no meta-commentary.

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

## Response (verbatim)

<assumptions>
  <assumption claim="Chicago population ~2.7M" risk="low"/>
  <assumption claim="Piano ownership rate ~2-3% of households" risk="medium - varies by socioeconomic status and cultural factors"/>
  <assumption claim="Average piano tuned 1-2 times per year" risk="medium - depends on use intensity"/>
  <assumption claim="A piano tuner completes 3-4 pianos per day" risk="medium - varies by piano condition and travel time"/>
  <assumption claim="Piano tuners work ~250 days/year" risk="low"/>
</assumptions>

<reasoning>
Chicago households: ~2.7M / 2.5 people per household ≈ 1.1M households
Pianos in Chicago: 1.1M × 2.5% ≈ 27,500 pianos
Annual tuning demand: 27,500 × 1.5 ≈ 41,250 tunings/year
Tuner capacity: 3.5 pianos/day × 250 days ≈ 875 tunings/tuner/year
Piano tuners needed: 41,250 / 875 ≈ 47 piano tuners
</reasoning>

<confidence>0.25 - piano ownership rate is highly speculative, and professional piano tuner density in major cities varies significantly based on music culture and economic factors</confidence>

<missed>
- Chicago's music culture (symphony orchestras, conservatories, studios) could significantly increase piano density
- Commercial/institutional pianos (concert halls, schools, studios) add substantial demand beyond residential
- Piano tuner specialization varies (some do repairs, restoration, or focus on specific piano types)
- Regional economics could concentrate tuners in specific neighborhoods
</missed>

<answer>~45-70 piano tuners, with higher probability toward the lower end if residential-only; potentially 100+ if institutional demand is significant</answer>

## Notes

- Model: claude-haiku-4-5-20251001 (subagent)
- Tools available: yes (but instructed not to use)
- Tools used: 0
- Duration: ~5.1s
- Confidence 0.25 — lowest self-assessed confidence across all conditions
- <missed> section surfaced 4 considerations not present in CoT condition
