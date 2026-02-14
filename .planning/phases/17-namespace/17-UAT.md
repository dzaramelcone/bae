---
status: complete
phase: 17-namespace
source: [17-01-SUMMARY.md, 17-02-SUMMARY.md, 17-03-SUMMARY.md]
started: 2026-02-14T01:20:00Z
updated: 2026-02-14T01:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Bae types available without import
expected: Launch cortex. In Py mode, type `Node` — prints the class, no NameError. Same for `Graph`, `Dep`, `Recall`, `Annotated`.
result: pass

### 2. ns shows usage hint
expected: In Py mode, type `ns` (no parentheses) and press Enter. Output shows "ns() -- inspect namespace. ns(obj) -- inspect object." instead of a function address.
result: pass

### 3. ns() lists namespace objects
expected: Call `ns()`. Prints a column-aligned table of namespace entries (Node, Graph, Dep, Recall, ns, store, channels, asyncio, os, etc.) with type labels and one-line summaries. Underscore-prefixed keys are hidden.
result: pass

### 4. ns(REPLDefinedNode) shows fields (gap closure re-test)
expected: Define a Node subclass in the REPL with Dep/Recall fields, then call `ns(MyNode)`. Output shows class name, each field with its type, and kind classification (plain/dep). No NameError.
result: pass

### 5. ns(graph) shows topology
expected: Create a simple graph from Node subclasses (`g = Graph(start=MyNode)`). Call `ns(g)`. Output shows `Graph(start=MyNode)`, node count, edges, and terminal nodes.
result: pass

### 6. _ holds last expression result
expected: Type `42` and press Enter. Then type `_` and press Enter — output shows `42`.
result: pass

### 7. _trace after graph run
expected: In GRAPH mode, run a graph. Switch to Py mode and type `_trace` — it holds a trace object.
result: skipped
reason: GRAPH mode is a stub ("Not yet implemented") — _trace capture code exists in shell.py but can't be exercised through UI until GRAPH mode is built

## Summary

total: 7
passed: 6
issues: 0
pending: 0
skipped: 1

## Gaps

[none]
