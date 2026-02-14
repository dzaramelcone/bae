---
status: complete
phase: 18-ai-agent
source: 18-01-SUMMARY.md, 18-02-SUMMARY.md
started: 2026-02-13T22:00:00Z
updated: 2026-02-14T03:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. AI object in namespace
expected: Launch cortex, type `ai` in PY mode. Shows repr with session ID and 0 calls.
result: pass

### 2. NL conversation
expected: Switch to NL mode (Shift+Tab), type a question like "what is bae?". After a few seconds, AI response appears on the [ai] channel. No crash.
result: pass (with noted future work)
notes: "Blocking call -- streaming/progressive display and markdown rendering are future enhancements."

### 3. NL follow-up (session persistence)
expected: In NL mode, ask a follow-up referencing the previous answer (e.g. "can you elaborate?"). AI response shows awareness of the prior exchange.
result: pass

### 4. NL error handling
expected: If AI fails (e.g. network issue, timeout), error traceback appears on [ai] channel. REPL does not crash — prompt returns normally.
result: pass

### 5. Code extraction
expected: In PY mode, run `ai.extract_code(...)`. Returns extracted code blocks.
result: pass

### 6. Context builder with namespace objects
expected: In PY mode, define `x = 42`, then switch to NL and ask "what variables do I have?". AI response mentions `x = 42`.
result: pass (after 3 prompt iterations)
notes: "Fixed by: (1) reformatting context as REPL output, (2) disowning Claude Code tools, (3) precise tool API signatures."

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Future Work (accepted, not blocking)

- Streaming/progressive display for NL responses (currently blocking)
- Markdown rendering for [ai] channel output
- Auto code extraction + eval loop (AI code → extract → exec → feed output back)
