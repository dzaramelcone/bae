# Milestone v3.0: Async Graphs

**Status:** Active
**Phases:** 11-13
**Total Plans:** 4 (Phase 11), 4 (Phase 12), TBD (Phase 13)

## Overview

Async interface with parallel dep resolution. Dep(callable) is already the fan-out/join primitive — this milestone makes it concurrent. Subgraph composition (Dep that runs another graph) falls out for free via async __call__ and async dep functions — no special framework support needed.

DSPy has native async (`Predict.acall()`), PydanticAI is async-native, pytest-asyncio is already configured.

## Phases

### Phase 11: Async Core ✓
**Goal**: All LM backends, Graph.run(), and Node.__call__() are async. Existing tests pass.
**Depends on**: v2.0 complete
**Requirements**: ASYNC-01 through ASYNC-09
**Plans:** 4 plans — **Complete** (2026-02-09)

Plans:
- [x] 11-01-PLAN.md — LM Protocol + PydanticAI + ClaudeCLI async (lm.py + tests)
- [x] 11-02-PLAN.md — DSPyBackend + OptimizedLM async (dspy_backend.py, optimized_lm.py + tests)
- [x] 11-03-PLAN.md — Node + Graph + Compiler + CLI async (node.py, graph.py, compiler.py, cli.py + tests)
- [x] 11-04-PLAN.md — Integration + E2E test migration + full suite verification

**Success Criteria:**
1. `Graph.run()` is `async def` and awaits LM calls
2. All three backends (PydanticAI, ClaudeCLI, DSPy) implement async LM protocol
3. PydanticAI uses `await agent.run()` (native async, not sync wrapper)
4. ClaudeCLI uses `asyncio.create_subprocess_exec()` (not `subprocess.run()`)
5. DSPy uses `await predictor.acall()` (native async)
6. All existing tests pass with pytest-asyncio

### Phase 12: Parallel Deps + Migration ⚠️
**Goal**: Independent deps on the same node resolve concurrently. Full test suite, ootd.py, and E2E pass.
**Depends on**: Phase 11
**Requirements**: PDEP-01 through PDEP-05, MIG-01 through MIG-03
**Plans:** 4 plans executed — **MIG-03 failing** (fill() returns dict instead of nested Pydantic model in E2E)

Plans:
- [x] 12-01-PLAN.md — Async resolve_fields + resolve_dep with topo-sort gather (resolver.py)
- [x] 12-02-PLAN.md — Graph run/arun split + callers update (graph.py, compiler.py, cli.py, ootd.py)
- [x] 12-03-PLAN.md — Test migration: graph.run -> graph.arun, resolver tests async (~9 test files)
- [x] 12-04-PLAN.md — TDD new parallel-dep tests (concurrent gather, sync/async mixing, fail-fast)

**Success Criteria:**
1. `resolve_fields()` and `resolve_dep()` are async
2. Independent deps on the same node fire via `asyncio.gather()`
3. `Dep(sync_fn)` and `Dep(async_fn)` both work (runtime detection via `inspect.iscoroutinefunction`)
4. Dep DAG topological ordering still enforced — dependent deps resolve in order, independent deps resolve in parallel
5. Per-run dep caching is race-condition-free under concurrent resolution
6. examples/ootd.py works with async graph.run()
7. E2E tests pass with async backends

### Phase 13: Fix Nested Model Construction in Fill
**Goal**: fill() correctly constructs nested Pydantic models from LLM JSON output. E2E test `test_anticipate_has_llm_filled_vibe` passes.
**Depends on**: Phase 12
**Requirements**: MIG-03
**Gap Closure**: Closes gap from v3.0 milestone audit
**Plans:** TBD

**Success Criteria:**
1. `fill()` returns properly constructed nested Pydantic model instances (not raw dicts)
2. E2E test `test_anticipate_has_llm_filled_vibe` passes — `anticipate.vibe` is `VibeCheck` instance
3. All 5 E2E tests pass with `--run-e2e`
4. Full test suite (344+) passes, 0 regressions

---

## Key Decisions

- Full async, not threading — correct long-term play
- DSPy has native async (Predict.acall) — no asyncio.to_thread() needed
- PydanticAI is async-native — just swap run_sync() to await run()
- pytest-asyncio already configured with asyncio_mode="auto"
- Dep(callable) supports both sync and async — detect at runtime
- Node.__call__() becomes async — user custom __call__ must also be async
- CLI boundary: asyncio.run() wraps async graph.run() in Typer commands
- Subgraph composition is emergent — Dep(fn) where fn runs a graph, no special support
- Dynamic fan-out (runtime N) punted — async __call__ with manual gather is the escape hatch
- Declarative fan-out (DepMap etc) deferred until real use case demands it

## Conversion Scope

| File | Methods -> async | Difficulty |
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
