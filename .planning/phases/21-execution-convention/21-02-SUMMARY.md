---
phase: 21-execution-convention
plan: 02
subsystem: repl
tags: [xml-tag, code-extraction, eval-loop, convention, regex]

# Dependency graph
requires:
  - phase: 21-execution-convention
    provides: "xml_tag convention selected via 6-convention eval (Plan 01)"
provides:
  - "extract_executable() with <run>code</run> regex"
  - "Convention-aware eval loop (single-block execution with multi-block feedback)"
  - "System prompt with xml_tag fewshot examples"
affects: [22-stream-format, 23-output-views]

# Tech tracking
tech-stack:
  added: []
  patterns: ["<run>code</run> for executable, markdown fences for illustrative"]

key-files:
  created: []
  modified:
    - bae/repl/ai.py
    - bae/repl/ai_prompt.md
    - tests/repl/test_ai.py
    - tests/repl/test_ai_integration.py

key-decisions:
  - "xml_tag regex: r'<run>\\s*\\n?(.*?)\\n?\\s*</run>' (re.DOTALL) -- matches <run> blocks with flexible whitespace"
  - "No backward compat: bare markdown fences no longer trigger execution"
  - "Multi-block notice via debug channel with exec_notice metadata type"

patterns-established:
  - "Convention-marked execution: only <run>code</run> blocks are extracted and run"
  - "Single-block policy: first <run> block per response executes, extras produce feedback"

# Metrics
duration: 4min
completed: 2026-02-14
---

# Phase 21 Plan 02: Implement Winning Convention Summary

**xml_tag convention (<run>code</run>) replacing blind extract_code() with convention-aware extract_executable() and 5-example system prompt**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-14T17:37:04Z
- **Completed:** 2026-02-14T17:41:55Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Replaced _CODE_BLOCK_RE and extract_code() with _EXEC_BLOCK_RE and extract_executable() using xml_tag regex
- Eval loop now executes only the first <run> block per response; extra blocks produce AI feedback and debug channel notice
- System prompt teaches the convention with 5 fewshot examples covering: NL-only, computation, illustrative-only, mixed, and namespace inspection
- 41 tests pass in test_ai.py including 2 new tests (multi_block_notice, illustrative_not_executed)
- Integration tests updated for new API (extract_executable, <run> syntax in concurrent session test)

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace extract_code with extract_executable and update eval loop** - `0e8c90d` (feat)
2. **Task 2: Update system prompt and tests for winning convention** - `65bd6e0` (feat)

## Files Created/Modified
- `bae/repl/ai.py` - Replaced _CODE_BLOCK_RE with _EXEC_BLOCK_RE, extract_code with extract_executable, rewrote eval loop for single-block execution
- `bae/repl/ai_prompt.md` - New "Code execution convention" section with 5 xml_tag fewshot examples
- `tests/repl/test_ai.py` - TestExtractExecutable (6 tests), updated TestEvalLoop (11 tests including 2 new), TestPromptFile (4 tests including convention check)
- `tests/repl/test_ai_integration.py` - Updated extract_code references to extract_executable, updated concurrent session test to use <run> syntax

## Decisions Made
- xml_tag regex uses flexible whitespace matching (`\s*\n?`) to handle both `<run>code</run>` (inline) and `<run>\ncode\n</run>` (multiline) patterns
- Multi-block notice uses singular/plural grammar ("1 block was" vs "2 blocks were")
- Feedback format simplified from `[Block N output]` to `[Output]` since only one block executes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated test_ai_integration.py for new API**
- **Found during:** Task 2 (full suite run)
- **Issue:** test_ai_extract_code_from_namespace called removed extract_code method; test_concurrent_sessions_namespace_mutations used markdown fences that no longer trigger execution
- **Fix:** Renamed test to test_ai_extract_executable_from_namespace using <run> syntax; updated concurrent session mock responses to use <run> tags
- **Files modified:** tests/repl/test_ai_integration.py
- **Verification:** All 54 tests in test_ai.py + test_ai_integration.py pass
- **Committed in:** 65bd6e0 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Integration test file was not listed in plan's files_modified but required updates for API compatibility. No scope creep.

## Issues Encountered
- 6 tests in test_fill_protocol.py and test_integration.py fail with "Claude Code cannot be launched inside another Claude Code session" -- this is an environment artifact of running pytest inside Claude Code, not a regression from our changes. These tests pass in standalone pytest runs.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 21 complete (both plans executed)
- xml_tag convention fully implemented and tested
- Ready for Phase 22 (Stream Format)

## Self-Check: PASSED

- [x] bae/repl/ai.py exists
- [x] bae/repl/ai_prompt.md exists
- [x] tests/repl/test_ai.py exists
- [x] tests/repl/test_ai_integration.py exists
- [x] 21-02-SUMMARY.md exists
- [x] Commit 0e8c90d found
- [x] Commit 65bd6e0 found

---
*Phase: 21-execution-convention*
*Completed: 2026-02-14*
