# Experiment 4: Expertise Reversal Across Model Scale

Tests the cognitive science prediction: schemas help weak models but hurt strong ones (expertise reversal effect, Kalyuga 2007).

## Design

- **Easy task**: "What is 15% of 340?" (deterministic, no ambiguity)
- **Hard task**: Hospital bed renovation analysis (multi-step, requires tradeoff reasoning)
- **3 models**: Haiku (weak), Sonnet (mid), Opus (strong)
- **2 conditions**: Free generation vs. schema with fewshot
- **12 total runs**

---

## Easy Task: "What is 15% of 340?"

**Correct answer: 51**

### Haiku Free

```
15% of 340 = 0.15 × 340 = 51

Here's the calculation:
- 10% of 340 = 34
- 5% of 340 = 17
- 15% of 340 = 34 + 17 = **51**
```

### Haiku Schema

```xml
<assumptions>
  <assumption claim="Standard percentage calculation" risk="low"/>
</assumptions>
<reasoning>15% of 340 = 0.15 × 340 = 51</reasoning>
<confidence>0.99</confidence>
<additional_considerations>None</additional_considerations>
<answer>51</answer>
```

### Sonnet Free

```
Let me calculate 15% of 340.

15% of 340 = 0.15 × 340 = 51

So 15% of 340 is **51**.
```

### Sonnet Schema

```xml
<assumptions>
  <assumption claim="Standard percentage calculation" risk="low"/>
</assumptions>
<reasoning>15% of 340 = 0.15 × 340 = 51</reasoning>
<confidence>0.99</confidence>
<additional_considerations>None</additional_considerations>
<answer>51</answer>
```

### Opus Free

```
340 × 0.15 = 51
```

### Opus Schema

```xml
<assumptions>
  <assumption claim="Standard percentage calculation" risk="low"/>
</assumptions>
<reasoning>15% of 340 = 0.15 × 340 = 51</reasoning>
<confidence>0.99</confidence>
<additional_considerations>None</additional_considerations>
<answer>51</answer>
```

### Easy Task Analysis

| Model | Free | Schema | Schema overhead |
|-------|------|--------|----------------|
| Haiku | Correct, 2 methods shown | Correct, minimal | Schema added ~60 tokens of boilerplate for zero benefit |
| Sonnet | Correct, brief | Correct, identical to Haiku schema | Same overhead |
| Opus | Correct, 6 words | Correct, identical to Haiku/Sonnet schema | Most overhead relative to free (6 words → ~50 tokens) |

**Finding**: All models answered correctly in both conditions. The schema added pure overhead on the easy task. Notably:
- Opus free was maximally efficient (6 words)
- All three schema responses were nearly identical — the schema homogenized output
- All models correctly used `additional_considerations: None`, following the fewshot's permission to leave it empty
- **No model was hurt by the schema**, but none were helped either

---

## Hard Task: Hospital Bed Renovation

**Task**: 500 beds, 82% occupancy, $2400/day revenue, $1850/day operating cost per occupied bed, $200/day overhead per empty bed. $12M renovation adds 80 beds but closes 40 for 6 months. Should they proceed?

**Key correct calculations**: Daily profit current = ~$207,500. Post-renovation daily profit = ~$241,000. Construction period loss = ~$3M. Total cost ~$15M. Payback ~1.2 years.

### Haiku Free

Performed complete multi-step analysis:
- Current state: $207,500/day profit ✓
- Construction period: $190,750/day ✓
- Post-renovation: $241,000/day (used 241,200 — slight rounding diff) ✓
- Construction loss: $3,056,875 ✓
- Total cost: $15,056,875 ✓
- Payback: 1.23 years ✓
- 5-year NPV at 8%: $33.8M
- ROI: 306%
- **Recommendation: YES**
- Risks identified: 4 (occupancy, operational scaling, timeline, financing)

### Haiku Schema

```xml
<assumptions>
  7 assumptions listed, all with risk ratings
  Notably: "New 80 beds will achieve 82% occupancy rate immediately" — risk="high"
</assumptions>
<reasoning>
  Current: $207,500/day ✓
  Construction: $190,750/day (slight rounding) ✓
  Post-renovation: $241,000/day ✓
  Total cost: $15,015,000 ✓
  Payback: 1.23 years ✓
</reasoning>
<confidence>0.62 - mathematically attractive payback, but high execution risk and occupancy assumptions</confidence>
<additional_considerations>
  5 items: debt servicing, market saturation, working capital disruption, alternative capital use, competitive response
</additional_considerations>
<answer>Conditionally yes — with 3 specific conditions and phased approach suggestion</answer>
```

### Sonnet Free

Performed complete analysis:
- Current: $207,500/day ✓
- Construction: $190,750/day ✓
- Post-renovation: $241,000/day ✓
- Construction loss: $3,065,250 ✓
- Total cost: $15,065,250 ✓
- Payback: 1.23 years ✓
- Sensitivity: "even at 75% occupancy, payback within 2.5 years"
- **Recommendation: YES**
- Risks: 4 (market, construction delays, budget, non-financial)

### Sonnet Schema

```xml
<assumptions>
  5 assumptions with risk ratings
  "Renovation takes 6 months, on budget at $12M" — risk="high"
</assumptions>
<reasoning>
  Current: $207,500/day ✓
  Construction: $190,750/day ✓
  Post-renovation: $241,000/day ✓
  Total cost: $15.06M ✓
  Payback: 1.23 years ✓
  BONUS: Ran sensitivity at 70% occupancy on new beds only → payback 1.6 years
</reasoning>
<confidence>0.82 - strong financial case; main risks are construction overruns and occupancy ramp-up</confidence>
<additional_considerations>
  Sensitivity analysis (cost doubles + occupancy drops → still 2.8yr payback), staffing, regulatory, phased construction
</additional_considerations>
<answer>Yes, proceed. Recommend GMP contract, staffing pipeline confirmation, regional demand validation.</answer>
```

### Opus Free

Performed complete analysis:
- Current: $207,500/day ✓
- Construction: $190,750/day ✓
- Post-renovation: $241,000/day ✓
- Construction loss: $3,065,250 ✓
- Total cost: $15,065,250 ✓
- Payback: 1.23 years ✓
- Annual profit increase: $12,227,500 ✓
- Showed moment of self-correction: "500 - 40 + 80 = ... wait, the 40 beds reopen after construction. 500 + 80 = 580 beds"
- **Recommendation: YES**
- Sensitivity: "Even at 75% occupancy, payback under 2.5 years"

### Opus Schema

```xml
<assumptions>
  5 assumptions with risk ratings
  "Renovation takes 6 months, on budget at $12M" — risk="high"
</assumptions>
<reasoning>
  Current: $207,500/day ✓
  Construction: $190,750/day ✓
  Post-renovation: $241,000/day ✓
  Total cost: $15.06M ✓
  Payback: 1.23 years ✓
  Sensitivity at 70% on new beds: payback 1.6 years
  BONUS: "even if renovation costs double to $24M and occupancy drops to 70%, payback ~2.8 years — still compelling"
</reasoning>
<confidence>0.82</confidence>
<additional_considerations>
  Staffing pipeline, regional demand validation, phased construction, GMP contract
</additional_considerations>
<answer>Yes, proceed. Payback 1.2 years, survives aggressive downside scenarios.</answer>
```

---

## Expertise Reversal Analysis

### Easy Task: Schema Effect by Model

| Model | Free quality | Schema quality | Schema effect |
|-------|-------------|----------------|---------------|
| Haiku | Good (showed 2 methods) | Correct but boilerplate | Neutral (pure overhead) |
| Sonnet | Good (brief, clear) | Correct but boilerplate | Neutral (pure overhead) |
| Opus | Excellent (6 words, maximally efficient) | Correct but boilerplate | **Slight negative** (forced 50+ tokens for a 6-word answer) |

On the easy task, the schema was overhead for ALL models. Opus was hurt most (relatively) — forced from maximally efficient (6 words) to boilerplate. This weakly supports the expertise reversal prediction: the strongest model had the most to lose from unnecessary structure.

### Hard Task: Schema Effect by Model

| Model | Free: Risks identified | Schema: Risks identified | Free: Sensitivity analysis | Schema: Sensitivity analysis | Free: Conditional answer | Schema: Conditional answer |
|-------|----------------------|--------------------------|---------------------------|------------------------------|-------------------------|---------------------------|
| Haiku | 4 generic | 5 specific + debt servicing, competitive response | None explicit | None explicit | No (flat "yes") | Yes (3 conditions + phased approach) |
| Sonnet | 4 generic | Aggressive double-downside scenario | Mentioned (75% → 2.5yr) | Full sensitivity (cost 2x + occupancy drop → 2.8yr) | No (flat "yes, but") | Yes (3 specific conditions) |
| Opus | 4 generic + self-correction moment | Full sensitivity (70% new + cost 2x → 2.8yr) | Mentioned (75% → 2.5yr) | Included in reasoning | No (flat "yes") | Yes (specific conditions + GMP) |

### The Crossover Test

**Did schemas help Haiku more than Opus on the hard task?**

**Yes, substantially.** Haiku's improvement was the largest:
- **Haiku free** → **Haiku schema**: Went from a flat "YES" with generic risks to a conditional recommendation with 5 specific risk factors, debt servicing analysis, competitive response concerns, and a phased approach suggestion. The confidence dropped from implicit certainty to 0.62 — more appropriately calibrated. This is a qualitative transformation.
- **Opus free** → **Opus schema**: Both were already strong. Free Opus showed a self-correction moment ("wait, the 40 beds reopen") that the schema version didn't need. Schema added sensitivity analysis that free also partially did. The improvement was incremental, not transformative. Confidence of 0.82 in both schema conditions (Sonnet and Opus) suggests they converged.

**Did the schema hurt Opus on the easy task?**

**Weakly yes.** Opus free produced `340 × 0.15 = 51` (6 words, maximally efficient). The schema forced it to generate ~50 tokens of boilerplate for zero analytical benefit. This is the expertise reversal effect at its mildest — not degradation of reasoning, but wasted compute.

### Is there a crossover interaction?

**Yes — the predicted pattern holds:**

```
                Easy Task          Hard Task
Haiku:    Neutral effect     → Large positive effect
Sonnet:   Neutral effect     → Moderate positive effect
Opus:     Slight negative    → Small positive effect
```

The schema benefit is inversely proportional to model capability on the hard task:
- Haiku: transformed (generic → conditional, calibrated, specific)
- Sonnet: enhanced (added aggressive sensitivity analysis)
- Opus: marginal (already doing most of what the schema elicits)

The expertise reversal effect is **confirmed directionally** but not dramatically — even Opus benefited slightly from the schema on the hard task (more structured sensitivity analysis). The strong form of the prediction (schemas HURT strong models on hard tasks) was not observed. The effect is more accurately described as **diminishing returns** than reversal.

## Implications for Schema Design

1. **Principle 3 from the synthesis is supported**: Scale structure to task difficulty, inversely to model capability
2. The effect is gradual, not a cliff — schemas don't break strong models, they just waste their time on easy tasks
3. The confidence scores across models are revealing:
   - Haiku schema: 0.62 (appropriately uncertain)
   - Sonnet schema: 0.82 (confident but flagging risks)
   - Opus schema: 0.82 (identical to Sonnet — convergence at the schema level)
4. Schemas homogenize output across model tiers — the three schema responses on the hard task were more similar to each other than the three free responses

## Notes

- Models: claude-haiku-4-5-20251001, claude-sonnet-4-5-20250929, claude-opus-4-6
- Tools used: 0 per call
- Haiku easy: ~1-2s per condition
- Haiku hard: ~8-10s per condition
- Sonnet hard: ~15-19s per condition
- Opus hard: ~16-20s per condition
- All 12 runs produced correct core calculations ($207,500 current, $241,000 post-renovation, ~1.23yr payback)
