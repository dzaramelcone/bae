# Phase 21: Execution Convention - Context

**Gathered:** 2026-02-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Eval loop only executes code the AI explicitly marks as executable. Illustrative code (examples, pseudocode, explanations) is NOT executed. Convention replaces the current `extract_code()` which runs all python fences indiscriminately.

</domain>

<decisions>
## Implementation Decisions

### Marking convention
- Convention choice is an **open research question** — must be empirically validated
- Test all three candidates equally: fence annotation (`python:exec`), wrapper marker (`<exec>`), and inverse convention (mark examples instead)
- Run evals across **Opus, Sonnet, and Haiku** — convention must work across all Claude tiers
- Eval uses simple, straightforward prompts and fewshot with fake conversation samples — no adversarial testing
- **100% compliance required** under normal conditions — if a convention fails on any model with reasonable prompts, it's rejected
- The winning convention is whatever the evals select

### Multi-block handling
- **One executable block per response** — only the first block marked as executable is extracted and run
- Additional executable blocks are ignored
- AI receives feedback: "Only your first executable block was run. N additional blocks were ignored."
- User also sees a notice that extra blocks were ignored

### Backward compatibility
- **No backward compatibility** — clean break from current `extract_code()` behavior
- Convention applies to **all AI responses**, not just eval loop turns
- No fallback mode for models that don't follow the convention — if convention isn't used, no code executes
- No config toggle — convention is required
- `extract_code()` is **fully replaced** by the new convention-aware extractor
- Entire design is driven by eval results

### Claude's Discretion
- Fallback behavior when AI doesn't use the convention (Claude decides based on eval data whether to run nothing or apply a heuristic)
- Exact eval harness design and prompt scenarios
- How to present the "blocks ignored" notice to the user (channel, styling)

</decisions>

<specifics>
## Specific Ideas

- Evals should use "subagents" dispatched to test conventions — not just Opus
- Fewshot samples in the system prompt showing fake conversation examples of the convention in use
- The eval is the authority — no convention is pre-committed, the winner is determined empirically

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 21-execution-convention*
*Context gathered: 2026-02-14*
