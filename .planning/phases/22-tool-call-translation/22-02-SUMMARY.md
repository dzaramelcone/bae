---
phase: 22-tool-call-translation
plan: 02
subsystem: repl
tags: [eval-loop, tool-calls, system-prompt, async-exec]

# Dependency graph
requires:
  - phase: 22-tool-call-translation
    plan: 01
    provides: "translate_tool_calls() pure function: text -> list[str] of Python code"
provides:
  - "Eval loop tool call translation: detect -> translate -> execute -> feed back"
  - "System prompt tool tag vocabulary with reference table and fewshot examples"
  - "tool_translated/tool_result metadata types on [py] channel"
affects: [ai-streaming, future-tool-types]

# Tech tracking
tech-stack:
  added: []
  patterns: ["tool call branch before run-block branch in eval loop", "combined multi-tool output with --- separator"]

key-files:
  created: []
  modified:
    - bae/repl/ai.py
    - bae/repl/ai_prompt.md
    - tests/repl/test_ai.py

key-decisions:
  - "Tool tags take precedence over <run> blocks when both present in a response"
  - "All tool calls in a batch share one eval loop iteration and one feedback round"
  - "tool_translated/tool_result metadata types distinguish tool calls from ai_exec/ai_exec_result"

patterns-established:
  - "Eval loop priority: translate_tool_calls() checked first, extract_executable() second"
  - "Multi-tool output: execute all independently, combine with --- separator, single _send() feedback"

# Metrics
duration: 3min
completed: 2026-02-14
---

# Phase 22 Plan 02: Eval Loop Integration Summary

**Tool call translation wired into eval loop with system prompt vocabulary teaching all 5 terse tag formats**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-14T18:11:06Z
- **Completed:** 2026-02-14T18:13:46Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Eval loop checks translate_tool_calls() before extract_executable() on every iteration
- ALL tool tags in a response are translated and executed independently via async_exec
- Outputs combined with --- separator into single [Tool output] feedback to AI
- System prompt teaches AI all 5 tool tag formats (R, W, E, G, Grep) with reference table
- 3 fewshot examples demonstrate read, glob, and grep usage
- 8 new tests (7 eval loop + 1 prompt), 61/61 test_ai.py green, 268/268 repl suite green

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire translate_tool_calls into eval loop** - `e707c21` (feat)
2. **Task 2: Add tool tag vocabulary to system prompt** - `fa75679` (feat)

## Files Created/Modified
- `bae/repl/ai.py` - Tool call translation branch in eval loop before run-block branch
- `bae/repl/ai_prompt.md` - File and search tools section with reference table + 3 fewshot examples
- `tests/repl/test_ai.py` - TestEvalLoopToolCalls (7 tests) + test_prompt_mentions_tool_tags

## Decisions Made
- **Tool tag precedence:** When a response contains both tool tags and `<run>` blocks, tool tags take precedence and the run block is not executed. This prevents ambiguity.
- **Batch-per-iteration:** All tool calls in a single response share one loop iteration and one feedback round (combined output). This keeps the iteration counter simple and matches the plan's "one iteration per batch" requirement.
- **Distinct metadata types:** tool_translated/tool_result are separate from ai_exec/ai_exec_result, allowing downstream consumers (channels, store) to distinguish tool call execution from run-block execution.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Tool call translation pipeline complete: detection (Plan 01) -> eval loop execution (Plan 02)
- AI learns tag syntax via prompt, eval loop translates and executes transparently
- Phase 22 fully complete, ready for next phase

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 22-tool-call-translation*
*Completed: 2026-02-14*
