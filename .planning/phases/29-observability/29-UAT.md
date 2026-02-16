---
status: complete
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
  artifacts: []
  missing: []

- truth: "Quiet mode suppresses all non-essential messages (submitted, resolved, done)"
  status: failed
  reason: "User reported: submitted/resolved messages not gated by OutputPolicy. Only gate prompt itself shows correctly."
  severity: minor
  test: 2
  artifacts: []
  missing: []

- truth: "Verbose mode shows per-node transition events (node start/end, fill, decide)"
  status: failed
  reason: "User reported: no node transition events emitted. Engine only emits start/complete/fail, not per-node lifecycle."
  severity: major
  test: 3
  artifacts: []
  missing: []
