# Roadmap: Bae

## Milestones

- v1.0 DSPy Compilation — Phases 1-4 (shipped 2026-02-05)
- v2.0 Context Frames — Phases 5-10 (shipped 2026-02-08)
- v3.0 Async Graphs — Phases 11-13 (shipped 2026-02-13)
- v4.0 Cortex — Phases 14-19 (in progress)

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

### v4.0 Cortex (In Progress)

**Milestone Goal:** NL-first augmented REPL where human and AI collaborate in a shared namespace -- session store captures all I/O for cross-session memory, channels route labeled output, and the AI agent operates in natural language while producing correct code.

- [x] **Phase 14: Shell Foundation** - Async REPL with modes, good text editing, and clean lifecycle
- [x] **Phase 15: Session Store** - RAG-friendly persistence layer for all I/O across sessions
- [x] **Phase 16: Channel I/O** - Labeled output streams wired to session store with bae graph integration
- [x] **Phase 17: Namespace** - Reflective shared namespace with bae objects and introspection
- [ ] **Phase 18: AI Agent** - NL-first AI operating in conversation while producing correct code
- [x] **Phase 19: Task Lifecycle** - Background task management and custom prompt configuration
- [ ] **Phase 20: AI Eval Loop** - AI executes code/commands in REPL namespace and bash, pipes results back into conversation

## Phase Details

### Phase 14: Shell Foundation
**Goal**: User can launch cortex, switch between modes, write well-edited code, and exit cleanly
**Depends on**: Nothing (first v4.0 phase)
**Requirements**: REPL-01, REPL-03, REPL-04, REPL-05, REPL-07, REPL-08, REPL-12, REPL-13, REPL-14
**Success Criteria** (what must be TRUE):
  1. Running `bae` with no arguments launches cortex; user can type `await asyncio.sleep(1)` and it executes
  2. Shift+Tab cycles through NL / Py / Graph / Bash modes and the prompt visually indicates which mode is active
  3. In Py mode, user gets syntax highlighting, multiline editing (Shift+Enter for newlines), and tab completion on namespace objects
  4. In Bash mode, shell commands execute and output appears
  5. Ctrl-C with no tasks exits; Ctrl-D exits with graceful shutdown (tasks cancelled, queues drained)
**Plans:** 3 plans

Plans:
- [x] 14-01-PLAN.md — REPL shell + modes + Python execution + entry point
- [x] 14-02-PLAN.md — Bash mode + tab completion + lifecycle
- [x] 14-03-PLAN.md — Fix async_exec spurious output from loop variables (gap closure)

### Phase 15: Session Store
**Goal**: All I/O flows through a persistence layer that labels, indexes, and structures data for RAG queries and cross-session memory
**Depends on**: Phase 14
**Requirements**: STORE-01, STORE-02, STORE-03, STORE-04
**Success Criteria** (what must be TRUE):
  1. Every input and output (all modes, all channels) is automatically labeled and persisted to the session store
  2. Stored data has structured metadata (timestamps, mode, channel, session ID) queryable for RAG -- not opaque blobs
  3. After exiting and re-launching cortex, the AI retains project context from previous sessions
  4. User can inspect what context is stored (e.g., `store()` or equivalent shows indexed entries)
**Plans:** 4 plans

Plans:
- [x] 15-01-PLAN.md — SessionStore class with SQLite + FTS5 persistence (TDD)
- [x] 15-02-PLAN.md — REPL integration, store() inspector, and integration tests
- [x] 15-03-PLAN.md — Gap closure: stdout capture + callable SessionStore
- [x] 15-04-PLAN.md — Gap closure: unified formatting, ellipsis, dict returns

### Phase 16: Channel I/O
**Goal**: All output flows through labeled channels that users can see, filter, and access -- bae graph execution integrates via wrapper pattern without source modifications
**Depends on**: Phase 14, Phase 15
**Requirements**: CHAN-01, CHAN-02, CHAN-03, CHAN-04, CHAN-05
**Success Criteria** (what must be TRUE):
  1. Every line of output is prefixed with a color-coded channel label (e.g., `[py]`, `[graph]`, `[ai]`, `[bash]`)
  2. User can open a TUI select menu to toggle which channels are visible
  3. Channels are accessible as Python objects in the namespace (e.g., `channels.py`, `channels.graph`)
  4. Enabling debug mode captures all channel output to a log file
  5. Graph execution output routes through channels via a wrapper around `graph.arun()` -- no bae source modifications
**Plans:** 2 plans

Plans:
- [x] 16-01-PLAN.md — Channel + ChannelRouter classes with TDD
- [x] 16-02-PLAN.md — Shell integration, graph wrapper, and integration tests

### Phase 17: Namespace
**Goal**: User interacts with real bae objects in a pre-loaded namespace and can introspect any object
**Depends on**: Phase 14
**Requirements**: NS-01, NS-02, NS-03, NS-04
**Success Criteria** (what must be TRUE):
  1. `Node`, `Graph`, `Dep`, `Recall` are available in the REPL without importing
  2. After executing an expression, `_` holds the result; after running a graph, `_trace` holds the trace
  3. Calling `ns()` prints all namespace objects with their types and one-line summaries
  4. Calling `ns(graph)` shows topology (nodes, edges); calling `ns(MyNode)` shows fields with annotations
**Plans:** 3 plans

Plans:
- [x] 17-01-PLAN.md — Namespace seeding and introspection (TDD)
- [x] 17-02-PLAN.md — Shell wiring and integration tests
- [x] 17-03-PLAN.md — Gap closure: register cortex module for REPL annotation resolution

### Phase 18: AI Agent
**Goal**: AI operates in natural language while producing correct Python and system calls -- the primary interaction mode for cortex
**Depends on**: Phase 16, Phase 17
**Requirements**: AI-01, AI-02, AI-03, AI-04, AI-05, AI-06, AI-07
**Success Criteria** (what must be TRUE):
  1. `await ai("what nodes does this graph have?")` returns a natural language answer incorporating namespace context (referenced variables, graph topology, recent trace)
  2. `await ai.fill(MyNode, context)` calls bae's LM fill and returns a populated node; `await ai.choose_type([A, B], ctx)` returns the selected type
  3. AI can parse Python code from NL conversation and integrate it into the codebase (extract code blocks, write files, run commands)
  4. All AI output appears on the `[ai]` channel and is persisted to the session store
  5. Prompt engineering delivers reliable NL-to-code: AI produces correct Python, makes appropriate bash/system calls, and handles ambiguity by asking
**Plans:** 2 plans

Plans:
- [x] 18-01-PLAN.md — AI callable class with CLI backend, context builder, code extractor, and unit tests
- [x] 18-02-PLAN.md — Shell integration wiring and integration tests

### Phase 19: Task Lifecycle
**Goal**: User can monitor, kill, and manage background tasks, and customize what the prompt displays
**Depends on**: Phase 18
**Requirements**: REPL-06, REPL-10, REPL-11
**Success Criteria** (what must be TRUE):
  1. Ctrl-C while tasks are running opens a menu listing active tasks with option to kill individual ones
  2. Double Ctrl-C kills all running tasks and returns to a bare cortex prompt
  3. User can configure the prompt to show custom content (CPU usage, running task count, cost accumulator, etc.)
**Plans:** 5 plans

Plans:
- [x] 19-01-PLAN.md -- ToolbarConfig class with built-in widgets (TDD)
- [x] 19-02-PLAN.md -- Task tracking, interrupt handler, kill menu, and subprocess cleanup
- [x] 19-03-PLAN.md -- Gap closure: background dispatch for toolbar visibility and kill menu activation
- [x] 19-04-PLAN.md -- Gap closure: TaskManager with lifecycle tracking and process group management (TDD)
- [x] 19-05-PLAN.md -- Gap closure: Shell integration, inline kill menu, PY async tracking

### Phase 20: AI Eval Loop
**Goal**: AI operates as a full agent — extracts and executes code/commands, sees results, retains cross-session context, and renders output properly
**Depends on**: Phase 18, Phase 19
**Requirements**: AI-06, STORE-03, REPL-10
**Success Criteria** (what must be TRUE):
  1. AI-generated Python code blocks are automatically extracted, executed in the REPL namespace, and results fed back to the correct AI session (multiple concurrent AI tasks supported)
  2. AI sessions spawned from PY mode (`await ai("question")`) are attachable/selectable in NL mode for continued turn-taking
  3. NL mode has a session selector when multiple AI sessions exist
  4. N concurrent AI prompts from PY REPL each route namespace mutations back to their correct sessions (tested)
  5. On launch, AI context includes recent session history from the store (cross-session memory)
  6. AI output renders markdown formatting in the terminal (headers, bold, code blocks, lists)
  7. Ctrl-C task menu renders as a numbered list below the input (printed to scrollback), not in the toolbar
**Plans:** 3 plans

Plans:
- [ ] 20-01-PLAN.md — Rich markdown rendering + task menu scrollback
- [ ] 20-02-PLAN.md — Multi-session AI management + cross-session memory
- [ ] 20-03-PLAN.md — AI eval loop (extract-execute-feedback) + concurrent session tests

## Progress

**Execution Order:**
Phases execute in numeric order: 14 -> 15 -> 16 -> 17 -> 18 -> 19 -> 20

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
| 20. AI Eval Loop | v4.0 | 0/3 | Planned | - |

---
*Last updated: 2026-02-14 after planning Phase 20 AI Eval Loop*
