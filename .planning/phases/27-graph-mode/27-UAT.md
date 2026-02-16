---
status: complete
phase: 27-graph-mode
source: [27-01-SUMMARY.md, 27-02-SUMMARY.md]
started: 2026-02-15T17:20:00Z
updated: 2026-02-15T17:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. graph() factory import
expected: `from bae import graph` imports successfully. `graph` is a callable function (not a class).
result: pass

### 2. graph() creates typed async callable
expected: `from examples.ootd import ootd` imports. `ootd` is an async callable (not a Graph instance). `inspect.signature(ootd)` shows `user_info` and `user_message` as keyword-only parameters.
result: pass

### 3. graph() encapsulation
expected: `ootd._name` returns `"IsTheUserGettingDressed"` (a string). `ootd` has no `_graph` attribute -- the internal Graph is fully hidden inside the closure.
result: pass

### 4. GRAPH mode: run submits graph
expected: In GRAPH mode, `run ootd(user_info=UserInfo(), user_message="test")` prints "submitted g1" and the graph starts executing in the background. A done/failed notification follows.
result: issue
reported: "thats obviously a leaky abstraction. we dont have access to the object its expecting"
severity: major

### 5. GRAPH mode: list shows runs
expected: In GRAPH mode, `list` shows a table with columns ID, STATE, ELAPSED, NODE showing graph runs. If no runs exist, shows "(no graph runs)".
result: skipped
reason: blocked by test 4 -- can't submit a graph to populate the list

### 6. GRAPH mode: inspect shows trace
expected: After a graph completes, `inspect g1` shows the run ID, state (done), elapsed time, node timings, and terminal node field values.
result: skipped
reason: blocked by test 4 -- can't submit a graph to inspect

### 7. GRAPH mode: trace shows transitions
expected: `trace g1` shows a numbered list of node type names for a completed run.
result: skipped
reason: blocked by test 4 -- can't submit a graph to trace

### 8. GRAPH mode: unknown command shows help
expected: In GRAPH mode, typing a nonsense command like `foobar` shows an error with a list of available commands (run, list, cancel, inspect, trace).
result: pass

## Summary

total: 8
passed: 4
issues: 1
pending: 0
skipped: 3

## Gaps

- truth: "run <expr> submits a graph callable with its required arguments"
  status: failed
  reason: "User reported: leaky abstraction -- run requires constructing input types (e.g. UserInfo) that aren't in the namespace"
  severity: major
  test: 4
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
- truth: "ls alias removed from GRAPH mode commands"
  status: failed
  reason: "User requested: remove ls alias"
  severity: minor
  test: 8
  root_cause: "ls alias exists in dispatch table in graph_commands.py"
  artifacts:
    - path: "bae/repl/graph_commands.py"
      issue: "ls alias in dispatch dict"
  missing:
    - "Remove ls from dispatch dict"
  debug_session: ""
