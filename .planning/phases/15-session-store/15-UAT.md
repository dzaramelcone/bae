---
status: diagnosed
phase: 15-session-store
source: [15-01-SUMMARY.md, 15-02-SUMMARY.md, 15-03-SUMMARY.md]
started: 2026-02-13T22:35:00Z
updated: 2026-02-13T22:50:00Z
---

## Current Test

[testing complete]

## Tests

### 1. PY mode input and expression output recorded
expected: Launch cortex, type `x = 42` then `x`. Then `store()`. Session entries include PY inputs and the expression result output.
result: pass

### 2. print() stdout captured and recorded
expected: Type `print('hello world')` in PY mode. The text "hello world" appears on screen AND `store()` shows a stdout entry containing "hello world".
result: pass

### 3. Bash mode records output
expected: Switch to BASH mode (Shift+Tab), run `echo hello`. Switch back to PY, run `store()`. Session entries include the bash output.
result: pass

### 4. store() shows clean session summary
expected: After several inputs, `store()` prints session entries with mode and direction labels. Output is clean text (no `<sqlite3.Row ...>` repr noise). `store()` expression itself produces no extra output line (returns None).
result: issue
reported: "Long entries in store() display get truncated mid-line with no ellipsis or indicator. Needs a truncation marker."
severity: minor

### 5. store() FTS5 search
expected: After typing various things, `store('hello')` returns only entries containing "hello". Clean output, no Row objects.
result: issue
reported: "FTS5 search works but display tags are inconsistent — store() shows [PY:output] while store('query') shows [PY:repl:output]. Tags are being formatted in different places rather than by a dedicated formatter. Needs refactoring so formatting is a single concern."
severity: major

### 6. Cross-session browsing via store.sessions()
expected: Exit cortex (Ctrl-D). Relaunch `uv run bae`. Type `store.sessions()` — returns a list with previous sessions. `store.recent()` and `store.search('hello')` also work directly.
result: issue
reported: "Methods work (no AttributeError), but store.sessions(), store.recent(), and store.search() all return raw sqlite3.Row objects. Completely unusable — walls of <sqlite3.Row object at 0x...>. Only __call__ converts to dicts. All public methods need to return dicts or formatted output."
severity: major

## Summary

total: 6
passed: 3
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "store() display truncates long entries cleanly with ellipsis"
  status: failed
  reason: "User reported: Long entries truncated mid-line with no indicator. Needs ellipsis."
  severity: minor
  test: 4
  root_cause: "Display formatting hardcodes [:60] and [:80] slices with no truncation indicator"
  artifacts:
    - path: "bae/repl/store.py"
      issue: "Line 132: session display truncates at 60 chars without ellipsis; line 126: search display truncates at 80 chars without ellipsis"
  missing:
    - "Add ellipsis suffix when content exceeds display width in both display paths"
  debug_session: ""

- truth: "store() and store('query') use consistent tag formatting via a single formatter"
  status: failed
  reason: "User reported: Tags differ between store() and store('query') — [PY:output] vs [PY:repl:output]. Formatting happens in different places, not centralized."
  severity: major
  test: 5
  root_cause: "Two separate formatting paths — session display uses [mode:direction] (2 fields), search display uses [mode:channel:direction] (3 fields)"
  artifacts:
    - path: "bae/repl/store.py"
      issue: "Line 132: [mode:direction] format; line 126: [mode:channel:direction] format — no shared formatter"
  missing:
    - "Extract _format_entry() method used by both __call__ branches with canonical tag format"
  debug_session: ""

- truth: "All SessionStore public methods return usable data (dicts, not raw Row objects)"
  status: failed
  reason: "User reported: store.sessions(), store.recent(), store.search() return raw sqlite3.Row objects. Only __call__ converts to dicts."
  severity: major
  test: 6
  root_cause: "Only __call__ converts Row to dict; search(), recent(), session_entries(), sessions() all return raw sqlite3.Row"
  artifacts:
    - path: "bae/repl/store.py"
      issue: "Lines 91-118: all public methods return list[sqlite3.Row]; only __call__ (lines 124-132) uses dict(e)"
  missing:
    - "All public methods return list[dict] via [dict(row) for row in rows] conversion"
  debug_session: ""
