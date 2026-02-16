---
status: diagnosed
phase: 29-observability
source: [29-01-SUMMARY.md, 29-02-SUMMARY.md, 29-03-SUMMARY.md]
started: 2026-02-16T00:30:00Z
updated: 2026-02-16T00:45:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Lifecycle notifications on graph completion
expected: In GRAPH mode, `run <graph>` shows a start notification and a completion notification with elapsed time (e.g. `g1 done (1.2s)`).
result: issue
reported: "prints twice.. [graph:g1] g1 done (40909ms) then [graph:g1] g1 done (40.9s)"
severity: major

### 2. Quiet output policy suppresses lifecycle
expected: `run <graph> --quiet` suppresses start/complete notifications. Only errors or gate prompts would appear.
result: issue
reported: "still resolves.. submitted/resolved messages not gated by policy. Only one done though (vs two in NORMAL), confirming test 1 duplicate."
severity: minor

### 3. Verbose output policy shows all events
expected: `run <graph> --verbose` shows all events including node transitions, not just start/complete.
result: issue
reported: "not seeing that unfortunately.. i would think all nodes would have notifs on start/end, for each step.. fill.. decide.. etc"
severity: major

### 4. Enhanced inspect shows dep timings and RSS
expected: After a graph completes, `inspect <id>` shows a "Dep timings:" section listing each dep function with its duration, and an "RSS delta:" line showing memory change.
result: pass
notes: "Both sections appear. User feedback: dep timings should show start ms, end ms, delta t — not just duration. RSS delta label unclear to user."

### 5. Debug command on completed graph
expected: `debug <id>` on a completed graph reports "not active" since it only works on running/waiting graphs.
result: pass

### 6. Lifecycle events visible from other modes
expected: While in a different mode (e.g. NL or default), a graph completing in the background shows its lifecycle notification inline (or as a badge if shush is on).
result: pass
notes: "User noted gate ID counter is global not per-graph (g1.0, g2.1, g3.2 instead of g1.0, g2.0, g3.0). UX concern."

## Summary

total: 6
passed: 3
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "Graph completion shows a single done notification with elapsed time"
  status: failed
  reason: "User reported: prints twice.. [graph:g1] g1 done (40909ms) then [graph:g1] g1 done (40.9s)"
  severity: major
  test: 1
  root_cause: "Engine _emit('complete') and _on_done task callback both fire. _emit uses ms format, _on_done uses seconds format. Two separate code paths produce the same message."
  artifacts:
    - path: "bae/repl/engine.py"
      issue: "_emit('complete') at lines 232-235 and 317-320"
    - path: "bae/repl/graph_commands.py"
      issue: "_on_done callback at lines 122-125 duplicates engine complete event"
  missing:
    - "Remove success/fail branches from _on_done — keep only cancellation (not covered by _emit)"

- truth: "Quiet mode suppresses all non-essential messages (submitted, resolved, done)"
  status: failed
  reason: "User reported: submitted/resolved messages not gated by OutputPolicy. Only gate prompt itself shows correctly."
  severity: minor
  test: 2
  root_cause: "submitted and resolved messages are direct router.write() calls in graph_commands.py that bypass OutputPolicy. Only engine notify calls go through _emit which checks policy.should_emit()."
  artifacts:
    - path: "bae/repl/graph_commands.py"
      issue: "Line 97-100 (submitted) and line 345-349 (resolved) bypass OutputPolicy"
  missing:
    - "Gate submitted/done/cancelled messages through run.policy.should_emit()"
    - "Resolved message debatable — may be useful as user input acknowledgment"

- truth: "Verbose mode shows per-node transition events (node start/end, fill, decide)"
  status: failed
  reason: "User reported: no node transition events emitted. Engine only emits start/complete/fail, not per-node lifecycle."
  severity: major
  test: 3
  root_cause: "OutputPolicy.VERBOSE.should_emit('transition') returns True but arun() in graph.py has no mechanism to emit events. No EVENT_HOOK_KEY exists in dep_cache. TimingLM records timing data but never emits events."
  artifacts:
    - path: "bae/graph.py"
      issue: "arun() while-loop has no event emission hooks at node transition points"
    - path: "bae/repl/engine.py"
      issue: "No EVENT_HOOK_KEY injected into dep_cache for arun to call back"
  missing:
    - "Add EVENT_HOOK_KEY sentinel to dep_cache pattern"
    - "Emit transition/fill/decide/terminal events from arun() at strategic points"
    - "Give TimingLM access to event emission for LM operation events"
