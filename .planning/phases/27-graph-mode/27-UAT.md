---
status: complete
phase: 27-graph-mode
source: [27-04-SUMMARY.md, 27-05-SUMMARY.md]
started: 2026-02-15T21:40:00Z
updated: 2026-02-15T21:40:00Z
---

## Current Test

[testing complete]

## Tests

### 1. run with flattened params
expected: In GRAPH mode, `run ootd(name="Dzara", user_message="should I wear a coat?")` works with flat kwargs — no UserInfo construction needed. Prints "submitted g1" and graph runs in background.
result: issue
reported: "flat params work and submits fine, but locks input -- can't type while graph runs, may be stealing stdin"
severity: blocker

### 2. list renders formatted table
expected: In GRAPH mode, `list` shows a properly formatted Rich table with box-drawing characters and aligned columns (ID, STATE, ELAPSED, NODE). No raw ANSI escape codes visible.
result: pass

### 3. inspect shows detail on failed run
expected: After a graph fails, `inspect g1` shows the run ID, state, elapsed time, AND the nodes that executed before the failure with their timings.
result: issue
reported: "fields not aligned with nodes, no per-node timing, trace is wall of text -- lacks indenting and formatting, hard to read"
severity: major

### 4. trace shows partial history on failure
expected: After a graph fails, `trace g1` shows a numbered list of node types that executed before the error — not "no trace available".
result: pass

## Summary

total: 4
passed: 2
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "graph runs in background while Dzara continues using the REPL"
  status: failed
  reason: "User reported: flat params work and submits fine, but locks input -- can't type while graph runs, may be stealing stdin"
  severity: blocker
  test: 1
  artifacts: []
  missing: []
- truth: "inspect shows per-node timings with well-formatted, indented field values"
  status: failed
  reason: "User reported: fields not aligned with nodes, no per-node timing, trace is wall of text lacking indenting and formatting"
  severity: major
  test: 3
  artifacts: []
  missing: []
