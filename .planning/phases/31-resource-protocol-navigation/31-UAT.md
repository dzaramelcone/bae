---
status: diagnosed
phase: 31-resource-protocol-navigation
source: 31-01-SUMMARY.md, 31-02-SUMMARY.md, 31-03-SUMMARY.md
started: 2026-02-16T15:00:00Z
updated: 2026-02-16T15:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Homespace at root returns nav tree
expected: Running `homespace()` in a cortex session shows a Rich-rendered nav tree rooted at "home" with no children (no resourcespaces registered yet)
result: issue
reported: "terminal escape codes once again"
severity: major

### 2. back() at root is safe
expected: Running `back()` at root returns the same root nav tree as `homespace()` — no crash, no error
result: pass

### 3. Navigation into nonexistent resource gives fuzzy error
expected: Running `ResourceRegistry().navigate("sourc")` after registering a "source" resource returns an error containing "Did you mean @source()?"
result: pass

### 4. ToolRouter read at root lists resourcespaces
expected: `ToolRouter(registry).dispatch("read", "")` with an empty registry returns "No resourcespaces registered."
result: pass

### 5. Pruning caps long output
expected: `_prune()` on output over 2000 chars returns pruned output with `[pruned:` indicator and preserved headings/tables
result: pass

### 6. AI prompt includes resource navigation section
expected: `bae/repl/ai_prompt.md` contains a "## Resources" section with instructions for `homespace()`, `back()`, and `source.nav()`
result: pass

### 7. Toolbar location hidden at root
expected: When no resource is navigated into (registry.current is None), the toolbar location widget returns empty — no visual clutter
result: pass

## Summary

total: 7
passed: 6
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "homespace() displays a Rich-rendered nav tree rooted at home"
  status: failed
  reason: "User reported: terminal escape codes once again"
  severity: major
  test: 1
  root_cause: "_run_py displays expression results via repr(result) (shell.py:429-431). homespace() returns a string with ANSI escape codes from _rich_to_ansi, and repr() escapes them — shows \\x1b[1mhome\\x1b[0m instead of bold rendering. All navigation functions (homespace, back, navigate) return ANSI strings that get repr'd."
  artifacts:
    - path: "bae/repl/shell.py"
      issue: "_run_py uses repr() for all expression results, escaping ANSI codes"
    - path: "bae/repl/resource.py"
      issue: "Navigation functions return ANSI strings that need direct printing, not repr"
  missing:
    - "Navigation return values need a type whose __repr__ outputs raw ANSI (not escaped), or navigation functions should use a display-aware return type"
  debug_session: ""
