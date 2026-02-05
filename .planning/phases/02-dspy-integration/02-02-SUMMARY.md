---
phase: 02-dspy-integration
plan: 02
subsystem: graph-execution
tags: [auto-routing, ellipsis-body, ast-inspection, graph-run]
dependency-graph:
  requires: [02-01, 02-03]
  provides: [_has_ellipsis_body, _get_routing_strategy, auto-routing in Graph.run]
  affects: [02-04, 02-05]
tech-stack:
  added: []
  patterns: [AST inspection, routing strategy dispatch, trace collection]
key-files:
  created:
    - tests/test_auto_routing.py
  modified:
    - bae/node.py
    - bae/graph.py
    - tests/test_graph.py
    - tests/test_integration.py
decisions:
  - name: Ellipsis body detection uses AST
    rationale: Reliable detection of `...` vs custom logic, handles indentation via textwrap.dedent
    impact: Requires inspect.getsource which may fail for built-in methods
  - name: A | None triggers decide not make
    rationale: LLM needs to choose whether to produce A or terminate (None is a choice)
    impact: Consistent with union handling, avoids implicit "always produce A"
metrics:
  duration: 8 min
  completed: 2026-02-05
---

# Phase 02 Plan 02: Auto-Routing Summary

**One-liner:** Graph.run() auto-routes based on return type introspection - ellipsis body triggers decide/make, custom logic escapes to direct call

## What Was Built

### Feature 1: Ellipsis Body Detection

Added `_has_ellipsis_body(method)` to `bae/node.py`:
- Uses AST inspection to check if method body is single `...` (Ellipsis constant)
- Handles class method indentation via `textwrap.dedent`
- Returns True for `def __call__(self, lm) -> A | B: ...`
- Returns False for custom logic like `return lm.decide(self)`

### Feature 2: Auto-Routing in Graph.run()

Added `_get_routing_strategy(node_cls)` to `bae/graph.py`:
- Returns `("custom",)` for nodes with custom logic (non-ellipsis body)
- Returns `("terminal",)` for ellipsis body with pure None return
- Returns `("make", target_type)` for ellipsis body with single return type
- Returns `("decide", types_list)` for ellipsis body with union/optional return

Updated `Graph.run()` to use auto-routing:
- Determines strategy per node using `_get_routing_strategy`
- Dispatches to lm.decide(), lm.make(), or direct __call__ based on strategy
- Now returns `GraphResult` with node and trace instead of just Node|None
- Trace captures all visited nodes in execution order

## Key Code

```python
# bae/node.py
def _has_ellipsis_body(method) -> bool:
    source = inspect.getsource(method)
    source = textwrap.dedent(source)
    tree = ast.parse(source)
    # Find FunctionDef, check if body is single Expr(Constant(...))
    ...

# bae/graph.py
def _get_routing_strategy(node_cls):
    if not _has_ellipsis_body(node_cls.__call__):
        return ("custom",)

    # Analyze return type hint
    if isinstance(return_hint, types.UnionType):
        if len(concrete_types) == 1 and not is_optional:
            return ("make", concrete_types[0])
        return ("decide", concrete_types)
    ...

# Graph.run() dispatch
strategy = _get_routing_strategy(current.__class__)
if strategy[0] == "terminal":
    current = None
elif strategy[0] == "make":
    current = lm.make(current, strategy[1])
elif strategy[0] == "decide":
    current = lm.decide(current)
else:  # custom
    current = current(lm=lm)
```

## Test Coverage

- `tests/test_auto_routing.py` (374 lines)
  - `_has_ellipsis_body` detection for ellipsis vs custom logic
  - `_get_routing_strategy` for all return type patterns
  - `Graph.run()` auto-routing integration
  - `GraphResult` return with trace verification

Updated existing tests:
- `tests/test_graph.py` - expect GraphResult instead of None
- `tests/test_integration.py` - expect GraphResult instead of None

## Commits

| Hash | Type | Description |
|------|------|-------------|
| ebf3815 | test | Add failing tests for _has_ellipsis_body |
| 5a1cb77 | feat | Implement _has_ellipsis_body for auto-routing detection |
| 2d9bed0 | test | Add tests for _get_routing_strategy and Graph.run auto-routing |
| e6e1eb4 | feat | Implement auto-routing in Graph.run() |
| 7fbdf9a | fix | Update existing tests for GraphResult return type |

## Deviations from Plan

None - plan executed exactly as written.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| A \| None triggers decide | LLM chooses between producing A or terminating - None is a valid choice |
| Test nodes require __call__ | Forward reference issue with LM when Node subclass inherits base __call__ |
| GraphResult always returned | Consistent API - trace is always available for debugging/logging |

## Next Phase Readiness

**Blockers:** None

**Ready for:**
- 02-04: Dep injection can now work with traced graph execution
- 02-05: Compilation can leverage auto-routing patterns
