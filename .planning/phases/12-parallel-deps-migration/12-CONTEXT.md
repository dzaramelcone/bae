# Phase 12: Parallel Deps + Migration - Context

**Gathered:** 2026-02-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Make independent deps on the same node resolve concurrently via `asyncio.gather()`. Support both sync and async dep callables via single `Dep()` marker with runtime detection. Restore sync `run()` API with async `arun()` escape hatch. Full test suite, ootd.py, and E2E pass.

</domain>

<decisions>
## Implementation Decisions

### Sync/async dep coexistence
- Single `Dep()` marker for both sync and async callables — runtime detection via `inspect.iscoroutinefunction`
- Sync dep functions wrapped in thin coroutine wrapper (`async def w(): return fn()`) — NOT `asyncio.to_thread()`
- Async dep functions receive already-resolved values (plain values, not awaitables) — same contract as current sync behavior
- `resolve_dep()` is always `async def` — uniform internal contract

### Concurrency boundaries
- `TopologicalSorter.prepare()` + `get_ready()` for level-by-level resolution — each level gathered, results cached, next level dispatched
- Each topo level is a set of unique callables — deduplication is inherent, no redundant execution
- No concurrency limit (no semaphore) — all ready deps in a level fire via single `asyncio.gather()`
- Per-run dep cache is a plain dict — topo-sort ordering guarantees no races (transitive deps always resolved in earlier level)
- No locks needed — structural correctness from topo ordering
- Recall fields resolved concurrently with dep fields (recalls search trace, no dep dependency)
- Same type-hint-based dep injection pattern for async dep functions — `Annotated[T, Dep(fn)]` on parameters
- Manual `asyncio.gather()` inside `async __call__` is the escape hatch for dynamic fan-out

### Error propagation under gather
- Fail fast — first exception cancels remaining tasks (`asyncio.gather(return_exceptions=False)`)
- First error propagates as-is (no ExceptionGroup wrapping)
- Dep function exceptions wrapped in `DepError(node_type, field_name, cause=original)` — consistent with Phase 7 structured exceptions
- If any dep in a topo level fails, stop the whole DAG — no partial resolution of downstream levels

### Migration strategy
- `resolve_dep()` and `resolve_fields()` converted to async in-place — no dual sync/async versions
- `Graph.run()` rolled back to sync (uses `asyncio.run()` internally) — better public API for users who don't care about async
- `Graph.arun()` added as native async version for callers already in an event loop
- Existing sync dep functions in tests and ootd.py: mix of sync and async — some stay sync to prove wrapping works, some migrated to async to test that path
- `ootd.py` uses `graph.run()` (sync) at top level
- Targeted new tests for: gather behavior, sync/async dep mixing, concurrent caching correctness, fail-fast cancellation, DepError wrapping

### Claude's Discretion
- Internal implementation of the thin coroutine wrapper for sync deps
- Whether `resolve_fields` internally separates dep and recall resolution or gathers everything at once
- Exact test count and granularity for new parallel-dep tests
- How `arun()` and `run()` share implementation (likely `run()` calls `asyncio.run(self.arun(...))`)

</decisions>

<specifics>
## Specific Ideas

- Dep deduplication within a topo level is structural (set from `get_ready()`), not a filtering step — leverage what `TopologicalSorter` already provides
- The `run()` / `arun()` naming follows the aiohttp/langchain convention (`arun` not `run_async`)
- Phase 11 made `run()` async — Phase 12 rolls that back. This is intentional: sync-by-default is a better public API

</specifics>

<deferred>
## Deferred Ideas

- Concurrency limits (semaphore for rate-limited backends) — add when a real use case demands it
- Dynamic fan-out framework support (DepMap, etc.) — manual gather in `__call__` is the escape hatch for now
- Declarative fan-out annotations — deferred until real use case

</deferred>

---

*Phase: 12-parallel-deps-migration*
*Context gathered: 2026-02-08*
