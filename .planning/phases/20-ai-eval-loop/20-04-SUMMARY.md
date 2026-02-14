---
phase: 20-ai-eval-loop
plan: 04
subsystem: repl
tags: [asyncio, coroutines, prompt-engineering, ai-eval-loop]

# Dependency graph
requires:
  - phase: 20-03
    provides: "AI eval loop with code extraction and feedback"
provides:
  - "Safe PY dispatch for coroutine collections (no crash on unawaited coroutines)"
  - "AI system prompt that defaults to NL answers, code only for inspection/computation"
affects: [20-05, ai-eval-loop, repl]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Recursive collection traversal with id-based cycle detection for coroutine safety"
    - "Coroutine cleanup via .close() to prevent RuntimeWarning on GC"

key-files:
  created: []
  modified:
    - bae/repl/shell.py
    - bae/repl/ai_prompt.md
    - tests/repl/test_exec.py

key-decisions:
  - "Close unawaited coroutines via .close() rather than letting them GC (prevents RuntimeWarning)"
  - "Pop namespace['_'] when coroutine collection detected to prevent stale references"
  - "AI prompt defaults to NL answers with explicit 'When to write code' criteria"

patterns-established:
  - "Coroutine collection guard: _contains_coroutines() before repr() on any PY result"

# Metrics
duration: 3min
completed: 2026-02-14
---

# Phase 20 Plan 04: Gap Closure Summary

**Safe coroutine collection handling in PY dispatch + AI prompt rewrite to stop runaway code generation loops**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-14T13:29:50Z
- **Completed:** 2026-02-14T13:33:17Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- PY mode gracefully handles unawaited coroutine collections with warning message and cleanup
- AI system prompt distinguishes NL responses from tool-use code blocks
- 7 new coroutine detection tests, 245 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Safe coroutine collection handling in PY dispatch** - `a00e5fa` (fix)
2. **Task 2: Rewrite AI system prompt to distinguish NL from tool-use** - `9d15896` (fix)

## Files Created/Modified
- `bae/repl/shell.py` - Added _contains_coroutines() and _count_and_close_coroutines() helpers, updated PY dispatch for both sync and async paths
- `bae/repl/ai_prompt.md` - Rewrote system prompt: NL-default rules, "When to write code" criteria, NL-only examples
- `tests/repl/test_exec.py` - 7 new tests for coroutine detection and cleanup helpers

## Decisions Made
- Close unawaited coroutines explicitly via .close() rather than letting them garbage collect -- prevents RuntimeWarning and event loop corruption
- Pop namespace["_"] when coroutine collection detected to prevent stale coroutine references from persisting across REPL iterations
- AI prompt restructured around "answer in natural language by default" with explicit criteria for when code is appropriate -- removes the "1 short line per turn" and "use python fences for tool calls" rules that forced code on every response

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Coroutine crash blocker resolved -- PY mode safe for arbitrary async expressions
- AI prompt ready for UAT re-evaluation -- runaway code generation loop root cause addressed
- Remaining UAT gaps (session indicators, eval loop output tee, channel display) tracked in 20-05-PLAN.md

## Self-Check: PASSED

All files found, all commits verified, all key content present.

---
*Phase: 20-ai-eval-loop*
*Completed: 2026-02-14*
