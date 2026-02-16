# Condition 3: Sonnet — Schema with Evaluative Fields (no tools)

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
  <assumption claim="Average household size ~2.5 people" risk="low"/>
  <assumption claim="~80% of households own a piano" risk="high - likely much lower, maybe 2-5%"/>
  <assumption claim="Piano tuned once per year" risk="medium - enthusiasts tune more, casual owners less"/>
  <assumption claim="Piano tuner services 4 pianos per day" risk="medium - includes travel time"/>
  <assumption claim="Piano tuner works 250 days/year" risk="low"/>
</assumptions>

<reasoning>
2.7M people / 2.5 people per household = ~1.1M households.
Assuming 3% piano ownership (between casual and enthusiast): 1.1M × 0.03 = 33,000 pianos.
33,000 pianos tuned 1x/year = 33,000 tunings/year.
Tuner capacity: 4 pianos/day × 250 days = 1,000 tunings/year.
33,000 tunings / 1,000 per tuner = 33 tuners.

Alternative check with 5% ownership: 55,000 pianos → 55 tuners.
Alternative check with 2% ownership: 22,000 pianos → 22 tuners.
</reasoning>

<confidence>0.3 - piano ownership rate is the dominant uncertainty</confidence>

<missed>Commercial pianos (schools, churches, concert halls, studios) could significantly increase the total. Professional venues tune much more frequently (monthly or weekly).</missed>

<answer>~30-50 piano tuners</answer>

## Notes

- Model: claude-sonnet-4-5-20250929 (subagent)
- Tools available: yes (but instructed not to use)
- Tools used: 0
- Duration: ~10.2s
- Wrote 80% ownership, immediately flagged as "high" risk, self-corrected to 3%
- Ran alternative checks at 2% and 5% — sensitivity analysis unprompted
