---
phase: 21-execution-convention
verified: 2026-02-14T23:15:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 21: Execution Convention Verification Report

**Phase Goal:** Eval loop only executes code the AI explicitly marks as executable
**Verified:** 2026-02-14T23:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                      | Status     | Evidence                                                                                               |
| --- | -------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------ |
| 1   | AI code blocks marked as executable are extracted and run by eval loop    | ✓ VERIFIED | extract_executable() uses `<run>` regex, eval loop calls it at line 95, tests pass                     |
| 2   | AI code blocks shown as illustration are NOT extracted or executed        | ✓ VERIFIED | test_illustrative_block_ignored passes, test_eval_loop_illustrative_not_executed confirms no execution |
| 3   | Only the first executable block per response is extracted and run         | ✓ VERIFIED | extract_executable returns (first_code, extra_count), test_multiple_executable_blocks passes           |
| 4   | Extra executable blocks produce feedback to AI and notice to user         | ✓ VERIFIED | Lines 123-133 implement multi-block notice, test_eval_loop_multi_block_notice passes                   |
| 5   | When AI does not use the convention, no code executes                     | ✓ VERIFIED | Markdown fences without `<run>` return (None, 0), test_illustrative_not_executed confirms no execution |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                 | Expected                                                         | Status     | Details                                                                                 |
| ------------------------ | ---------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------- |
| `bae/repl/ai.py`         | extract_executable() replacing extract_code(), updated eval loop | ✓ VERIFIED | _EXEC_BLOCK_RE (lines 29-32), extract_executable (214-224), eval loop uses it (line 95) |
| `bae/repl/ai_prompt.md`  | System prompt with winning convention fewshot examples           | ✓ VERIFIED | "Code execution convention" section (line 8), 5 fewshot examples with `<run>` tags      |
| `tests/repl/test_ai.py`  | Updated tests for new extraction and eval loop behavior          | ✓ VERIFIED | TestExtractExecutable (6 tests), TestEvalLoop (11 tests, 2 new), all passing            |

### Key Link Verification

| From                              | To                                | Via                                                            | Status     | Details                                             |
| --------------------------------- | --------------------------------- | -------------------------------------------------------------- | ---------- | --------------------------------------------------- |
| bae/repl/ai.py                    | bae/repl/ai_prompt.md             | _load_prompt() reads updated system prompt with convention    | ✓ WIRED    | _PROMPT_FILE at line 35, _load_prompt at line 233  |
| bae/repl/ai.py __call__           | bae/repl/ai.py extract_executable | eval loop calls extract_executable instead of extract_code     | ✓ WIRED    | Line 95: `code, extra = self.extract_executable(response)` |
| extract_executable                | _EXEC_BLOCK_RE                    | Regex pattern extraction                                       | ✓ WIRED    | Line 221 uses _EXEC_BLOCK_RE.findall(text)         |
| eval loop                         | multi-block feedback              | extra > 0 triggers notice to AI and debug channel              | ✓ WIRED    | Lines 123-133 implement feedback and notice         |

### Requirements Coverage

| Requirement | Status        | Supporting Truths   |
| ----------- | ------------- | ------------------- |
| EXEC-01     | ✓ SATISFIED   | Truth 1, 2          |
| EXEC-02     | ✓ SATISFIED   | Truth 1, 2, 5       |

**Details:**
- **EXEC-01**: AI can distinguish between executable code and illustrative/pseudocode
  - System prompt teaches `<run>` for executable, markdown fences for illustrative
  - 5 fewshot examples demonstrate both cases
- **EXEC-02**: Only code blocks explicitly marked as executable are extracted and run
  - extract_executable() only extracts `<run>` blocks
  - Markdown fences without `<run>` are ignored (test_illustrative_block_ignored)
  - Eval loop executes only first `<run>` block (test_multiple_executable_blocks)

### Anti-Patterns Found

None. Zero TODO/FIXME/PLACEHOLDER comments, no empty implementations, no stub patterns.

### Human Verification Required

None. All truths are programmatically verified through tests and code inspection.

### Summary

**All must-haves verified.** Phase 21 goal achieved.

- xml_tag convention (`<run>code</run>`) fully implemented
- extract_code() completely replaced with extract_executable()
- Eval loop executes only first `<run>` block per response
- Multi-block feedback sent to AI and debug channel
- System prompt teaches convention with 5 fewshot examples
- Markdown fences without `<run>` are ignored (no execution)
- All 41 tests pass (36 in test_ai.py, 5 in test_ai_integration.py)
- Commits 0e8c90d and 65bd6e0 verified in git history

**Requirements EXEC-01 and EXEC-02 satisfied.** Clean break from previous blind extraction. Ready for Phase 22.

---

_Verified: 2026-02-14T23:15:00Z_
_Verifier: Claude (gsd-verifier)_
