---
status: complete
phase: 18-ai-agent
source: 18-01-SUMMARY.md, 18-02-SUMMARY.md
started: 2026-02-13T22:00:00Z
updated: 2026-02-13T22:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. AI object in namespace
expected: Launch cortex, type `ai` in PY mode. Shows repr with session ID and 0 calls.
result: pass

### 2. NL conversation
expected: Switch to NL mode (Shift+Tab), type a question like "what is bae?". After a few seconds, AI response appears on the [ai] channel. No crash.
result: issue
reported: "its blocking? this should be an async call.. itd be nice to have markdown too.."
severity: minor

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
result: issue
reported: "AI doesn't trust the namespace context — treats it as example data, tries to run bash commands (tools disabled), hallucinates Chinese characters. System prompt doesn't make clear that namespace snapshot is live REPL state."
severity: major

## Summary

total: 6
passed: 4
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "NL response appears progressively and renders markdown formatting"
  status: failed
  reason: "User reported: blocking call with no visual feedback, raw markdown displayed as plain text"
  severity: minor
  test: 2
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "AI uses namespace context to give specific, relevant answers about user's variables"
  status: failed
  reason: "User reported: AI doesn't trust namespace context, treats as example data, tries bash commands, hallucinates"
  severity: major
  test: 6
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
