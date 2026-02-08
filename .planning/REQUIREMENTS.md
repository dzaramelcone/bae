# Requirements: v3.0 Async Graphs

**Created:** 2026-02-08
**Status:** Active

## Async Core

- [ ] **ASYNC-01**: Graph.run() is async (`async def run()`)
- [ ] **ASYNC-02**: LM protocol methods (choose_type, fill, make, decide) are async
- [ ] **ASYNC-03**: PydanticAIBackend uses native async (`await agent.run()` instead of `agent.run_sync()`)
- [ ] **ASYNC-04**: ClaudeCLIBackend uses `asyncio.create_subprocess_exec()` instead of `subprocess.run()`
- [ ] **ASYNC-05**: DSPyBackend uses native async (`await predictor.acall()` instead of `predictor()`)
- [ ] **ASYNC-06**: OptimizedLM async (inherits from async DSPyBackend)
- [ ] **ASYNC-07**: Node.__call__() is async
- [ ] **ASYNC-08**: CLI uses `asyncio.run()` at the boundary (Typer stays sync)
- [ ] **ASYNC-09**: CompiledGraph.run() is async

## Parallel Dependency Resolution

- [ ] **PDEP-01**: Independent deps on the same node resolve concurrently via `asyncio.gather()`
- [ ] **PDEP-02**: Dep(callable) supports both sync and async callables (detect with `inspect.iscoroutinefunction`)
- [ ] **PDEP-03**: Dep DAG resolution respects topological ordering while maximizing parallelism within each level
- [ ] **PDEP-04**: Per-run dep caching works correctly with concurrent resolution (no race conditions)
- [ ] **PDEP-05**: resolve_fields() and resolve_dep() are async

## Subgraph Composition

- [ ] **SUB-01**: A Dep callable can execute another Graph (`async def sub(input): return await other_graph.run(start).result`)
- [ ] **SUB-02**: Subgraph traces are accessible from the parent GraphResult
- [ ] **SUB-03**: Subgraph errors propagate cleanly as DepError in parent graph

## Migration

- [ ] **MIG-01**: All existing tests pass with async (pytest-asyncio, asyncio_mode="auto")
- [ ] **MIG-02**: examples/ootd.py works with async graph.run()
- [ ] **MIG-03**: E2E tests (--run-e2e) pass with async backends

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ASYNC-01 | 11 | Pending |
| ASYNC-02 | 11 | Pending |
| ASYNC-03 | 11 | Pending |
| ASYNC-04 | 11 | Pending |
| ASYNC-05 | 11 | Pending |
| ASYNC-06 | 11 | Pending |
| ASYNC-07 | 11 | Pending |
| ASYNC-08 | 11 | Pending |
| ASYNC-09 | 11 | Pending |
| PDEP-01 | 12 | Pending |
| PDEP-02 | 12 | Pending |
| PDEP-03 | 12 | Pending |
| PDEP-04 | 12 | Pending |
| PDEP-05 | 12 | Pending |
| SUB-01 | 13 | Pending |
| SUB-02 | 13 | Pending |
| SUB-03 | 13 | Pending |
| MIG-01 | 11-13 | Pending |
| MIG-02 | 13 | Pending |
| MIG-03 | 13 | Pending |

**Coverage:** 20 requirements, 0 complete

---
*Created: 2026-02-08 for v3.0 Async Graphs*
