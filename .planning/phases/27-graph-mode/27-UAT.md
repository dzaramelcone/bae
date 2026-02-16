---
status: complete
phase: 27-graph-mode
source: [27-01-SUMMARY.md, 27-02-SUMMARY.md, 27-03-SUMMARY.md]
started: 2026-02-15T20:00:00Z
updated: 2026-02-15T20:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. run with auto-injected param types
expected: In GRAPH mode, `run ootd(user_info=UserInfo(name="Dzara", city="NYC"), user_message="should I wear a coat?")` works WITHOUT manually importing UserInfo. The command prints "submitted g1" and the graph runs in the background.
result: issue
reported: "graph submits fine (with ootd.UserInfo qualified path) but then locks up -- never completes"
severity: blocker

### 2. ls is not a recognized command
expected: In GRAPH mode, typing `ls` shows "unknown command" with a list of valid commands (run, list, cancel, inspect, trace). It does NOT behave as an alias for list.
result: pass

### 3. list shows graph runs
expected: In GRAPH mode, `list` shows a table with columns ID, STATE, ELAPSED, NODE showing graph runs. If no runs exist, shows "(no graph runs)".
result: issue
reported: "list shows correct data but Rich table renders as raw ANSI escape codes instead of formatted output"
severity: minor

### 4. inspect shows execution trace
expected: After a graph completes, `inspect g1` shows the run ID, state (done), elapsed time, node timings, and terminal node field values.
result: issue
reported: "inspect g1 only shows 'Run g1 (failed, 67.6s)' -- doesn't show which node failed or the nodes that succeeded before it"
severity: major

### 5. trace shows node transitions
expected: `trace g1` shows a numbered list of node type names for a completed run.
result: issue
reported: "trace g1 says 'no trace available' -- nodes did execute before the failure but trace is empty"
severity: major

## Summary

total: 5
passed: 1
issues: 4
pending: 0
skipped: 0

## Gaps

- truth: "run <expr> submits a graph that runs to completion in the background"
  status: failed
  reason: "User reported: graph submits fine but then locks up -- never completes"
  severity: blocker
  test: 1
  artifacts: []
  missing: []
- truth: "list shows a properly formatted table of graph runs"
  status: failed
  reason: "User reported: Rich table renders as raw ANSI escape codes instead of formatted output"
  severity: minor
  test: 3
  artifacts: []
  missing: []
- truth: "inspect shows which node failed and nodes that succeeded before it"
  status: failed
  reason: "User reported: inspect only shows summary line -- no node-level detail, no failure location"
  severity: major
  test: 4
  artifacts: []
  missing: []
- truth: "trace shows node transition history for a failed run"
  status: failed
  reason: "User reported: trace g1 says 'no trace available' even though nodes executed before failure"
  severity: major
  test: 5
  artifacts: []
  missing: []
