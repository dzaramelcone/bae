# Experiment 5: Two-Phase vs. Single-Pass

Tests whether schema tokens interleaved with reasoning do cognitive work during generation, or whether the same benefit comes from reasoning first and formatting second.

## Task

"A city of 2 million people is considering building a new subway line. The line would cost $4.2 billion, take 7 years to build, and serve an estimated 180,000 daily riders. The current bus system serving the same corridor handles 45,000 daily riders at an operating cost of $3.10 per rider. The projected subway operating cost would be $1.80 per rider. Analyze whether the city should proceed."

---

## Condition 1: Single-Pass Schema

### Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Return ONLY your answer in the schema format, no meta-commentary.

A city of 2 million people is considering building a new subway line. The line would cost $4.2 billion, take 7 years to build, and serve an estimated 180,000 daily riders. The current bus system serving the same corridor handles 45,000 daily riders at an operating cost of $3.10 per rider. The projected subway operating cost would be $1.80 per rider. Analyze whether the city should proceed.

<example>
<question>Should a county build a new bridge costing $800M to replace a ferry service?</question>
<assumptions>
  <assumption claim="Ferry handles 12,000 vehicles/day" risk="low"/>
  <assumption claim="Bridge would handle 35,000 vehicles/day" risk="medium - induced demand is hard to predict"/>
  <assumption claim="Ferry operating cost $15/vehicle, bridge $2/vehicle" risk="medium - bridge maintenance costs escalate"/>
  <assumption claim="Construction takes 5 years" risk="high - infrastructure projects routinely run 30-50% over"/>
</assumptions>
<reasoning>Current ferry cost: 12,000 × $15 × 365 = $65.7M/year. Bridge operating cost at projected volume: 35,000 × $2 × 365 = $25.55M/year. Annual savings: ~$40M. Payback period: $800M / $40M = 20 years. However, construction overruns could push cost to $1.04-1.2B, extending payback to 26-30 years. The bridge also unlocks economic development on both sides.</reasoning>
<confidence>0.45 - the financial case is marginal and highly sensitive to construction cost overruns and demand projections</confidence>
<additional_considerations>Toll revenue could offset costs but faces political resistance. Environmental impact of construction vs reduced ferry emissions. The ferry provides maritime jobs that would be eliminated.</additional_considerations>
<answer>Conditionally yes — proceed only with firm fixed-price construction contracts and guaranteed federal/state cost-sharing of at least 40%.</answer>
</example>

Now answer:
```

### Response (verbatim)

```xml
<question>Should a city of 2 million build a $4.2B subway line taking 7 years, serving 180,000 daily riders?</question>

<assumptions>
  <assumption claim="Subway will serve 180,000 daily riders" risk="high - induced demand projections for new transit are notoriously optimistic; actual ridership often 20-40% below projections"/>
  <assumption claim="Operating cost is $1.80 per rider" risk="medium - initial operating costs often escalate 15-25% in first decade; staffing and maintenance inflation"/>
  <assumption claim="Current bus ridership is 45,000 daily riders" risk="low"/>
  <assumption claim="Bus operating cost is $3.10 per rider" risk="low - verifiable from current budgets"/>
  <assumption claim="7-year construction timeline" risk="high - major subway projects routinely experience 40-80% schedule overruns"/>
  <assumption claim="$4.2B capital cost is firm" risk="high - transit megaprojects typically run 30-60% over budget"/>
</assumptions>

<reasoning>
Current bus system annual cost: 45,000 riders/day × $3.10 × 365 = $51.1M/year

Projected subway operating cost at 180,000 riders: 180,000 × $1.80 × 365 = $118.44M/year

Operating cost difference: The subway costs $67.34M more annually to operate, despite lower per-rider cost. This assumes the bus service is eliminated entirely.

Annual benefit from eliminated bus operating costs: $51.1M
Net annual operating cost increase: $118.44M - $51.1M = $67.34M/year

Capital cost with realistic overruns (assume 45% overrun): $4.2B × 1.45 = $6.09B

Adjusted payback with conservatism (assume 30% ridership shortfall to 126,000 riders, $2.10/rider with inflation):
Annual operating cost: 126,000 × $2.10 × 365 = $96.4M/year
Net annual operating cost increase: $96.4M - $51.1M = $45.3M/year

Payback period: $6.09B / $45.3M = 134 years

7-year construction delay means no revenue for 7 years = additional $317M in deferred benefits

Real discount rate for municipal infrastructure is ~3-4%. At 3% discount over 134-year payback, the net present value is deeply negative unless there are substantial non-ridership benefits.
</reasoning>

<confidence>0.25 - The financial case is severely unfavorable under realistic assumptions. Even best-case scenarios show 60+ year payback periods.</confidence>

<additional_considerations>
- Induced demand effects: Higher ridership might generate economic development, property tax increases, and business revenue that offset operating costs
- Induced demand risk: 180,000 figure may reflect wishful thinking rather than market analysis
- Construction period impact: 7 years of congestion, disruption, and no service benefits
- Network effects: Value depends entirely on whether this integrates with existing transit (if integration is poor, ridership drops 30-50%)
- Opportunity cost: $4.2-6B spent on subway cannot fund 20+ bus rapid transit corridors, which have 10-20 year payback periods
- Climate/congestion benefits: Quantifiable but rarely justified by ridership alone
- Political lock-in: Once built, must operate indefinitely even if unprofitable
</additional_considerations>

<answer>No — do not proceed with the subway as currently planned. Recommend instead: (1) Conduct rigorous demand study with skepticism toward projections, (2) Evaluate Bus Rapid Transit in the corridor with dedicated lanes (payback 12-18 years, $200-400M cost), (3) If ridership projections later prove conservative (160K+ daily validated demand) AND construction costs can be locked at $4B or below, revisit in 3-5 years. The subway becomes viable only with external funding covering 60%+ of capital costs or with demonstrated demand significantly exceeding current projections.</answer>
```

---

## Condition 2: Two-Phase

### Phase 1 Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Think through this problem thoroughly. No formatting requirements.

A city of 2 million people is considering building a new subway line. The line would cost $4.2 billion, take 7 years to build, and serve an estimated 180,000 daily riders. The current bus system serving the same corridor handles 45,000 daily riders at an operating cost of $3.10 per rider. The projected subway operating cost would be $1.80 per rider. Analyze whether the city should proceed.
```

### Phase 1 Response (verbatim)

This is a complex decision that requires balancing multiple factors beyond simple cost-benefit arithmetic. Let me work through the key considerations:

**Financial Analysis:**

The subway would serve 4x the current ridership (180,000 vs 45,000), suggesting substantial latent demand. At the operating level, the subway is more efficient ($1.80 vs $3.10 per rider), which matters for long-term sustainability.

However, the capital cost is enormous. At $4.2 billion with 180,000 daily riders, that's roughly $64,000 per daily rider just in construction costs. To break even on the construction investment through operating savings alone would take decades—likely longer than the system's useful life. Operating cost savings would save roughly $234 million annually (45,000 riders × $1.30/rider difference), meaning just the operating margin wouldn't recover the capital investment for 18 years, before accounting for maintenance, replacement cycles, or the time value of money.

**Questions That Matter More Than the Numbers:**

1. **Is the 180,000 rider projection credible?** This assumes the subway will induce or capture demand. If it's just cannibalizing bus riders, you're spending $4.2B to move people from one vehicle to another. The 4x projection needs strong justification—is this based on comparable transit expansions, or optimistic modeling?

2. **What's the land use impact?** Subways reshape cities. If this line catalyzes dense development along the corridor, property tax increases and economic productivity gains could dwarf the $4.2B investment. Conversely, if the corridor is already built out, this benefit won't materialize.

3. **What about congestion relief?** The 135,000 additional daily riders (if real) represent 135,000 cars potentially off the road. In a 2-million-person city, that's meaningful congestion reduction, air quality improvement, and reduced road maintenance costs. These aren't captured in the operating cost comparison.

4. **What are the alternatives?** Could bus rapid transit (dedicated lanes, signal priority) achieve 60% of the ridership at 10% of the cost? Could congestion pricing or parking reform shift demand without capital investment?

5. **What's the time horizon?** If this is a 50-year asset, the 7-year construction delay matters less. If the city faces fiscal constraints or demographic decline, the long-term ridership could be overestimated.

6. **Who bears the risk?** If the city's growth projections are wrong and the line carries 80,000 riders instead of 180,000, the investment becomes catastrophic. What's the downside scenario?

**The Recommendation Framework:**

The city should proceed **only if**:
- The 180,000 rider projection is based on rigorous demand modeling (not optimism bias)
- Development opportunities along the corridor are real and can be captured
- The broader congestion/environmental/land-use benefits are quantified and material
- Alternative transit improvements have been seriously evaluated and rejected
- The city has stable funding and won't face maintenance crises in 15-20 years

The city should **not proceed if**:
- The projection relies on hope rather than comparable precedent
- The corridor is already built out with no development potential
- A $300M bus rapid transit alternative could capture 70% of the benefit
- The city's finances are precarious or population is declining

In reality, most cities that build subways do so with a mix of these factors—some strong, some weak. The financial numbers alone almost never justify it; the decision is usually about whether the city can afford to be the kind of place that has a subway network, and whether that identity is worth the cost.

### Phase 2 Prompt (verbatim)

```
DO NOT use any tools. Answer directly. Return ONLY your answer in the schema format, no meta-commentary.

Organize the following analysis into the schema below. Extract and restructure ONLY — do not add new analysis or new considerations.

---

ANALYSIS TO RESTRUCTURE:

[Phase 1 response inserted verbatim]

---

SCHEMA:

<assumptions>
  <assumption claim="..." risk="low|medium|high - explanation"/>
</assumptions>
<reasoning>...</reasoning>
<confidence>0.X - explanation</confidence>
<additional_considerations>...</additional_considerations>
<answer>...</answer>
```

### Phase 2 Response (verbatim)

```xml
<assumptions>
  <assumption claim="180,000 daily riders projection is achievable" risk="high - depends on demand modeling credibility and whether growth is induced vs. cannibalized from buses"/>
  <assumption claim="$4.2B capital cost estimate is accurate" risk="medium - transit projects frequently experience cost overruns"/>
  <assumption claim="Operating cost savings of $1.30/rider are sustainable" risk="medium - maintenance and replacement cycles not fully accounted for"/>
  <assumption claim="Subway construction takes 7 years with no major delays" risk="medium - major infrastructure projects commonly experience timeline slippage"/>
  <assumption claim="Comparable ridership and cost data from other transit systems applies" risk="medium - local geography, density, and demand patterns vary significantly"/>
</assumptions>

<reasoning>
The financial arithmetic shows the subway cannot recover its $4.2B capital investment through operating margin alone within a reasonable timeframe (18+ years). However, the decision framework reveals that cost-benefit analysis is insufficient without addressing: (1) demand model credibility—whether 180,000 riders represents real demand or optimistic projection; (2) land use catalysis—whether the corridor can support dense development that generates tax revenue and economic gains exceeding construction costs; (3) congestion and environmental externalities—135,000 vehicles removed from roads annually have value beyond operating cost comparisons; (4) alternative solutions—whether bus rapid transit or demand management could achieve comparable benefits at lower cost; (5) city fiscal health and long-term sustainability of maintenance obligations; and (6) downside risk scenarios if projections miss significantly.

The recommendation framework clarifies that proceed/no-proceed depends on satisfying multiple conjunctive conditions rather than any single financial metric.
</reasoning>

<confidence>
0.8 - The framework correctly identifies the key decision factors and appropriate risk assessment, though the specific numerical thresholds (e.g., "18 years to break even") are dependent on input accuracy that cannot be verified without access to the underlying demand models and cost estimates.
</confidence>

<additional_considerations>
The analysis correctly reframes the decision from "does operating margin justify capital cost" to "is this the kind of city we want to be and can we afford it." This shifts focus from sunk cost fallacy to strategic city identity and opportunity cost of $4.2B deployed elsewhere. The downside scenario risk (80,000 riders vs. 180,000) is material and often underweighted in municipal decisions.
</additional_considerations>

<answer>
Proceed only if: (1) 180,000 rider projection is rigorous, not optimistic; (2) development opportunities along corridor are real and capturable; (3) congestion/environmental/land-use benefits are quantified and material; (4) alternatives (BRT, demand management) have been seriously evaluated and rejected; (5) city finances are stable for 15-20 year maintenance horizon.

Do not proceed if: (1) projection relies on hope rather than precedent; (2) corridor is already built out; (3) a $300M BRT alternative captures 70% of benefit; (4) city finances are precarious or population is declining.

The decision hinges on demand model credibility, development capacity, externality quantification, and fiscal sustainability—not on the operating cost spread alone.
</answer>
```

---

## Analysis

### 1. Does Phase 1 free reasoning produce different analysis than single-pass schema?

**Yes, substantially different.** The free reasoning (Phase 1) and the single-pass schema produced markedly different analytical approaches:

- **Single-pass schema** performed quantitative stress-testing: calculated actual costs ($51.1M/year bus vs $118.44M/year subway), applied realistic overruns (45% → $6.09B), modeled ridership shortfall (30% → 126,000), computed payback (134 years), and applied discount rates. It reached a clear **"No"** with confidence 0.25.

- **Free reasoning** took a qualitative-strategic approach: framed it as "questions that matter more than the numbers," discussed land use impacts, city identity, network effects, and produced a conditional framework rather than a definitive answer. Its one quantitative calculation ($234M annual savings, 18-year payback) used a different methodology — it computed savings per rider rather than total system cost differential.

### 2. Does two-phase recover information lost to formatting overhead?

**No — the opposite happened.** The free reasoning produced *less* quantitative rigor, not more. It didn't compute total subway operating cost, didn't model overruns, didn't apply discount rates. The single-pass schema's structure forced more rigorous computation. The schema fields — particularly `<assumptions>` with explicit risk ratings — triggered the model to stress-test its own numbers in ways the free generation did not.

### 3. Does single-pass schema surface considerations free reasoning missed?

**Yes:**
- Single-pass uniquely surfaced: realistic cost overrun modeling (45%), ridership shortfall sensitivity (30%), NPV analysis with discount rate, opportunity cost quantified as "20+ BRT corridors," political lock-in risk
- Free reasoning uniquely surfaced: city identity framing ("whether the city can afford to be the kind of place that has a subway"), land use catalysis as potentially dwarfing construction cost, the deeper question of what the 4x ridership projection actually means

Different kinds of thinking, but the schema forced *more disciplined* analysis.

### 4. Phase 2 restructuring: what happened?

**Information was lost, not recovered.** Phase 2 compressed the free reasoning into the schema but:
- Lost the specific numerical calculations entirely (the $234M/year figure, the 18-year payback)
- Lost the "city identity" framing — the most original insight from Phase 1
- Assigned confidence 0.8 (!) to what was originally a deeply uncertain analysis — the restructuring model treated the Phase 1 output as authoritative rather than exploratory
- The `<additional_considerations>` field became meta-commentary about the analysis rather than additional substantive considerations

### 5. Key finding

**Single-pass wins decisively.** The schema tokens ARE doing cognitive work during generation. Specifically:

- The `<assumptions>` field with risk ratings triggered quantitative stress-testing that free reasoning skipped
- The `<confidence>` field in single-pass produced 0.25 (appropriately low and well-calibrated) while the Phase 2 restructuring produced 0.80 (inappropriately high — the restructuring model confused "the analysis is well-organized" with "the conclusion is confident")
- The `<additional_considerations>` field in single-pass produced 7 specific substantive items; in Phase 2 it produced abstract meta-commentary
- The single-pass answer was more actionable (specific recommendations with quantified thresholds)

**This supports the autoregressive conditioning theory:** schema field names are not just containers filled after thinking — they alter the thinking itself. When `<assumptions>` with risk ratings appears in the generation stream, it changes what the model computes next. The two-phase approach loses this because the reasoning has already been generated before the schema tokens enter the context.

**However**, the free reasoning produced one insight the schema did not: the "city identity" framing. This suggests schemas may narrow as well as deepen — they focus computation on the fields provided, potentially at the cost of more creative or lateral thinking.

## Notes

- Model: claude-haiku-4-5-20251001 (subagent) for all three calls
- Tools used: 0 per call
- Condition 1 duration: ~11s
- Condition 2 Phase 1 duration: ~15s
- Condition 2 Phase 2 duration: ~9s
