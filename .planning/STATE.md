# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-15)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v6.0 Graph Runtime -- Phase 26 Engine Foundation complete

## Current Position

Phase: 26 (Engine Foundation) -- COMPLETE
Plan: 02 of 02 complete
Status: Phase 26 complete, ready for Phase 27
Last activity: 2026-02-15 -- 26-02 GraphRegistry + TimingLM + shell integration

Progress: v1-v5 done | v6.0 [###.......] 15%

## Performance Metrics

**Velocity:**
- Total plans completed: 85 (13 v1.0 + 21 v2.0 + 9 v3.0 + 24 v4.0 + 9 v5.0 + 9 work)
- v1.0 duration: 1 day (2026-02-04 -> 2026-02-05)
- v2.0 duration: 2 days (2026-02-07 -> 2026-02-08)
- v3.0 duration: 5 days (2026-02-04 -> 2026-02-09)
- v4.0 duration: 2 days (2026-02-13 -> 2026-02-14)
- v5.0 duration: 1 day (2026-02-14)

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 26-02 | GraphRegistry + TimingLM + shell | 5min | 2 | 3 |
| 30-02 | AgenticBackend + AI refactor | 3min | 2 | 5 |
| 30-01 | Agent Core | 2min | 1 | 2 |
| 26-01 | dep_cache + hardening | 3min | 1 | 3 |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

- 26-02: TimingLM passed as both lm and dep_cache[LM_KEY] to arun() -- graph uses lm directly for routing
- 26-02: TimingLM times fill/make (node-producing), not choose_type/decide (routing)
- 26-02: GRAPH dispatch calls await _run_graph() directly; engine handles own task submission
- 30-02: REPL AI keeps interleaved tool-tag + run-block loop; agent_loop only for AgenticBackend
- 30-02: Lazy import of async_exec in agent.py to break circular import chain
- 30-02: AgenticBackend delegates choose_type/make/decide to wrapped ClaudeCLIBackend
- 30-01: Agent core as module-level functions, not class -- stateless per invocation
- 30-01: _cli_send takes session_id/call_count as params -- caller owns session state
- 26-01: Internal dep_cache variable renamed to cache to avoid parameter shadowing
- 26-01: CancelledError handled separately from TimeoutError (re-raises directly)
- 26-01: await process.wait() added after process.kill() for both error paths in _run_cli_json

### Pending Todos

- Update `tests/traces/json_structured_fill_reference.py` -- drifted from real backend
- Bump Python requirement to 3.14 stable
- AI streaming/progressive display for NL responses
- Session store: conversation indexing agent

### Blockers/Concerns

None.

### Roadmap Evolution

- Phase 30 added: Agent Core Extraction

### Research Notes (v6.0)

- Phase 28 (Input Gates) flagged for deeper research: Future-based prompt + dep_cache injection + concurrent routing
- Python 3.14 `asyncio.capture_call_graph()` available for Phase 29 observability
- Zero new dependencies required for entire milestone
- Critical pitfall: input gate deadlock if graphs call `TerminalPrompt.ask()` -- must use Future-based CortexPrompt

## Session Continuity

Last session: 2026-02-15
Stopped at: Completed 26-02-PLAN.md, Phase 26 complete
Branch: main
Resume file: None
