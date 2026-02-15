---
phase: 30-agent-core-extraction
plan: 01
subsystem: agent
tags: [agent-loop, eval-loop, async, claude-cli, extraction]

requires: []
provides:
  - "extract_executable() -- regex <run> block extraction from LM text"
  - "agent_loop() -- multi-turn eval loop decoupled from REPL"
  - "_agent_namespace() -- fresh namespace for headless agent execution"
  - "_cli_send() -- Claude CLI subprocess with session persistence"
affects: [30-02, repl-ai-refactor, agentic-backend]

tech-stack:
  added: []
  patterns: ["function-based agent core (not class)", "send-function injection for transport abstraction"]

key-files:
  created: [bae/agent.py, tests/test_agent.py]
  modified: []

key-decisions:
  - "Agent core as module-level functions, not a class -- loop is stateless per invocation"
  - "_cli_send takes session_id and call_count as params -- session state owned by caller"
  - "No httpx in _agent_namespace -- not a guaranteed project dependency"

patterns-established:
  - "send-function injection: agent_loop takes async send callable, transport-agnostic"
  - "namespace isolation: _agent_namespace returns fresh dict per call"

duration: 3min
completed: 2026-02-15
---

# Phase 30 Plan 01: Agent Core Extraction Summary

**Multi-turn eval loop extracted from REPL AI into standalone bae/agent.py with send-function injection**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T14:25:33Z
- **Completed:** 2026-02-15T14:28:30Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Extracted eval loop core from bae/repl/ai.py into bae/agent.py as pure functions
- agent_loop decoupled from REPL concerns (no router, store, label, session management)
- 8 unit tests covering extract_executable, agent_loop, and _agent_namespace
- Full test suite (571 tests) passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create bae/agent.py with core agent functions**
   - `e0da055` (test: add failing tests for agent core -- TDD RED)
   - `032fbbe` (feat: implement core agent loop -- TDD GREEN)

## Files Created/Modified
- `bae/agent.py` -- Core agent loop: extract_executable, agent_loop, _agent_namespace, _cli_send
- `tests/test_agent.py` -- 8 unit tests for agent core functions

## Decisions Made
- Agent core as module-level functions, not a class -- the eval loop is stateless per invocation, namespace and send function injected per call
- _cli_send takes session_id and call_count as explicit params rather than managing internal state -- session ownership belongs to the caller (REPL AI or AgenticBackend)
- Excluded httpx from _agent_namespace since it may not be a project dependency

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- bae/agent.py ready for Plan 02 (AgenticBackend + REPL AI refactor)
- REPL AI can be refactored to wrap agent_loop for <run> block handling
- AgenticBackend can use agent_loop + _cli_send for tool-augmented fill()

---
*Phase: 30-agent-core-extraction*
*Completed: 2026-02-15*
