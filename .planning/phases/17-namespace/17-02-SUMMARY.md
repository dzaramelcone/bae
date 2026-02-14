---
phase: 17-namespace
plan: 02
subsystem: repl
tags: [namespace, shell-wiring, trace-capture, integration-tests, repl]

requires:
  - phase: 17-namespace-01
    provides: seed() namespace factory and NsInspector callable class
  - phase: 16-channel-io
    provides: ChannelRouter for output routing and channel_arun wrapper
  - phase: 14-repl
    provides: CortexShell with self.namespace dict and async_exec
provides:
  - CortexShell uses seed() for namespace initialization with all bae types
  - _trace capture in namespace after successful graph runs
  - _trace capture from exception.trace on failed graph runs
  - Error routing through [graph] channel for GRAPH mode
  - Integration test suite verifying full namespace wiring
affects: [18-nl-mode]

tech-stack:
  added: []
  patterns: [namespace-wiring, trace-capture-on-error]

key-files:
  created:
    - tests/repl/test_namespace_integration.py
  modified:
    - bae/repl/shell.py

key-decisions:
  - "Kept asyncio and os imports in shell.py -- asyncio needed for Task type hint and gather, os needed for toolbar cwd display"
  - "GRAPH mode error handler captures _trace then routes traceback through [graph] channel (matches PY mode error pattern)"

patterns-established:
  - "Trace capture pattern: store trace in namespace on success, extract from exception.trace on error"

duration: 2min
completed: 2026-02-13
---

# Phase 17 Plan 02: Shell Namespace Wiring Summary

**seed() replaces inline namespace dict in CortexShell with _trace capture on graph success and error, verified by 12 integration tests**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-14T00:35:57Z
- **Completed:** 2026-02-14T00:38:25Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- CortexShell.__init__ uses seed() instead of inline dict -- Node, Graph, Dep, Recall, ns all available without import
- GRAPH mode captures _trace in namespace after successful graph runs (result.trace)
- GRAPH mode captures _trace from exception.trace on failed graph runs (partial trace preservation)
- Error routing added to GRAPH mode handler -- tracebacks route through [graph] channel matching PY mode pattern
- 12 integration tests covering namespace seeding, _ capture, _trace capture (success + error), and ns() callable
- 114/114 REPL tests pass (zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire seed() into shell and capture _trace** - `e2e1cee` (feat)
2. **Task 2: Integration tests for namespace wiring** - `2260814` (test)

## Files Created/Modified
- `bae/repl/shell.py` - Replaced inline namespace dict with seed(), added _trace capture and GRAPH error routing
- `tests/repl/test_namespace_integration.py` - 12 integration tests for full namespace wiring (208 lines)

## Decisions Made
- **Kept asyncio and os imports:** asyncio is needed for asyncio.Task type hint and asyncio.gather in _shutdown; os is needed for os.getcwd() and os.path.expanduser() in toolbar. seed() also provides them in namespace, but shell.py uses them directly.
- **GRAPH error routing through channel:** Added try/except around channel_arun in GRAPH mode that formats traceback and routes through router.write("graph", ...) matching the existing PY mode error pattern. This ensures GRAPH mode errors are visible and recorded.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All four namespace success criteria from the roadmap are now satisfied:
  - NS-01: Node, Graph, Dep, Recall available without import
  - NS-02: _ holds last expression result, _trace holds last graph trace
  - NS-03: ns() callable for namespace introspection
- 114/114 REPL tests pass across all modules (test_exec, test_store, test_channels, test_namespace, test_namespace_integration, test_store_integration)
- Phase 17 (Namespace) is complete -- ready for Phase 18 (NL Mode)

## Self-Check: PASSED

- [x] bae/repl/shell.py exists
- [x] tests/repl/test_namespace_integration.py exists
- [x] 17-02-SUMMARY.md exists
- [x] Commit e2e1cee (Task 1) exists
- [x] Commit 2260814 (Task 2) exists
- [x] Namespace seeded correctly (Node, ns present)
- [x] 12/12 integration tests pass
- [x] 114/114 total REPL tests pass (zero regressions)

---
*Phase: 17-namespace*
*Completed: 2026-02-13*
