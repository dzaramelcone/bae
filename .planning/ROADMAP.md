# Roadmap: Bae

## Milestones

- v1.0 DSPy Compilation -- Phases 1-4 (shipped 2026-02-05)
- v2.0 Context Frames -- Phases 5-10 (shipped 2026-02-08)
- v3.0 Async Graphs -- Phases 11-13 (shipped 2026-02-13)
- v4.0 Cortex -- Phases 14-20 (shipped 2026-02-14)
- v5.0 Stream Views -- Phases 21-25 (shipped 2026-02-14)
- v6.0 Graph Runtime -- Phases 26-30 (in progress)

## Phases

<details>
<summary>v1.0 DSPy Compilation (Phases 1-4) -- SHIPPED 2026-02-05</summary>

- [x] Phase 1: Signature Generation (1/1 plans)
- [x] Phase 1.1: Deps Signature Extension (1/1 plans)
- [x] Phase 2: DSPy Integration (5/5 plans)
- [x] Phase 3: Optimization (4/4 plans)
- [x] Phase 4: Production Runtime (2/2 plans)

</details>

<details>
<summary>v2.0 Context Frames (Phases 5-10) -- SHIPPED 2026-02-08</summary>

- [x] Phase 5: Markers + Resolver (4/4 plans)
- [x] Phase 6: Node LM Protocol (5/5 plans)
- [x] Phase 7: Integration (4/4 plans)
- [x] Phase 8: Cleanup + Migration (4/4 plans)
- [x] Phase 10: Hint Annotation (3/3 plans)

</details>

<details>
<summary>v3.0 Async Graphs (Phases 11-13) -- SHIPPED 2026-02-13</summary>

- [x] Phase 11: Async Core (4/4 plans)
- [x] Phase 12: Parallel Deps + Migration (4/4 plans)
- [x] Phase 13: Fix Nested Model Construction in Fill (1/1 plan)

</details>

<details>
<summary>v4.0 Cortex (Phases 14-20) -- SHIPPED 2026-02-14</summary>

- [x] Phase 14: Shell Foundation (3/3 plans)
- [x] Phase 15: Session Store (4/4 plans)
- [x] Phase 16: Channel I/O (2/2 plans)
- [x] Phase 17: Namespace (3/3 plans)
- [x] Phase 18: AI Agent (2/2 plans)
- [x] Phase 19: Task Lifecycle (5/5 plans)
- [x] Phase 20: AI Eval Loop (5/5 plans)

</details>

<details>
<summary>v5.0 Stream Views (Phases 21-25) -- SHIPPED 2026-02-14</summary>

- [x] Phase 21: Execution Convention (2/2 plans)
- [x] Phase 22: Tool Call Translation (2/2 plans)
- [x] Phase 23: View Framework (1/1 plan)
- [x] Phase 24: Execution Display (1/1 plan)
- [x] Phase 25: Views Completion (3/3 plans)

</details>

### v6.0 Graph Runtime (In Progress)

**Milestone Goal:** Run bae graphs async inside cortex with concurrent execution, human-in-the-loop input gates, and full observability through the view system.

- [x] **Phase 26: Engine Foundation** - Registry, engine wrapper, timing, TaskManager integration (2026-02-15)
- [x] **Phase 27: Graph Mode** - Command interface for graph management (2026-02-15)
- [ ] **Phase 28: Input Gates** - Future-based human-in-the-loop suspension with routing UX
- [ ] **Phase 29: Observability** - Channel integration, debug views, metrics, scaling validation

## Phase Details

### Phase 26: Engine Foundation
**Goal**: Graphs run concurrently inside cortex as managed tasks with lifecycle tracking
**Depends on**: Phase 25 (v5.0 complete)
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, INT-01
**Success Criteria** (what must be TRUE):
  1. Dzara can submit a graph and it runs to completion in the background while she continues using the REPL
  2. Running graphs appear in the Ctrl-C task menu and can be cancelled from there
  3. The registry tracks each graph's lifecycle state (RUNNING/WAITING/DONE/FAILED/CANCELLED) and current node
  4. Per-node timing data (start/end) and dep call durations are captured for every graph run
  5. `Graph.arun()` accepts a `dep_cache` parameter without breaking existing call sites
**Plans**: 4 plans

Plans:
- [x] 26-01-PLAN.md -- dep_cache parameter, event loop yield, CancelledError fix
- [x] 26-02-PLAN.md -- GraphRegistry, TimingLM, engine wrapper, shell integration
- [x] 26-03-PLAN.md -- Graph instance guard, subprocess session isolation (gap closure)
- [x] 26-04-PLAN.md -- GraphRun error field, GRAPH mode error surfacing, kwarg fix (gap closure)

### Phase 27: Graph Mode
**Goal**: Dzara can start, monitor, inspect, and cancel graphs through GRAPH mode commands
**Depends on**: Phase 26
**Requirements**: MODE-01, MODE-02, MODE-03, MODE-04, MODE-05
**Success Criteria** (what must be TRUE):
  1. `run <expr>` evaluates a namespace expression and submits the resulting graph to the engine
  2. `list` shows all graph runs with their state, elapsed time, and current node
  3. `cancel <id>` stops a running graph and cleans up its resources
  4. `inspect <id>` displays the full execution trace with node timings and field values
  5. `trace <id>` shows node transition history for a running or completed graph
**Plans**: 2 plans

Plans:
- [x] 27-01-PLAN.md -- graph() factory function, async callable API, engine submit_coro + result storage
- [x] 27-02-PLAN.md -- GRAPH mode command dispatcher (run/list/cancel/inspect/trace)

### Phase 28: Input Gates
**Goal**: Graphs can pause for human input and Dzara can respond from any mode
**Depends on**: Phase 27
**Requirements**: GATE-01, GATE-02, GATE-03, GATE-04, GATE-05, MODE-06
**Success Criteria** (what must be TRUE):
  1. When a graph needs user input, execution suspends (via asyncio.Future) until Dzara responds
  2. Pending input count shows as a toolbar badge visible in all modes
  3. `input <id> <value>` in GRAPH mode and `@gid <value>` from any mode both resolve a pending gate
  4. Pending gates display field name, type, and description so Dzara knows what to provide
  5. Shush mode (badge only) vs inline notification is toggleable per preference
**Plans**: TBD

Plans:
- [ ] 28-01: TBD
- [ ] 28-02: TBD

### Phase 29: Observability
**Goal**: Full visibility into graph execution through the channel/view system with scaling validation
**Depends on**: Phase 28
**Requirements**: OBS-01, OBS-02, OBS-03, OBS-04, OBS-05, OBS-06, INT-02, INT-03
**Success Criteria** (what must be TRUE):
  1. Graph events flow through the `[graph]` channel with typed metadata and render correctly in UserView and DebugView
  2. Lifecycle notifications (start, complete, fail, transition) appear inline regardless of which mode Dzara is in
  3. Debug view shows node timings, dep durations, LM call times, and validation errors for any graph run
  4. 10+ concurrent graphs run without event loop starvation, channel flooding, or memory leaks
  5. Graph events persist to SessionStore so Dzara can review past runs across sessions
**Plans**: TBD

Plans:
- [ ] 29-01: TBD
- [ ] 29-02: TBD

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Signature Generation | v1.0 | 1/1 | Complete | 2026-02-04 |
| 1.1. Deps Signature Extension | v1.0 | 1/1 | Complete | 2026-02-04 |
| 2. DSPy Integration | v1.0 | 5/5 | Complete | 2026-02-04 |
| 3. Optimization | v1.0 | 4/4 | Complete | 2026-02-05 |
| 4. Production Runtime | v1.0 | 2/2 | Complete | 2026-02-05 |
| 5. Markers + Resolver | v2.0 | 4/4 | Complete | 2026-02-07 |
| 6. Node LM Protocol | v2.0 | 5/5 | Complete | 2026-02-07 |
| 7. Integration | v2.0 | 4/4 | Complete | 2026-02-07 |
| 8. Cleanup + Migration | v2.0 | 4/4 | Complete | 2026-02-08 |
| 10. Hint Annotation | v2.0 | 3/3 | Complete | 2026-02-08 |
| 11. Async Core | v3.0 | 4/4 | Complete | 2026-02-09 |
| 12. Parallel Deps + Migration | v3.0 | 4/4 | Complete | 2026-02-09 |
| 13. Fix Nested Fill | v3.0 | 1/1 | Complete | 2026-02-09 |
| 14. Shell Foundation | v4.0 | 3/3 | Complete | 2026-02-13 |
| 15. Session Store | v4.0 | 4/4 | Complete | 2026-02-13 |
| 16. Channel I/O | v4.0 | 2/2 | Complete | 2026-02-13 |
| 17. Namespace | v4.0 | 3/3 | Complete | 2026-02-13 |
| 18. AI Agent | v4.0 | 2/2 | Complete | 2026-02-13 |
| 19. Task Lifecycle | v4.0 | 5/5 | Complete | 2026-02-14 |
| 20. AI Eval Loop | v4.0 | 5/5 | Complete | 2026-02-14 |
| 21. Execution Convention | v5.0 | 2/2 | Complete | 2026-02-14 |
| 22. Tool Call Translation | v5.0 | 2/2 | Complete | 2026-02-14 |
| 23. View Framework | v5.0 | 1/1 | Complete | 2026-02-14 |
| 24. Execution Display | v5.0 | 1/1 | Complete | 2026-02-14 |
| 25. Views Completion | v5.0 | 3/3 | Complete | 2026-02-14 |
| 26. Engine Foundation | v6.0 | 4/4 | Complete | 2026-02-15 |
| 27. Graph Mode | v6.0 | 2/2 | Complete | 2026-02-15 |
| 28. Input Gates | v6.0 | 0/TBD | Not started | - |
| 29. Observability | v6.0 | 0/TBD | Not started | - |

---
