# Condition 4: Sonnet — Schema with Evaluative Fields + Tools

## Prompt (verbatim)

```
Answer the following question using the provided schema. You have access to WebSearch — use it when a field requires grounded evidence. Return ONLY your answer in the schema format, no meta-commentary.

How many piano tuners are in Chicago?

<example>
<question>How many dentists are in London?</question>
<assumptions>
  <assumption claim="London population ~9M" risk="low"/>
  <assumption claim="Average person visits dentist 2x/year" risk="medium - varies by culture"/>
  <assumption claim="A dentist sees 8 patients/day" risk="medium - depends on procedure type"/>
</assumptions>
<contemporaneous_research>
  <finding claim="NHS reports ~29,000 dentists in England, ~6,000 in London" source="NHS Digital Workforce Statistics 2023" verified="true"/>
</contemporaneous_research>
<reasoning>Fermi estimate gave ~9,000 but NHS data shows ~6,000. The discrepancy reveals that visit frequency assumption was too high — many people skip dental visits entirely.</reasoning>
<confidence>0.7 - grounded in official data</confidence>
<missed>Private-only dentists not captured in NHS data</missed>
<answer>~6,000 dentists in London (data-grounded), Fermi estimate was ~9,000</answer>
</example>

Now answer:
```

## Response (verbatim)

<assumptions>
  <assumption claim="Chicago city population ~2.7M" risk="low - grounded in census data"/>
  <assumption claim="10-28% of households own a piano" risk="medium - wide range in sources, using conservative 10%"/>
  <assumption claim="Average household size ~2.5 people" risk="low - typical for US cities"/>
  <assumption claim="Pianos tuned 1-2x/year on average" risk="medium - varies by usage"/>
  <assumption claim="Piano tuner tunes 800-1200 pianos/year" risk="medium - depends on full-time vs part-time"/>
</assumptions>

<contemporaneous_research>
  <finding claim="Chicago city population 2,721,308 in 2026" source="World Population Review 2026" verified="true"/>
  <finding claim="28% of US households own a piano or keyboard instrument" source="Piano industry statistics" verified="true"/>
  <finding claim="Conservative estimate: 10% of households own acoustic pianos" source="Piano World forums discussion" verified="partial - anecdotal"/>
  <finding claim="Piano tuner can service 800-1200 pianos/year" source="Brainly educational resources, Indeed career data" verified="true"/>
</contemporaneous_research>

<reasoning>
Fermi calculation:
- Chicago households: 2,721,308 / 2.5 = ~1,088,000 households
- Pianos (conservative 10%): 1,088,000 × 0.10 = ~108,800 pianos
- Pianos (optimistic 28%): 1,088,000 × 0.28 = ~304,640 pianos
- Average tunings/piano/year: 1.5
- Total tunings needed (conservative): 108,800 × 1.5 = 163,200
- Total tunings needed (optimistic): 304,640 × 1.5 = 456,960
- Tunings per tuner/year: 1,000 (middle estimate)
- **Conservative estimate: 163,200 / 1,000 = ~163 tuners**
- **Optimistic estimate: 456,960 / 1,000 = ~457 tuners**
- **Middle estimate using 15%: (1,088,000 × 0.15 × 1.5) / 1,000 = ~245 tuners**
</reasoning>

<confidence>0.6 - Fermi-based with grounded population data but uncertain piano ownership percentage</confidence>

<missed>
- Institutional pianos (schools, churches, concert halls) which tune more frequently
- Digital piano prevalence reducing acoustic piano ownership
- Part-time vs full-time tuner ratio
- Tuners who also do repair work (fewer tunings/year)
</missed>

<answer>~150-250 piano tuners in Chicago. Middle Fermi estimate: 245 tuners. This assumes Chicago's 2.7M population creates ~1.1M households, 10-15% own acoustic pianos, each tuned 1.5x/year, and each tuner services ~1,000 pianos annually.</answer>

**Sources:**
- [Chicago Population 2026](https://worldpopulationreview.com/us-cities/illinois/chicago)
- [Piano Ownership Statistics](https://keynoteauthority.com/learning/30-fascinating-piano-statistics-numbers-facts/)
- [Piano Tuner Workload Analysis](https://brainly.com/question/51855256)
- [Piano Tuner Career Data](https://www.indeed.com/career-advice/pay-salary/how-much-do-piano-tuners-make)

## Notes

- Model: claude-sonnet-4-5-20250929 (subagent)
- Tools available: yes (and encouraged)
- Tools used: 3 (WebSearch)
- Duration: ~31.6s
- Searched for grounding data but did NOT find the Piano Technicians Guild registry data that Haiku found
- Used piano ownership statistics to refine Fermi estimate but stayed in estimation mode rather than finding actual counts
