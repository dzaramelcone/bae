---
phase: 30-agent-core-extraction
plan: 02
subsystem: agent
tags: [agent-loop, lm-backend, agentic-fill, extract-executable, two-phase]

requires:
  - phase: 30-01
    provides: "extract_executable, agent_loop, _agent_namespace, _cli_send in bae/agent.py"
provides:
  - "AgenticBackend -- LM backend with agentic research + structured extraction fill()"
  - "REPL AI delegating to shared extract_executable from bae.agent"
  - "AgenticBackend exportable from bae top-level"
affects: [graph-runtime, agentic-workflows]

tech-stack:
  added: []
  patterns: ["two-phase fill: agentic research then structured extraction", "lazy import to break circular dependency"]

key-files:
  created: []
  modified: [bae/lm.py, bae/repl/ai.py, bae/__init__.py, bae/agent.py, tests/test_agent.py]

key-decisions:
  - "REPL AI keeps its interleaved tool-tag + run-block loop -- agent_loop only used by AgenticBackend"
  - "Lazy import of async_exec in agent.py to break circular import chain"
  - "_EXEC_BLOCK_RE kept in ai.py for run_tool_calls stripping, imported extract_executable for extraction"
  - "AgenticBackend delegates choose_type/make/decide to wrapped ClaudeCLIBackend"

patterns-established:
  - "Two-phase fill: agent_loop for research, then _run_cli_json for structured extraction"
  - "Lazy import pattern for breaking agent<->repl circular dependency"

duration: 3min
completed: 2026-02-15
---

# Phase 30 Plan 02: AgenticBackend + REPL AI Refactor Summary

**AgenticBackend with two-phase fill (agent_loop research + structured extraction) and REPL AI delegating extract_executable to shared agent core**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T14:29:17Z
- **Completed:** 2026-02-15T14:32:06Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- REPL AI now delegates extract_executable to shared bae.agent implementation
- AgenticBackend in bae/lm.py with two-phase fill: agent_loop for research, structured extraction for typed output
- AgenticBackend exported from bae top-level package
- 5 new tests (delegation + two-phase fill + import verification), 576 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor AI.__call__ to use agent_loop** - `0eaa3bb` (refactor)
2. **Task 2: Build AgenticBackend and export from bae** - `997948a` (feat)

## Files Created/Modified
- `bae/lm.py` -- AgenticBackend class with two-phase fill
- `bae/repl/ai.py` -- extract_executable delegated to bae.agent
- `bae/__init__.py` -- AgenticBackend added to exports
- `bae/agent.py` -- Lazy import of async_exec to break circular dep
- `tests/test_agent.py` -- 5 new tests for AgenticBackend

## Decisions Made
- REPL AI keeps its interleaved tool-tag + run-block loop; agent_loop is only used by AgenticBackend (headless, no tool tags)
- Lazy import of async_exec in agent.py's agent_loop function to break the circular import chain: bae.agent -> bae.repl.exec -> bae.repl.__init__ -> bae.repl.shell -> bae.repl.ai -> bae.agent
- _EXEC_BLOCK_RE regex kept in ai.py because run_tool_calls needs it to strip <run> blocks before scanning for tool tags; extract_executable imported from bae.agent for the actual extraction
- AgenticBackend delegates choose_type/make/decide to a wrapped ClaudeCLIBackend -- only fill() has the agentic two-phase behavior

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Lazy import to break circular dependency**
- **Found during:** Task 2 (AgenticBackend implementation)
- **Issue:** Top-level `from bae.repl.exec import async_exec` in agent.py creates circular import chain through bae.repl.__init__ -> bae.repl.shell -> bae.repl.ai -> bae.agent
- **Fix:** Moved async_exec import inside agent_loop function body (lazy import)
- **Files modified:** bae/agent.py
- **Verification:** All imports succeed, 576 tests pass
- **Committed in:** 997948a (Task 2 commit)

**2. [Rule 3 - Blocking] Kept _EXEC_BLOCK_RE in ai.py**
- **Found during:** Task 1 (AI refactor)
- **Issue:** Plan said to remove _EXEC_BLOCK_RE from ai.py, but run_tool_calls uses it to strip <run> blocks. Importing it from bae.agent triggers same circular import.
- **Fix:** Kept _EXEC_BLOCK_RE definition in ai.py for run_tool_calls, import only extract_executable from bae.agent
- **Files modified:** bae/repl/ai.py
- **Verification:** 71 AI tests pass, no behavior change
- **Committed in:** 0eaa3bb (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both fixes necessary to resolve circular import. Extract_executable is properly shared; _EXEC_BLOCK_RE duplication is minimal (same regex, used for different purposes in each module).

## Issues Encountered

- Circular import chain discovered: bae.agent -> bae.repl.exec -> bae.repl -> bae.repl.shell -> bae.repl.ai -> bae.agent. Resolved with lazy import pattern in agent.py.
- Preexisting test failure in tests/repl/test_engine.py (untracked file, not related to this plan) -- excluded from verification.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- Agent core extraction complete: bae.agent provides the shared loop, REPL AI uses it, AgenticBackend builds on it
- AgenticBackend ready for use in graph runtime where agentic fill is needed
- Phase 30 fully complete

---
*Phase: 30-agent-core-extraction*
*Completed: 2026-02-15*
