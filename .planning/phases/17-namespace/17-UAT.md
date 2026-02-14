---
status: complete
phase: 17-namespace
source: [17-01-SUMMARY.md, 17-02-SUMMARY.md]
started: 2026-02-13T20:00:00Z
updated: 2026-02-13T20:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Bae types available without import
expected: Launch cortex, type `Node` — prints the class, no NameError. Same for `Graph`, `Dep`, `Recall`.
result: pass

### 2. ns shows usage hint
expected: In Py mode, type `ns` (no parentheses) and press Enter. Output shows "ns() -- inspect namespace. ns(obj) -- inspect object." instead of a function address like `<function ns at 0x...>`.
result: pass

### 3. ns() lists namespace objects
expected: Call `ns()` in Py mode. Prints a column-aligned table of all namespace entries (Node, Graph, Dep, Recall, ns, store, channels, asyncio, os, etc.) with type labels and one-line summaries. Underscore-prefixed keys (_trace, __builtins__) are hidden.
result: pass

### 4. ns(NodeClass) shows fields with annotations
expected: Define a Node subclass with Dep and Recall fields, then call `ns(MyNode)`. Output shows class name, docstring (if any), successors, terminal status, and each field with its type, kind (dep/recall/plain), and Dep(fn_name) or Recall() markers.
result: issue
reported: "ns(MyNode) crashes with NameError: name 'Annotated' is not defined. classify_fields() calls get_type_hints() which resolves annotations using the class's module globals, not the REPL namespace. Classes defined in <cortex> don't have Annotated/Dep/Recall in their module globals. Even importing Annotated into the REPL namespace doesn't fix it."
severity: major

### 5. ns(graph) shows topology
expected: Create a graph from Node subclasses and assign to `graph`. Call `ns(graph)`. Output shows `Graph(start=StartNode)`, node count, edges (NodeA -> NodeB, NodeC), and terminal nodes.
result: pass

### 6. _ holds last expression result
expected: In Py mode, type `42` and press Enter. Then type `_` and press Enter — output shows `42`.
result: pass

## Summary

total: 6
passed: 5
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "ns(NodeClass) shows fields with dep/recall/plain classification for REPL-defined classes"
  status: failed
  reason: "User reported: ns(MyNode) crashes with NameError — classify_fields() calls get_type_hints() which resolves annotations using class module globals, not REPL namespace. REPL-defined classes have <cortex> module whose globals lack Annotated/Dep/Recall."
  severity: major
  test: 4
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
