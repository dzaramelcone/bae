---
status: diagnosed
phase: 26-engine-foundation
source: [26-01-SUMMARY.md, 26-02-SUMMARY.md]
started: 2026-02-15T15:00:00Z
updated: 2026-02-15T15:30:00Z
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
note: Works when graph imported from module (`from examples.ootd import graph`). Passing instance to Graph() fails — Graph expects class, not instance.

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
reported: "Graph() constructor fails with unhashable Node TypeError when passing instance. Graph expects class, not instance. dep_cache unit tests pass but confusing API error."
severity: blocker

## Summary

total: 5
passed: 2
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "Graph() gives clear error when instance passed instead of class"
  status: failed
  reason: "User reported: Graph._discover() raises confusing 'unhashable type' error. Graph(start=...) expects a class but user naturally passes instance with fields. No runtime guard, no helpful error message."
  severity: major
  test: 2, 5
  root_cause: "Graph.__init__ accepts start: type[Node] but has no runtime isinstance check. _discover() puts self.start into a set, which fails on instances because Pydantic BaseModel sets __hash__ = None. Error message is cryptic."
  artifacts:
    - path: "bae/graph.py"
      issue: "Lines 156-167: no isinstance(start, type) guard in __init__"
    - path: "bae/graph.py"
      issue: "Lines 188-195: _discover uses set() which hashes self.start"
  missing:
    - "Runtime guard in Graph.__init__ that detects instance vs class and gives helpful error"
  debug_session: ".planning/debug/node-unhashable-in-discover.md"

- truth: "Running graphs appear in Ctrl-C task menu"
  status: failed
  reason: "User reported: Ctrl-C killed the entire REPL process instead of showing the task menu while a graph was running in background"
  severity: blocker
  test: 3
  root_cause: "ClaudeCLIBackend._run_cli_json() at bae/lm.py:464 creates subprocesses WITHOUT start_new_session=True. SIGINT hits entire process group (REPL + Claude CLI child). KeyboardInterrupt bypasses prompt_toolkit handler, propagates to shell.py:449 which catches it and exits. Every other subprocess in codebase (ai.py:235, bash.py:34, agent.py:173) uses start_new_session=True — lm.py is the sole outlier."
  artifacts:
    - path: "bae/lm.py"
      issue: "Line 464: create_subprocess_exec missing start_new_session=True"
    - path: "bae/repl/shell.py"
      issue: "Line 449: KeyboardInterrupt caught in run() causes clean exit"
  missing:
    - "Add start_new_session=True to _run_cli_json subprocess creation"
  debug_session: ".planning/debug/ctrl-c-kills-repl.md"

- truth: "Graphs run to completion with timing data captured"
  status: failed
  reason: "User reported: Both runs have state=FAILED, empty node_timings, empty current_node. Graphs fail immediately. GraphRun doesn't store the exception — no error visibility."
  severity: blocker
  test: 4
  root_cause: "Two bugs. (1) shell._run_graph passes text=text but graph start node expects user_info + user_message — wrong kwarg, TypeError raised at graph.py:300-303 before any node executes. (2) GraphRun has no error field, _execute re-raises into void, TaskManager._on_done eats the exception silently — three layers conspire to hide the error."
  artifacts:
    - path: "bae/repl/shell.py"
      issue: "Line 343: passes text=text but graph needs graph-specific field names"
    - path: "bae/repl/engine.py"
      issue: "Lines 39-46: GraphRun has no error field to store exceptions"
    - path: "bae/repl/tasks.py"
      issue: "Lines 75-84: _on_done detects failure but never logs/surfaces exception"
  missing:
    - "GraphRun needs error field to store exception"
    - "Engine _execute should store exception in run.error before re-raising"
    - "Graph channel should surface error message to user"
    - "GRAPH mode needs design for mapping REPL input to graph-specific field names"
  debug_session: ".planning/debug/engine-silent-fail.md"
