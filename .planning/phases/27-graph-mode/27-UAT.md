---
status: diagnosed
phase: 27-graph-mode
source: [27-01-SUMMARY.md, 27-02-SUMMARY.md, 27-03-SUMMARY.md]
started: 2026-02-15T20:00:00Z
updated: 2026-02-15T20:10:00Z
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
  root_cause: "ClaudeCLIBackend has 20s per-call timeout (lm.py:413). Complex graphs like ootd with 6+ nodes accumulate 10+ LM calls; any slow call triggers timeout. 67.6s indicates several calls succeeded before one hit the limit."
  artifacts:
    - path: "bae/lm.py"
      issue: "timeout: int = 20 is too low for complex graphs"
  missing:
    - "Increase default timeout or make configurable per-graph"
  debug_session: ".planning/debug/graph-run-timeout-no-trace.md"
- truth: "list shows a properly formatted table of graph runs"
  status: failed
  reason: "User reported: Rich table renders as raw ANSI escape codes instead of formatted output"
  severity: minor
  test: 3
  root_cause: "_cmd_list sends ANSI string via router.write() but channel formatters (UserView._render_prefixed) treat content as plain text via FormattedText, displaying escape codes literally instead of interpreting them with ANSI() wrapper."
  artifacts:
    - path: "bae/repl/graph_commands.py"
      issue: "router.write() calls at lines 140, 206 send ANSI strings without metadata signal"
    - path: "bae/repl/views.py"
      issue: "UserView._render_prefixed wraps in FormattedText (plain text) not ANSI()"
  missing:
    - "Add metadata={'type': 'ansi'} to router.write() calls"
    - "Extend formatters to check metadata type and use ANSI() wrapper when appropriate"
  debug_session: ".planning/debug/graph-list-ansi-escape-codes.md"
- truth: "inspect shows which node failed and nodes that succeeded before it"
  status: failed
  reason: "User reported: inspect only shows summary line -- no node-level detail, no failure location"
  severity: major
  test: 4
  root_cause: "submit_coro() bypasses TimingLM injection (engine.py:125-141) since LM is already bound in closure. GraphRun.node_timings stays empty. inspect checks run.node_timings but finds nothing."
  artifacts:
    - path: "bae/repl/engine.py"
      issue: "submit_coro (line 125) creates GraphRun with graph=None, no TimingLM"
    - path: "bae/repl/graph_commands.py"
      issue: "_cmd_inspect checks run.node_timings but it's empty for submit_coro runs"
  missing:
    - "Extract timing/trace from GraphResult on run.result, or inject TimingLM into closure"
  debug_session: ".planning/debug/graph-run-timeout-no-trace.md"
- truth: "trace shows node transition history for a failed run"
  status: failed
  reason: "User reported: trace g1 says 'no trace available' even though nodes executed before failure"
  severity: major
  test: 5
  root_cause: "_wrap_coro() (engine.py:143-160) only sets run.result on success. On failure, RuntimeError from LM backend propagates -- graph.arun() attaches .trace to BaeError/DepError but not RuntimeError. run.result stays None, so trace command sees nothing."
  artifacts:
    - path: "bae/repl/engine.py"
      issue: "_wrap_coro only sets run.result on success (line 148-149), not on failure"
    - path: "bae/graph.py"
      issue: "Only BaeError/DepError get .trace attached (lines 336, 350), not RuntimeError"
  missing:
    - "Preserve partial trace on failure: extract from exception or capture before re-raise"
  debug_session: ".planning/debug/graph-run-timeout-no-trace.md"
