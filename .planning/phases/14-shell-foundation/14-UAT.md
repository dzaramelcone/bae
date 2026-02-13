---
status: diagnosed
phase: 14-shell-foundation
source: [14-01-SUMMARY.md, 14-02-SUMMARY.md]
started: 2026-02-13T21:00:00Z
updated: 2026-02-13T21:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Launch cortex
expected: Run `bae` with no arguments. A colored `> ` prompt appears with a bottom toolbar showing the mode name (NL) and current working directory.
result: pass

### 2. Mode switching
expected: Press Shift+Tab repeatedly. Prompt color changes and toolbar updates as it cycles: NL (blue) → PY (green) → GRAPH (orange) → BASH (purple) → back to NL.
result: pass

### 3. Python execution
expected: In PY mode, type `1 + 1` and press Enter. Output shows `2`. Then type `await asyncio.sleep(0)` and press Enter — executes without error.
result: issue
reported: "for loop using _ as loop variable prints 19 at the end (async_exec unconditionally returns namespace['_']). Also blank line after first print in async loop."
severity: major

### 4. Multiline editing
expected: In PY mode, press Escape then Enter (or Shift+Enter on kitty-protocol terminals). Cursor moves to a new line without submitting. Press Enter on an empty continuation to submit the block.
result: pass

### 5. Bash commands
expected: In BASH mode, type `echo hello` — prints "hello". Type `ls` — shows directory listing.
result: pass

### 6. Bash cd
expected: In BASH mode, type `cd /tmp`. The toolbar updates to show `/tmp` as cwd. Type `pwd` — prints `/tmp`. Type `cd ~` to return home.
result: pass

### 7. Bash stderr
expected: In BASH mode, type `ls /nonexistent_path`. Error message appears in red text.
result: pass

### 8. Tab completion
expected: In PY mode, type `as` then press Tab. Completion popup appears suggesting `asyncio` (and possibly `assert`). Select `asyncio` to complete.
result: pass

### 9. Stub modes
expected: In NL mode, type any text — shows "(NL mode stub)" message. In GRAPH mode, type any text — shows "Not yet implemented" message.
result: pass

### 10. Exit behavior
expected: With nothing running, press Ctrl-C — REPL exits. Launch again, press Ctrl-D — REPL exits silently.
result: pass

### 11. Existing CLI preserved
expected: Run `bae graph mermaid --help` — shows mermaid command help (does NOT launch cortex). Run `bae run --help` — shows run command help.
result: pass

## Summary

total: 11
passed: 10
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Python execution should not print spurious values from loop variables or internal namespace state"
  status: failed
  reason: "User reported: for loop using _ as loop variable prints 19 at the end (async_exec unconditionally returns namespace['_']). Also blank line after first print in async loop."
  severity: major
  test: 3
  root_cause: "async_exec() always returns namespace.get('_') on line 30, but only rewrites the AST to capture _ when the last statement is ast.Expr (line 15). When user code sets _ independently (e.g. for _ in range(20)), the stale/loop value leaks through as the return value, and shell.py line 135-136 prints it."
  artifacts:
    - path: "bae/repl/exec.py"
      issue: "Unconditional namespace.get('_') return on line 30 — should only return when expression capture rewrite happened"
  missing:
    - "Use a sentinel to track whether expression capture rewrite occurred; only return _ in that case"
  debug_session: ""
