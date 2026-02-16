# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-15)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v6.0 Graph Runtime -- Phase 29 Observability complete

## Current Position

Phase: 29 (Observability)
Plan: 03 of 03 complete
Status: Phase 29 verified (3/3 must-haves passed)
Last activity: 2026-02-15 -- Phase 29 execution complete

Progress: v1-v5 done | v6.0 [##########] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 99 (13 v1.0 + 21 v2.0 + 9 v3.0 + 24 v4.0 + 9 v5.0 + 23 v6.0)
- v1.0 duration: 1 day (2026-02-04 -> 2026-02-05)
- v2.0 duration: 2 days (2026-02-07 -> 2026-02-08)
- v3.0 duration: 5 days (2026-02-04 -> 2026-02-09)
- v4.0 duration: 2 days (2026-02-13 -> 2026-02-14)
- v5.0 duration: 1 day (2026-02-14)

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 29-03 | Concurrent stress + store persistence | 2min | 2 | 1 |
| 29-02 | Display layer wiring: debug, lifecycle views, output policy | 3min | 2 | 5 |
| 29-01 | OutputPolicy + dep timing + RSS + events | 4min | 2 | 4 |
| 28-03 | Shell UX: badge, @g routing, shush | 8min | 2 | 4 |
| 28-01 | Gate marker + InputGate infrastructure | 3min | 2 | 6 |
| 27-06 | stdin isolation + inspect formatting | 3min | 2 | 3 |
| 27-04 | LM timeout, partial trace, flattened params | 5min | 3 | 7 |
| 27-05 | ANSI rendering fix for graph commands | 2min | 2 | 3 |
| 27-03 | Param type injection + ls removal | 2min | 2 | 3 |
| 27-02 | GRAPH mode command dispatcher | 3min | 2 | 3 |
| 27-01 | graph() factory + engine coroutine | 6min | 2 | 7 |
| 26-04 | Graph error pipeline fix | 1min | 2 | 3 |
| 26-03 | Instance guard + subprocess isolation | 1min | 1 | 3 |
| 26-02 | GraphRegistry + TimingLM + shell | 5min | 2 | 3 |
| 30-02 | AgenticBackend + AI refactor | 3min | 2 | 5 |
| 30-01 | Agent Core | 2min | 1 | 2 |
| 26-01 | dep_cache + hardening | 3min | 1 | 3 |
| 28-02 | Engine gate interception + input/gates commands | 11min | 2 | 5 |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

- 29-03: StressStart -> Middle -> End with asyncio.sleep simulates realistic concurrent load
- 29-03: QUIET + successful = zero events, validated via channel buffer and store count
- 29-03: Cross-session proof via two SessionStore instances on same db file
- 29-02: Notify shush applies only to gate events -- lifecycle always flows through
- 29-02: Output policy flags parsed from run arg via split/remove before eval
- 29-02: GraphRun.policy set at creation time in submit/submit_coro (not deferred)
- 29-02: Lifecycle events color-coded in UserView: dim=start, green=complete, red=fail, yellow=cancel
- 29-01: DEP_TIMING_KEY as dep_cache sentinel, matching GATE_HOOK_KEY pattern
- 29-01: notify signature evolved to (content, meta=None) -- backward compatible
- 29-01: RSS via resource.getrusage high-water mark, not tracemalloc (zero overhead)
- 29-01: OutputPolicy on GraphRun, set at submit time via policy kwarg
- 28-03: Gate routing only from non-NL modes -- NL preserves @label session routing
- 28-03: Pydantic TypeAdapter for gate value coercion -- reuses existing dependency
- 28-03: Shush toggle as GRAPH mode command, not key binding -- consistent with dispatch pattern
- 28-01: Gate marker is frozen dataclass with description field, matching Dep/Recall/Effect pattern
- 28-01: Gate fields classified as "gate" -- automatically excluded from LM plain model by existing equality check
- 28-01: InputGate uses asyncio.Future with schema metadata; gate IDs are run_id.counter format
- 28-01: cancel_gates called in both _execute and _wrap_coro CancelledError handlers
- 27-06: Name-based timing lookup with consumed-index -- start node has no timing entry (constructed from kwargs)
- 27-04: ClaudeCLIBackend timeout 20 -> 120s for reliable complex graph execution
- 27-04: Outer try/except around arun while-loop attaches .trace to any unhandled exception
- 27-04: graph() flattens BaseModel input fields into simple kwargs via _composites closure
- 27-04: _param_types removed -- flattened params eliminate need for REPL type injection
- 27-05: ANSI metadata on router.write rather than direct print -- preserves channel visibility and store recording
- 27-05: Type injection removed from _cmd_run -- graph callables handle param flattening directly
- 27-03: _param_types on graph() wrapper auto-injected into namespace by _cmd_run before eval
- 27-03: Type injection permanent (not per-run) -- domain types belong in user namespace
- 27-03: ls alias removed from GRAPH dispatch -- only canonical command names
- 27-02: dispatch_graph replaces _run_graph -- shell.py delegates entirely to graph_commands.py
- 27-02: run <expr> uses async_exec for namespace expression evaluation, supports coroutines and Graph objects
- 27-01: graph() factory fully encapsulates Graph in closure, exposes only _name string on wrapper
- 27-01: submit_coro cannot inject TimingLM since LM is bound inside the coroutine
- 27-01: GraphRun.graph now optional (None for submit_coro runs)
- 26-04: GRAPH mode submits with no extra kwargs -- Phase 27 adds run graph(field=val) syntax
- 26-04: Error surfacing via Task.add_done_callback reading run.error set before re-raise
- 26-03: isinstance(start, type) guard before self.start so _discover() never sees an instance
- 26-03: start_new_session=True added to _run_cli_json -- all subprocesses now isolated
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
- 28-02: GATE_HOOK_KEY in resolver.py alongside LM_KEY -- dep_cache hook injection for gate fields
- 28-02: Gate results cached per (node_cls, 'gates') to prevent double-trigger in arun resolve loop
- 28-02: Pydantic TypeAdapter for gate value coercion in input command

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
Stopped at: Phase 29 complete -- all 3 plans executed, verified 3/3
Branch: main
Resume file: None
