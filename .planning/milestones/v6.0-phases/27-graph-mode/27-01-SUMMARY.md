---
phase: 27-graph-mode
plan: 01
subsystem: api
tags: [graph, factory, callable, inspect, engine, coroutine]

# Dependency graph
requires:
  - phase: 26-engine-foundation
    provides: GraphRegistry, GraphRun, TimingLM, TaskManager integration
provides:
  - "graph() factory function returning typed async callable"
  - "submit_coro() for pre-built coroutine submission with lifecycle tracking"
  - "GraphRun.result field for post-execution inspection"
  - "ootd as free-standing async callable in examples/ootd.py"
affects: [27-02-PLAN, graph-mode-commands, repl-shell]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Factory function returning closure with typed inspect.Signature"
    - "submit_coro() for wrapping pre-built coroutines with lifecycle tracking"

key-files:
  created: []
  modified:
    - bae/graph.py
    - bae/__init__.py
    - bae/repl/engine.py
    - examples/ootd.py
    - examples/run_ootd_traced.py
    - tests/test_graph.py
    - tests/repl/test_engine.py

key-decisions:
  - "graph() factory fully encapsulates Graph in closure, exposes only _name string on wrapper"
  - "All signature params are KEYWORD_ONLY matching arun's **kwargs pattern"
  - "submit_coro cannot inject TimingLM since LM is bound inside the coroutine"
  - "GraphRun.graph now optional (None for submit_coro runs)"

patterns-established:
  - "graph(start=NodeClass) as the public API for creating typed callables"
  - "wrapper._name for display name without leaking internals"

# Metrics
duration: 6min
completed: 2026-02-15
---

# Phase 27 Plan 01: Graph Factory and Engine Coroutine Support Summary

**graph() factory creates typed async callables from node graphs with inspect.Signature, engine gains submit_coro() for pre-built coroutine lifecycle tracking**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-15T16:59:33Z
- **Completed:** 2026-02-15T17:05:56Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- graph() factory in bae/graph.py creates async callables with typed signatures derived from start node's required plain fields
- Internal Graph fully encapsulated in closure -- only _name display string exposed on wrapper
- Engine stores GraphResult on completed runs and accepts pre-built coroutines via submit_coro()
- examples/ootd.py migrated to `ootd = graph(start=IsTheUserGettingDressed)` pattern
- 13 new tests covering factory behavior and engine enhancements

## Task Commits

Each task was committed atomically:

1. **Task 1: graph() factory function and ootd.py migration** - `e4b3e58` (feat)
2. **Task 2: Engine submit_coro and GraphRun result storage** - `39f6601` (feat)

## Files Created/Modified
- `bae/graph.py` - Added graph() factory function with typed signature building
- `bae/__init__.py` - Exported graph (lowercase) from bae package
- `bae/repl/engine.py` - Added submit_coro(), _wrap_coro(), GraphRun.result, optional graph field
- `examples/ootd.py` - Migrated to ootd = graph(start=IsTheUserGettingDressed)
- `examples/run_ootd_traced.py` - Updated for new callable API (asyncio.run + ootd())
- `tests/test_graph.py` - 7 new TestGraphFactory tests
- `tests/repl/test_engine.py` - 7 new tests for submit_coro and result storage (including 1 for _execute stores result)

## Decisions Made
- graph() factory fully encapsulates Graph in closure, exposes only _name string on wrapper -- matches must_haves
- All signature params are KEYWORD_ONLY matching arun's **kwargs pattern
- submit_coro cannot inject TimingLM since LM is already bound inside the coroutine -- acceptable tradeoff
- GraphRun.graph now Graph | None since submit_coro runs don't have a Graph reference
- Used hasattr(result, 'trace') check in _wrap_coro to detect GraphResult without import

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] FactoryEnd test node needed explicit terminal __call__**
- **Found during:** Task 1 (TestGraphFactory tests)
- **Issue:** FactoryEnd without explicit __call__ inherited Node.__call__ which delegates to lm.decide(), causing NotImplementedError with MockV2LM
- **Fix:** Added `async def __call__(self) -> None: ...` to FactoryEnd
- **Files modified:** tests/test_graph.py
- **Verification:** All factory tests pass
- **Committed in:** e4b3e58 (Task 1 commit)

**2. [Rule 1 - Bug] Updated examples/run_ootd_traced.py for new API**
- **Found during:** Task 1 (ootd.py migration)
- **Issue:** run_ootd_traced.py imported `graph` from examples.ootd and called `graph.run()` -- broken after migration
- **Fix:** Updated to import `ootd` and use `asyncio.run(ootd(...))` pattern
- **Files modified:** examples/run_ootd_traced.py
- **Verification:** File imports cleanly
- **Committed in:** e4b3e58 (Task 1 commit)

**3. [Rule 1 - Bug] Fixed coroutine-never-awaited warning in submit_coro test**
- **Found during:** Task 2 (engine tests)
- **Issue:** test_submit_coro_creates_running_graphrun used tm.shutdown() which left coroutine unfinished, producing RuntimeWarning
- **Fix:** Used asyncio.Event to wait for coroutine start, then explicit revoke_all + await
- **Files modified:** tests/repl/test_engine.py
- **Verification:** 24 engine tests pass with zero warnings
- **Committed in:** 39f6601 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 bug fixes, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- graph() factory and engine coroutine support ready for Plan 02 (GRAPH mode commands)
- GRAPH mode `run <expr>` can now submit callable results via submit_coro()
- inspect/trace commands can read GraphResult from GraphRun.result
- Note: bae CLI `bae graph show examples.ootd` (without :class syntax) no longer finds a Graph instance in examples/ootd -- users should use `bae graph show examples.ootd:IsTheUserGettingDressed`

## Self-Check: PASSED

- All 8 must_have artifacts verified
- All 7 created/modified files exist on disk
- Both task commits (e4b3e58, 39f6601) verified in git log
- 609 tests pass (596 original + 13 new), 5 skipped
- All 4 plan verification steps pass

---
*Phase: 27-graph-mode*
*Completed: 2026-02-15*
