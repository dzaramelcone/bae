# Roadmap: Bae

## Milestones

- v1.0 DSPy Compilation — Phases 1-4 (shipped 2026-02-05)
- v2.0 Context Frames — Phases 5-10 (shipped 2026-02-08)
- v3.0 Async Graphs — Phases 11-13 (shipped 2026-02-13)
- v4.0 Cortex — Phases 14-20 (shipped 2026-02-14)
- v5.0 Stream Views — Phases 21-25 (in progress)

## Phases

<details>
<summary>v1.0 DSPy Compilation (Phases 1-4) — SHIPPED 2026-02-05</summary>

- [x] Phase 1: Signature Generation (1/1 plans)
- [x] Phase 1.1: Deps Signature Extension (1/1 plans)
- [x] Phase 2: DSPy Integration (5/5 plans)
- [x] Phase 3: Optimization (4/4 plans)
- [x] Phase 4: Production Runtime (2/2 plans)

</details>

<details>
<summary>v2.0 Context Frames (Phases 5-10) — SHIPPED 2026-02-08</summary>

- [x] Phase 5: Markers + Resolver (4/4 plans)
- [x] Phase 6: Node LM Protocol (5/5 plans)
- [x] Phase 7: Integration (4/4 plans)
- [x] Phase 8: Cleanup + Migration (4/4 plans)
- [x] Phase 10: Hint Annotation (3/3 plans)

</details>

<details>
<summary>v3.0 Async Graphs (Phases 11-13) — SHIPPED 2026-02-13</summary>

- [x] Phase 11: Async Core (4/4 plans)
- [x] Phase 12: Parallel Deps + Migration (4/4 plans)
- [x] Phase 13: Fix Nested Model Construction in Fill (1/1 plan)

</details>

<details>
<summary>v4.0 Cortex (Phases 14-20) — SHIPPED 2026-02-14</summary>

- [x] Phase 14: Shell Foundation (3/3 plans)
- [x] Phase 15: Session Store (4/4 plans)
- [x] Phase 16: Channel I/O (2/2 plans)
- [x] Phase 17: Namespace (3/3 plans)
- [x] Phase 18: AI Agent (2/2 plans)
- [x] Phase 19: Task Lifecycle (5/5 plans)
- [x] Phase 20: AI Eval Loop (5/5 plans)

</details>

### v5.0 Stream Views (In Progress)

**Milestone Goal:** Multi-view stream framework with tool call translation and execution display overhaul.

- [x] **Phase 21: Execution Convention** - Eval loop distinguishes executable from illustrative code
- [x] **Phase 22: Tool Call Translation** - Detect and translate AI tool call patterns to Python equivalents
- [x] **Phase 23: View Framework** - ViewFormatter protocol with channel delegation
- [ ] **Phase 24: Execution Display** - UserView with Rich Panel framing, code+output grouping, deduplication
- [ ] **Phase 25: Views Completion** - DebugView, AI self-view, and runtime view toggling

## Phase Details

### Phase 21: Execution Convention
**Goal**: Eval loop only executes code the AI explicitly marks as executable
**Depends on**: Nothing (first v5.0 phase)
**Requirements**: EXEC-01, EXEC-02
**Success Criteria** (what must be TRUE):
  1. AI code blocks marked as executable are extracted and run by the eval loop
  2. AI code blocks shown as illustration (examples, pseudocode, explanations) are NOT executed
  3. When AI does not use the convention, no code executes (clean break, no backward compatibility)
**Plans**: 2 plans

Plans:
- [ ] 21-01-PLAN.md -- Eval harness: test 3 convention candidates across Opus/Sonnet/Haiku, select winner
- [ ] 21-02-PLAN.md -- Implement winning convention: replace extract_code, update prompt and eval loop

### Phase 22: Tool Call Translation
**Goal**: AI tool call attempts are caught, translated to Python, and executed transparently
**Depends on**: Phase 21 (convention for marking translated code)
**Requirements**: AIHR-02, AIHR-03, AIHR-04, AIHR-05, AIHR-06, AIHR-07, AIHR-08
**Success Criteria** (what must be TRUE):
  1. AI Read tool call (`<R:filepath>`) is intercepted and produces file contents in the namespace
  2. AI Write tool call (`<W:filepath>`) is intercepted and writes file content from the response
  3. AI Glob/Grep tool calls are intercepted and produce search results in the namespace
  4. AI Edit tool call (`<E:filepath:line_start-line_end>`) is intercepted and performs the file edit
  5. User sees a visible indicator (channel label or badge) when a tool call was translated and executed
**Plans**: 2 plans

Plans:
- [x] 22-01-PLAN.md — TDD: translate_tool_calls() pure function with all 5 tool types and fence exclusion
- [x] 22-02-PLAN.md — Eval loop integration, system prompt tool tag vocabulary, visible indicator

### Phase 23: View Framework
**Goal**: Channel display is pluggable via formatter strategy, with zero change to existing behavior
**Depends on**: Nothing (independent infrastructure)
**Requirements**: VIEW-01, VIEW-02
**Success Criteria** (what must be TRUE):
  1. ViewFormatter protocol exists with a render method that receives channel name, color, content, and metadata
  2. Channel._display() delegates to formatter when one is set, falls back to existing behavior when unset
  3. All existing REPL tests pass without modification (zero regression)
**Plans**: 1 plan

Plans:
- [x] 23-01-PLAN.md — ViewFormatter protocol, Channel._formatter field, _display() delegation + tests

### Phase 24: Execution Display
**Goal**: AI code execution renders as polished framed panels with deduplication
**Depends on**: Phase 23 (formatter infrastructure)
**Requirements**: VIEW-03, DISP-01, DISP-02, DISP-03, DISP-04
**Success Criteria** (what must be TRUE):
  1. AI-executed code renders in a Rich Panel with syntax highlighting and a descriptive title
  2. Execution output renders in a separate panel below the code panel
  3. Code and output panels appear as a grouped visual unit (no interleaved channel lines between them)
  4. AI-initiated code execution does NOT echo the code as a redundant [py] channel line
**Plans**: 1 plan

Plans:
- [ ] 24-01-PLAN.md — UserView formatter with buffered exec grouping, panel rendering, shell wiring

### Phase 25: Views Completion
**Goal**: User can cycle between debug, AI-self, and user views at runtime
**Depends on**: Phase 23 (framework), Phase 24 (UserView as reference)
**Requirements**: VIEW-04, VIEW-05, VIEW-06
**Success Criteria** (what must be TRUE):
  1. DebugView renders raw channel data with full metadata visible
  2. AI self-view provides structured feedback format consumed by the eval loop
  3. User can toggle between views at runtime via keybinding (Ctrl+V or equivalent)
  4. Toolbar displays the currently active view mode
**Plans**: TBD

Plans:
- [ ] 25-01: TBD
- [ ] 25-02: TBD

## Progress

**Execution Order:**
Phases 21 and 23 are parallel-safe (no dependencies between them). Phase 22 follows 21. Phase 24 follows 23. Phase 25 follows 23+24.

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
| 24. Execution Display | v5.0 | 0/1 | Not started | - |
| 25. Views Completion | v5.0 | 0/TBD | Not started | - |

---
*Last updated: 2026-02-14 after Phase 24 planning complete*
