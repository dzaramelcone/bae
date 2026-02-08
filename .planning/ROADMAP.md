# Milestone v3.0: Async Graphs

**Status:** Active
**Phases:** 11-13
**Total Plans:** TBD (created during plan-phase)

## Overview

Async interface with parallel dep resolution and subgraph composition. Dep(callable) is already the fan-out/join primitive — this milestone makes it concurrent. DSPy has native async (`Predict.acall()`), PydanticAI is async-native, pytest-asyncio is already configured.

## Phases

### Phase 11: Async Core
**Goal**: All LM backends, Graph.run(), and Node.__call__() are async. Existing tests pass.
**Depends on**: v2.0 complete
**Requirements**: ASYNC-01 through ASYNC-09, MIG-01

**Success Criteria:**
1. `Graph.run()` is `async def` and awaits LM calls
2. All three backends (PydanticAI, ClaudeCLI, DSPy) implement async LM protocol
3. PydanticAI uses `await agent.run()` (native async, not sync wrapper)
4. ClaudeCLI uses `asyncio.create_subprocess_exec()` (not `subprocess.run()`)
5. DSPy uses `await predictor.acall()` (native async)
6. All existing tests pass with pytest-asyncio

### Phase 12: Parallel Deps
**Goal**: Independent deps on the same node resolve concurrently. Sync and async dep callables both work.
**Depends on**: Phase 11
**Requirements**: PDEP-01 through PDEP-05

**Success Criteria:**
1. `resolve_fields()` and `resolve_dep()` are async
2. Independent deps on the same node fire via `asyncio.gather()` — measurable speedup for multi-dep nodes
3. `Dep(sync_fn)` and `Dep(async_fn)` both work (runtime detection via `inspect.iscoroutinefunction`)
4. Dep DAG topological ordering still enforced — dependent deps resolve in order, independent deps resolve in parallel
5. Per-run dep caching is race-condition-free under concurrent resolution

### Phase 13: Subgraph Composition
**Goal**: A Dep can execute another Graph. Subgraph traces and errors integrate cleanly with parent graph.
**Depends on**: Phase 12
**Requirements**: SUB-01 through SUB-03, MIG-02, MIG-03

**Success Criteria:**
1. A Dep callable that runs `await graph.run(start)` works end-to-end
2. Subgraph trace nodes are accessible from the parent GraphResult (nested or flattened)
3. Subgraph exceptions become DepError in the parent graph with clear error naming the subgraph
4. examples/ootd.py works with async graph.run()
5. E2E tests pass with async backends

---

## Key Decisions

- Full async, not threading — correct long-term play
- DSPy has native async (Predict.acall) — no asyncio.to_thread() needed
- PydanticAI is async-native — just swap run_sync() to await run()
- pytest-asyncio already configured with asyncio_mode="auto"
- Dep(callable) supports both sync and async — detect at runtime
- Node.__call__() becomes async — user custom __call__ must also be async
- CLI boundary: asyncio.run() wraps async graph.run() in Typer commands

## Conversion Scope

| File | Methods → async | Difficulty |
|------|----------------|------------|
| graph.py | 1 (run) | Moderate |
| lm.py | 9 (protocol + 2 backends) | Moderate |
| dspy_backend.py | 6 | Moderate |
| optimized_lm.py | 1 | Trivial |
| compiler.py | 1-2 | Trivial |
| node.py | 1 (__call__) | Trivial |
| resolver.py | 2 (resolve_dep, resolve_fields) | Tricky (gather) |
| cli.py | 0 (asyncio.run boundary) | Trivial |
| Tests (~325 functions) | All | Mechanical |

---
*Created: 2026-02-08 for v3.0 Async Graphs*
