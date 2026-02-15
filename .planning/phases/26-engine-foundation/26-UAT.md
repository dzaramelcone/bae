---
status: complete
phase: 26-engine-foundation
source: [26-01-SUMMARY.md, 26-02-SUMMARY.md]
started: 2026-02-15T15:00:00Z
updated: 2026-02-15T15:20:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Engine in namespace
expected: In PY mode, `engine` resolves to a GraphRegistry instance. `type(engine)` shows GraphRegistry.
result: pass

### 2. Graph submission via GRAPH mode
expected: In GRAPH mode, typing input submits to engine and prints "submitted g1". Graph runs in background — REPL remains responsive immediately.
result: pass
note: Works when graph imported from module (`from examples.ootd import graph`). Constructing new Graph() fails — see gap 1.

### 3. Running graph in Ctrl-C menu
expected: While a graph is running, pressing Ctrl-C shows the task menu with an entry prefixed "graph:" (e.g., `graph:g1:StartNode`).
result: issue
reported: "Ctrl-C killed the entire REPL process instead of showing the task menu. Graph was running in background (submitted g1 shown), but Ctrl-C exited to shell prompt."
severity: blocker

### 4. Timing data on completed run
expected: After a graph completes, `engine.get("g1")` returns a GraphRun with `state=DONE` and `node_timings` containing at least one NodeTiming with nonzero `duration_ms`.
result: issue
reported: "Both g1 and g2 have state=FAILED with empty node_timings and empty current_node. Graphs fail immediately without reaching any LM calls. GraphRun doesn't store the exception so there's no way to see why it failed."
severity: blocker

### 5. dep_cache pre-seeds resolver
expected: Calling `graph.arun(dep_cache={some_fn: "preseeded"})` uses the preseeded value instead of calling the dep function. Existing `arun()` calls (no dep_cache) work unchanged.
result: issue
reported: "Graph() constructor fails with unhashable Node TypeError for ALL Node subclasses — even those imported from module files. Cannot construct new graphs at all. dep_cache unit tests pass but the feature is unusable end-to-end because Graph._discover() uses sets."
severity: blocker

## Summary

total: 5
passed: 2
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "Node subclasses can be used in Graph._discover() set operations"
  status: failed
  reason: "User reported: All Node subclasses are unhashable — Graph._discover() uses sets but Node (Pydantic BaseModel) classes cannot be hashed. Fails for REPL-defined and module-imported classes alike. Only pre-constructed Graph objects (created at module import time) work."
  severity: blocker
  test: 2, 5
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "Running graphs appear in Ctrl-C task menu"
  status: failed
  reason: "User reported: Ctrl-C killed the entire REPL process instead of showing the task menu while a graph was running in background"
  severity: blocker
  test: 3
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "Graphs run to completion with timing data captured"
  status: failed
  reason: "User reported: Both runs have state=FAILED, empty node_timings, empty current_node. Graphs fail immediately. GraphRun doesn't store the exception — no error visibility."
  severity: blocker
  test: 4
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
