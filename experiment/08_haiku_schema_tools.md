# Condition 8: Haiku — Schema with Evaluative Fields + Tools

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
  <assumption claim="Chicago population ~2.7 million (metropolitan area ~9 million)" risk="low"/>
  <assumption claim="Piano ownership in Chicago ~3-5% of households" risk="medium"/>
  <assumption claim="Pianos need tuning 2-4 times per year on average" risk="medium"/>
  <assumption claim="Each piano tuner works ~1000-1200 hours/year on tuning" risk="medium"/>
</assumptions>

<contemporaneous_research>
  <finding claim="58 Registered Piano Technicians (RPTs) in Chicago chapter (44) + North Shore (14) in 2009" source="Wolfram Alpha Blog" verified="true"/>
  <finding claim="73 piano tuners listed in Chicago area directories" source="Chicago Consumers' Checkbook" verified="true"/>
  <finding claim="30-40 piano tuners actively working in Chicago area per online directories" source="Web search results" verified="true"/>
  <finding claim="One estimation model yields ~290 piano tuners" source="Web search results" verified="true"/>
  <finding claim="Chicago has 2.3x the national average workforce fraction for musical instrument tuners/repairers" source="Web search results" verified="true"/>
</contemporaneous_research>

<reasoning>
The classic "piano tuners in Chicago" is a famous Fermi estimation problem used in case interviews and physics education. The data shows wide variance depending on methodology:

- Registered Piano Technicians (RPTs): 58 in 2009 — this is a lower bound since RPT certification requires passing exams and paying annual dues
- Directory listings: 30-73 piano tuners currently listed
- Fermi estimates: ~120-290 range
- The discrepancy reflects: (1) who counts as a "piano tuner" (certified vs. casual), (2) how directories capture informal workers, (3) data age

The most defensible numbers are the directory counts (30-73) for currently active practitioners, with 58 RPTs as a verified lower bound for formally trained technicians.
</reasoning>

<confidence>0.5 - mixed data quality: directory counts are contemporaneous but potentially incomplete; RPT data is older (2009); Fermi estimates are methodologically sound but assumptions vary</confidence>

<missed>
- Part-time piano tuners not captured in professional registries
- Pianos tuned by repair shops as secondary service (not primary business)
- Recent data (post-2015) for total practicing piano tuners
- Distinction between "piano tuner" vs. "piano technician" with broader repair skills
</missed>

<answer>
The number of piano tuners in Chicago ranges widely depending on how you count:
- **30-40** actively listed in online directories (most conservative current count)
- **58** Registered Piano Technicians (RPTs) confirmed in 2009 (lower bound for formally certified)
- **73** listed in Chicago Consumers' Checkbook directory
- **120-290** range from Fermi estimation models (depends on assumptions)

The most reliable contemporaneous answer is **~50-75 active piano tuners** based on directory and registry data, though true informal practitioners may extend this to 100+.
</answer>

---

Sources:
- [How Many Piano Tuners Are There in Chicago?—Wolfram|Alpha Blog](https://blog.wolframalpha.com/2010/09/28/how-many-piano-tuners-are-there-in-chicago/)
- [Piano Tuners - Ratings and Reviews - Chicago Consumers' Checkbook](https://www.checkbook.org/chicago-area/piano-tuners/)
- [How Many Piano Tuners Are There In Chicago – Mozart Project](https://www.mozartproject.org/how-many-piano-tuners-are-there-in-chicago-2/)
- [Estimating the Number of Piano Tuners in Chicago | Jobaaj Learning Casestudies](https://www.jobaajlearnings.com/casestudies/Estimating-the-Number-of-Piano-Tuners-in-Chicago)

## Notes

- Model: claude-haiku-4-5-20251001 (subagent)
- Tools available: yes (and encouraged)
- Tools used: 2 (WebSearch)
- Duration: ~16.9s
- Found Piano Technicians Guild registry data (58 RPTs)
- Found Chicago Consumers' Checkbook directory listing (73)
- Used real data to calibrate and reality-check Fermi estimate
- Distinguished between certified professionals and total practitioners
