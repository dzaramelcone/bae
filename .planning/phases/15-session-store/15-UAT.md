---
status: complete
phase: 15-session-store
source: [15-01-SUMMARY.md, 15-02-SUMMARY.md]
started: 2026-02-13T22:00:00Z
updated: 2026-02-13T22:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. PY mode input recorded
expected: Launch cortex, type `x = 42`, then `store()`. Session shows entries including `[PY:input] x = 42`.
result: pass

### 2. PY mode output recorded
expected: Type `1 + 1` in PY mode. Then `store()`. Session entries include `[PY:output] 2` with direction=output.
result: pass

### 3. Bash mode records stdout and stderr
expected: Switch to BASH mode (Shift+Tab until BASH prompt), run `echo hello`. Then switch back to PY and run `store()`. Session entries include `[BASH:output] hello`.
result: pass

### 4. store() shows session summary
expected: After several inputs, `store()` prints a line like `Session <uuid>: N entries` followed by recent entries with mode and direction labels.
result: issue
reported: "print() output from PY mode not captured in store. for loop with 30 print() calls produced visible terminal output but store() shows no record of it. Only expression return values and errors are recorded, not stdout/stderr from print()."
severity: major

### 5. store() FTS5 search
expected: After typing various things, `store('42')` returns only entries containing "42" (e.g., `x = 42` input and `42` output).
result: pass

### 6. Cross-session persistence
expected: Exit cortex (Ctrl-D). Relaunch `uv run bae`. Type `store()`. You should see a new session, but `store.sessions()` (or inspecting `.bae/store.db`) shows both the previous and current session.
result: issue
reported: "Cross-session persistence works (new UUID, shared .bae/store.db), but store.sessions() fails with AttributeError because store in namespace is the inspector closure, not the SessionStore instance. No way to list or browse previous sessions from the REPL."
severity: major

## Summary

total: 6
passed: 4
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "All PY mode output including print() is recorded in the session store"
  status: failed
  reason: "User reported: print() output from PY mode not captured. Only expression return values and errors recorded, not stdout/stderr."
  severity: major
  test: 4
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "User can list and browse previous sessions from the REPL"
  status: failed
  reason: "User reported: store.sessions() fails with AttributeError because store in namespace is the inspector closure, not the SessionStore instance. No way to list or browse previous sessions."
  severity: major
  test: 6
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
