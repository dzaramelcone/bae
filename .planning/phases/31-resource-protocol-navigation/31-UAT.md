---
status: complete
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
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
