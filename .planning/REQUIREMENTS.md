# Requirements: v3.0 Async Graphs

**Created:** 2026-02-08
**Status:** Active

## Async Core

- [x] **ASYNC-01**: Graph.run() is async (`async def run()`)
- [x] **ASYNC-02**: LM protocol methods (choose_type, fill, make, decide) are async
- [x] **ASYNC-03**: PydanticAIBackend uses native async (`await agent.run()` instead of `agent.run_sync()`)
- [x] **ASYNC-04**: ClaudeCLIBackend uses `asyncio.create_subprocess_exec()` instead of `subprocess.run()`
- [x] **ASYNC-05**: DSPyBackend uses native async (`await predictor.acall()` instead of `predictor()`)
- [x] **ASYNC-06**: OptimizedLM async (inherits from async DSPyBackend)
- [x] **ASYNC-07**: Node.__call__() is async
- [x] **ASYNC-08**: CLI uses `asyncio.run()` at the boundary (Typer stays sync)
- [x] **ASYNC-09**: CompiledGraph.run() is async

## Parallel Dependency Resolution

- [ ] **PDEP-01**: Independent deps on the same node resolve concurrently via `asyncio.gather()`
- [ ] **PDEP-02**: Dep(callable) supports both sync and async callables (detect with `inspect.iscoroutinefunction`)
- [ ] **PDEP-03**: Dep DAG resolution respects topological ordering while maximizing parallelism within each level
- [ ] **PDEP-04**: Per-run dep caching works correctly with concurrent resolution (no race conditions)
- [ ] **PDEP-05**: resolve_fields() and resolve_dep() are async

## Migration

- [ ] **MIG-01**: All existing tests pass with async (pytest-asyncio, asyncio_mode="auto")
- [ ] **MIG-02**: examples/ootd.py works with async graph.run()
- [ ] **MIG-03**: E2E tests (--run-e2e) pass with async backends

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ASYNC-01 | 11 | Complete |
| ASYNC-02 | 11 | Complete |
| ASYNC-03 | 11 | Complete |
| ASYNC-04 | 11 | Complete |
| ASYNC-05 | 11 | Complete |
| ASYNC-06 | 11 | Complete |
| ASYNC-07 | 11 | Complete |
| ASYNC-08 | 11 | Complete |
| ASYNC-09 | 11 | Complete |
| PDEP-01 | 12 | Pending |
| PDEP-02 | 12 | Pending |
| PDEP-03 | 12 | Pending |
| PDEP-04 | 12 | Pending |
| PDEP-05 | 12 | Pending |
| MIG-01 | 12 | Pending |
| MIG-02 | 12 | Pending |
| MIG-03 | 12 | Pending |

**Coverage:** 17 requirements, 9 complete

---
*Created: 2026-02-08 for v3.0 Async Graphs*
