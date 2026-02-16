---
phase: 28-input-gates
plan: 02
subsystem: engine, graph-commands, resolver
tags: [gate, asyncio-future, input-gate, type-coercion, pydantic-typeadapter, graph-mode]

# Dependency graph
requires:
  - phase: 28-input-gates-01
    provides: Gate marker, InputGate dataclass, WAITING state, gate registry
provides:
  - Gate-aware resolve_fields with GATE_HOOK_KEY hook mechanism
  - Engine gate interception: WAITING/RUNNING state transitions during gate resolution
  - GRAPH mode `input <id> <value>` command with Pydantic type coercion
  - GRAPH mode `gates` command showing pending gate schema
  - Notify callback for inline gate creation events
affects: [28-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Gate hook injected via dep_cache[GATE_HOOK_KEY] -- same pattern as LM_KEY"
    - "Gate results cached per node class to prevent double-trigger on re-resolve"
    - "Pydantic TypeAdapter for gate value coercion in input command"
    - "_make_notify factory with shush_gates defensive getattr"

key-files:
  created: []
  modified:
    - bae/resolver.py
    - bae/repl/engine.py
    - bae/repl/graph_commands.py
    - tests/repl/test_engine.py
    - tests/repl/test_graph_commands.py

key-decisions:
  - "GATE_HOOK_KEY sentinel in resolver.py alongside LM_KEY -- avoids circular import from engine"
  - "Gate results cached per (node_cls, 'gates') key to prevent re-triggering when arun re-resolves fields"
  - "cancel command accepts WAITING state alongside RUNNING for correct gate cleanup"
  - "Pydantic TypeAdapter for type coercion -- validates raw string input against gate field type"
  - "_make_notify uses getattr(shell, 'shush_gates', False) for defensive forward-compat"

patterns-established:
  - "dep_cache hook injection: GATE_HOOK_KEY follows LM_KEY pattern for extending resolve_fields"
  - "Gate result caching: (node_cls, 'gates') tuple key prevents double-resolve in arun loop"

# Metrics
duration: 11min
completed: 2026-02-15
---

# Phase 28 Plan 02: Engine Gate Interception and Input Command Summary

**Gate-aware resolve_fields with dep_cache hook, WAITING/RUNNING state machine, GRAPH mode input/gates commands with Pydantic type coercion**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-15T22:52:47Z
- **Completed:** 2026-02-15T23:04:18Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Gate hook mechanism injected into resolve_fields via dep_cache, creating InputGates and suspending execution until user resolves
- Engine transitions WAITING when gates pending, resumes RUNNING when all resolved via asyncio.gather
- GRAPH mode `input <id> <value>` command with Pydantic TypeAdapter validation and type coercion
- GRAPH mode `gates` command listing all pending gates with node type and schema display
- Notify callback wired into submit path for inline gate creation events

## Task Commits

Each task was committed atomically:

1. **Task 1: Engine gate interception in _execute** - `331fdc2` (feat) -- pre-existing from prior session
2. **Task 2: GRAPH mode input command with type coercion and notification** - `35a8238` (feat)

## Files Created/Modified
- `bae/resolver.py` - GATE_HOOK_KEY sentinel, gate field detection in resolve_fields, gate result caching
- `bae/repl/engine.py` - _gate_hook inside _execute, notify param on submit/submit_coro, GATE_HOOK_KEY import
- `bae/repl/graph_commands.py` - input/gates commands, _make_notify helper, notify wiring in _cmd_run
- `tests/repl/test_engine.py` - 5 gate hook tests: creation, resume, multi-gate, cancel, notify
- `tests/repl/test_graph_commands.py` - 7 input/gates tests: resolve, no args, invalid id, invalid type, string, empty, pending

## Decisions Made
- GATE_HOOK_KEY defined in resolver.py (not engine.py) to avoid circular imports -- same module as LM_KEY
- Gate results cached per `(node_cls, "gates")` tuple key in dep_cache -- arun's main loop re-calls resolve_fields on each node after construction, and without caching the gate hook would fire twice creating duplicate gates that hang forever
- cancel command extended to accept WAITING state (Rule 1 fix) -- a waiting graph is logically running and should be cancellable
- Pydantic TypeAdapter used for type coercion instead of manual casting -- handles bool("true"), int("42"), and complex types uniformly
- _make_notify uses `getattr(shell, 'shush_gates', False)` for defensive access since shush_gates attribute is added by Plan 28-03

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Gate result caching to prevent double-trigger in arun loop**
- **Found during:** Task 1 (engine gate interception)
- **Issue:** Graph.arun() calls resolve_fields twice for each node -- once during make/decide target construction and once on the main loop's field resolution. Without caching, the gate hook fires twice creating duplicate gates whose second set of Futures are never resolved, causing a permanent hang.
- **Fix:** Added `gate_cache_key = (node_cls, "gates")` in resolve_fields that caches gate results per node class in dep_cache. Second call returns cached values without invoking the hook.
- **Files modified:** bae/resolver.py
- **Verification:** Diagnostic confirmed graph completes: WAITING -> resolve -> DONE
- **Committed in:** 331fdc2 (Task 1, pre-existing)

**2. [Rule 1 - Bug] Cancel command accepts WAITING state**
- **Found during:** Task 1 (engine gate interception)
- **Issue:** _cmd_cancel only checked `run.state != GraphState.RUNNING`, rejecting cancellation of WAITING graphs. A graph suspended at a gate should be cancellable.
- **Fix:** Changed condition to `run.state not in (GraphState.RUNNING, GraphState.WAITING)`
- **Files modified:** bae/repl/graph_commands.py
- **Verification:** test_gate_cancel_during_waiting passes
- **Committed in:** 331fdc2 (Task 1, pre-existing)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes essential for correct gate lifecycle. No scope creep.

## Issues Encountered
- Task 1 work was already committed in a prior session (commits 331fdc2 and 7a2630c labeled as 28-03). The engine gate hook, resolver changes, and gate hook tests were already in HEAD. Task 2 (input/gates commands) was the remaining work.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- End-to-end gate suspension and resolution works: graph pauses at Gate fields, user resolves via `input` command, graph resumes
- Plan 03 (shell integration) can use the notify callback pattern and shush_gates toggle
- The `@g` cross-mode gate routing already exists in shell.py (from prior 28-03 commits)

## Self-Check: PASSED

All files, commits, and content verified.

---
*Phase: 28-input-gates*
*Completed: 2026-02-15*
