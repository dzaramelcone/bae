---
status: complete
phase: 30-agent-core-extraction
source: [30-01-SUMMARY.md, 30-02-SUMMARY.md]
started: 2026-02-15T14:45:00Z
updated: 2026-02-15T14:48:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Import agent core
expected: `from bae.agent import extract_executable, agent_loop` and `from bae import AgenticBackend` import without error
result: pass

### 2. extract_executable parses real LM-style text
expected: Given text with a `<run>print("hello")</run>` block surrounded by prose, returns `('print("hello")', 0)`. Given text with no run block, returns `(None, 0)`.
result: pass

### 3. agent_loop drives a mock multi-turn exchange
expected: With a mock send function that returns a `<run>` block first, then plain text, agent_loop calls send twice and returns the final plain text response. No REPL imports triggered (no router, store, channels).
result: pass

### 4. REPL AI extract_executable still works
expected: `AI.extract_executable('<run>x=1</run>')` returns `('x=1', 0)` — the static method on AI delegates to bae.agent correctly.
result: pass

### 5. AgenticBackend delegates routing methods
expected: AgenticBackend(model="x").choose_type, .make, and .decide exist as methods and delegate to internal ClaudeCLIBackend (verified by checking `backend._cli` is a ClaudeCLIBackend instance).
result: pass

### 6. No REPL coupling in agent.py
expected: `grep -c "router|store|label|ChannelRouter|SessionStore|ToolCall" bae/agent.py` returns 0. Agent core has zero REPL imports.
result: pass

### 7. _cli_send sanitizes environment
expected: `_cli_send` builds a command that strips CLAUDECODE from env. First call uses `--session-id` + `--system-prompt`. Subsequent calls use `--resume`.
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
