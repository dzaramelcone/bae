---
phase: 28-input-gates
plan: 03
subsystem: repl, toolbar
tags: [toolbar-widget, gate-routing, cross-mode-input, shush-toggle]

# Dependency graph
requires:
  - phase: 28-input-gates
    plan: 01
    provides: InputGate, gate registry on GraphRegistry (create/resolve/query/cancel)
provides:
  - Toolbar gates badge widget (make_gates_widget)
  - Cross-mode @g<id> <value> gate resolution from PY/BASH/GRAPH modes
  - shush_gates toggle on CortexShell
  - _resolve_gate_input method with Pydantic TypeAdapter validation
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cross-mode pre-dispatch routing: intercept @g prefix before mode-specific handlers"
    - "Pydantic TypeAdapter for runtime gate value coercion"

key-files:
  created: []
  modified:
    - bae/repl/toolbar.py
    - bae/repl/shell.py
    - tests/repl/test_toolbar.py
    - tests/repl/test_graph_commands.py

key-decisions:
  - "Gate routing only from non-NL modes -- NL preserves @label session routing"
  - "Pydantic TypeAdapter for gate value coercion -- reuses existing dependency, handles bool/int/str/etc"
  - "Shush toggle is a GRAPH mode command, not a key binding -- consistent with command dispatch"
  - "Gates widget positioned between tasks and mem in toolbar order"

patterns-established:
  - "Pre-dispatch routing: cross-mode commands intercept before mode switch block"
  - "TypeAdapter coercion for user input to typed gate fields"

# Metrics
duration: 8min
completed: 2026-02-15
---

# Phase 28 Plan 03: Shell UX -- Toolbar Badge, Cross-Mode Gate Routing, and Shush Toggle Summary

**Toolbar badge for pending gate count, @g prefix resolves gates from any non-NL mode, shush command toggles inline notifications**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-15T22:52:55Z
- **Completed:** 2026-02-15T23:00:58Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Toolbar displays pending gate count as magenta badge (hidden when zero, singular/plural)
- @g<id> <value> prefix resolves gates from PY, BASH, and GRAPH modes with Pydantic type coercion
- NL mode @g prefix preserved for session routing (no conflict)
- Shush toggle via `shush` command in GRAPH mode controls inline notification verbosity

## Task Commits

Each task was committed atomically:

1. **Task 1: Toolbar gates badge widget** - `7a2630c` (feat)
2. **Task 2: Cross-mode @g routing and shush toggle** - `331fdc2` (feat)

## Files Created/Modified
- `bae/repl/toolbar.py` - Added make_gates_widget factory for pending gate count badge
- `bae/repl/shell.py` - Gates widget registration, @g pre-dispatch routing, _resolve_gate_input, shush toggle, toolbar.gates style
- `tests/repl/test_toolbar.py` - 3 tests for gates widget (hidden, plural, singular)
- `tests/repl/test_graph_commands.py` - 4 tests for gate resolution (bool, not found, invalid type, NL mode preservation)

## Decisions Made
- Gate routing only from non-NL modes: NL mode uses @label for session routing, so @g1 in NL mode routes to AI session "g1" not gate g1 -- this is correct behavior
- Pydantic TypeAdapter for gate value coercion: already a project dependency, handles bool("true")->True, int("42")->42, str passthrough
- Shush toggle as GRAPH mode command: consistent with existing command dispatch pattern, not a key binding
- Gates widget between tasks and mem: visual priority puts activity indicators together

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three plans in Phase 28 (Input Gates) complete pending Plan 02 (engine interception)
- Plan 02 can use shush_gates attribute for notification suppression
- Gate resolution UX fully wired: toolbar shows count, @g resolves from any mode

---
*Phase: 28-input-gates*
*Completed: 2026-02-15*
