---
phase: 20-ai-eval-loop
plan: 03
subsystem: repl
tags: [ai, eval-loop, code-extraction, async-exec, feedback, multi-session, concurrent]

# Dependency graph
requires:
  - phase: 18-ai-agent
    provides: "AI class with Claude CLI subprocess, session persistence, extract_code"
  - phase: 20-01
    provides: "Rich markdown rendering for AI channel output"
  - phase: 20-02
    provides: "Multi-session AI management, @N prefix routing, cross-session memory"
provides:
  - "AI eval loop: extract code -> execute in namespace -> feed results back"
  - "AI._send() method for subprocess communication (extracted from __call__)"
  - "max_eval_iters parameter preventing infinite recursion"
  - "Coroutine awaiting inline in eval loop (not fire-and-forget)"
  - "Concurrent session routing verified via integration tests"
affects: [ai-streaming, ai-bash-dispatch]

# Tech tracking
tech-stack:
  added: []
  patterns: ["eval-loop-inside-__call__ for self-contained agent iteration", "BaseException catch with CancelledError/KeyboardInterrupt/SystemExit passthrough"]

key-files:
  created: []
  modified:
    - bae/repl/ai.py
    - tests/repl/test_ai.py
    - tests/repl/test_ai_integration.py

key-decisions:
  - "Eval loop runs inside AI.__call__, not in shell dispatch -- keeps it self-contained and testable"
  - "CancelledError propagates out of eval loop (not caught); all other exceptions fed back as traceback"
  - "Coroutines from async_exec awaited inline in eval loop (eval loop needs results, unlike shell PY dispatch)"
  - "BaseException catch with explicit CancelledError/KeyboardInterrupt/SystemExit passthrough"

patterns-established:
  - "Eval loop pattern: respond -> extract_code -> async_exec -> feed back -> respond, up to max_eval_iters"
  - "_send() extracted as reusable subprocess communication method (prompt in, response out)"

# Metrics
duration: 3min
completed: 2026-02-14
---

# Phase 20 Plan 03: AI Eval Loop Summary

**Extract-execute-feedback loop in AI.__call__ with inline coroutine awaiting, iteration limit, and concurrent session routing tests**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-14T12:47:47Z
- **Completed:** 2026-02-14T12:51:04Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- AI.__call__ implements eval loop: extract Python code blocks -> execute via async_exec -> feed results back -> repeat until no code or limit
- Subprocess logic extracted into AI._send() for clean separation of concerns
- max_eval_iters (default 5) prevents infinite recursion
- Coroutines from async_exec awaited inline (eval loop needs the result, not fire-and-forget)
- CancelledError propagates out; all other exceptions caught and fed back as traceback for AI self-correction
- Concurrent AI sessions verified: two sessions via asyncio.gather mutate shared namespace correctly
- @N prefix routing verified: creates sessions, switches, sticky on follow-up, switches back
- 233/233 repl tests pass, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Eval loop in AI.__call__** - `6ea6b37` (feat)
2. **Task 2: Concurrent session routing tests** - `a2faeff` (feat)

## Files Created/Modified
- `bae/repl/ai.py` - Eval loop in __call__, extracted _send(), max_eval_iters param, import async_exec and traceback
- `tests/repl/test_ai.py` - 7 new eval loop unit tests (no-code, extraction, feedback, limit, coroutine, error, cancellation)
- `tests/repl/test_ai_integration.py` - 5 new integration tests (concurrent namespace, router labels, @N prefix routing)

## Decisions Made
- Eval loop runs inside AI.__call__, not in shell dispatch -- self-contained, testable, matches research anti-pattern guidance
- CancelledError propagates out of eval loop (not caught); all other exceptions fed back as traceback string
- Coroutines from async_exec awaited inline in eval loop (eval loop needs results, unlike shell PY dispatch which fires via TaskManager)
- BaseException catch with explicit CancelledError/KeyboardInterrupt/SystemExit passthrough covers all error types

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- AI eval loop complete -- AI can now extract code from its own responses, execute it, and iterate based on results
- All Phase 20 plans complete (01: display layer, 02: multi-session, 03: eval loop)
- Deferred: AI bash dispatch (Claude XML tool calls need parsing) -- beyond v4.0
- Deferred: AI streaming/progressive display for NL responses

## Self-Check: PASSED

All files found. All commits found. Summary verified.

---
*Phase: 20-ai-eval-loop*
*Completed: 2026-02-14*
