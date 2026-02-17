# Roadmap: Bae

## Milestones

- v1.0 DSPy Compilation -- Phases 1-4 (shipped 2026-02-05)
- v2.0 Context Frames -- Phases 5-10 (shipped 2026-02-08)
- v3.0 Async Graphs -- Phases 11-13 (shipped 2026-02-13)
- v4.0 Cortex -- Phases 14-20 (shipped 2026-02-14)
- v5.0 Stream Views -- Phases 21-25 (shipped 2026-02-14)
- v6.0 Graph Runtime -- Phases 26-30 (shipped 2026-02-16)
- v7.0 Hypermedia Resourcespace -- Phases 31-36 (in progress)

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

<details>
<summary>v6.0 Graph Runtime (Phases 26-30) -- SHIPPED 2026-02-16</summary>

- [x] Phase 26: Engine Foundation (4/4 plans)
- [x] Phase 27: Graph Mode (6/6 plans)
- [x] Phase 28: Input Gates (3/3 plans)
- [x] Phase 29: Observability (5/5 plans)
- [x] Phase 30: Agent Core Extraction (2/2 plans)

</details>

### v7.0 Hypermedia Resourcespace (In Progress)

- [x] **Phase 31: Resource Protocol + Navigation** - Resourcespace protocol, registry, navigation state, tool dispatch routing, output pruning (completed 2026-02-16)
- [x] **Phase 32: Source Resourcespace** - Project-scoped file operations proving the resourcespace pattern end-to-end (completed 2026-02-16)
- [x] **Phase 32.1: Resourcespace Package Structure** - Restructure into bae/repl/spaces/ with per-space packages (INSERTED) (completed 2026-02-16)
- [x] **Phase 32.1.1: Subresource Packages + Shim Removal** - Break subresources into own packages, remove shims, enforce structure (INSERTED) (completed 2026-02-16)
- [x] **Phase 32.2: UserView Tool Call Stripping** - Strip tool calls from AI output, show AI-native tool tags with docstring summaries (INSERTED) (completed 2026-02-16)
- [x] **Phase 33: Task Resourcespace** - Persistent task CRUD with FTS search and cross-session persistence (completed 2026-02-16)
- [ ] **Phase 34: Memory Resourcespace** - Session history as navigable, searchable, taggable resources
- [ ] **Phase 35: Search Resourcespace** - Federated cross-resourcespace search with navigation hyperlinks
- [ ] **Phase 36: Discovery + Integration** - Homespace dashboard, AI context injection, resource-scoped view summaries

## Phase Details

### Phase 31: Resource Protocol + Navigation
**Goal**: Agent can navigate a self-describing resource tree where tools operate on the current resource context
**Depends on**: Nothing (v7.0 foundation)
**Requirements**: RSP-01, RSP-02, RSP-03, RSP-04, RSP-05, RSP-06, RSP-07, RSP-08, RSP-09, RSP-10, RSP-11
**Success Criteria** (what must be TRUE):
  1. Agent calls a resource as a function and enters it; on entry sees a functions table with procedural docstrings and Python hints for advanced operations
  2. `.nav()` on any resource lists targets as `@resource()` hyperlinks; `@resource()` mentions are callable to navigate
  3. `homespace()` returns agent to root from any depth; subresourcespaces nest via dotted calls (e.g., `source.meta()`)
  4. Standard tools (read/write/edit/glob/grep) dispatch to the current resource's handlers; unsupported tools return clear errors
  5. All resourcespace tool output is capped at 500 tokens via summary-based pruning; error outputs are never pruned
**Plans**: 3 plans

Plans:
- [ ] 31-01-PLAN.md — Resourcespace protocol, ResourceRegistry, ResourceHandle, navigation state, error formatting (TDD)
- [ ] 31-02-PLAN.md — ToolRouter with dispatch, pruning, homespace fallback (TDD)
- [ ] 31-03-PLAN.md — Integration: wire registry/router into ai.py, shell.py, namespace, toolbar, prompt

### Phase 32: Source Resourcespace
**Goal**: Agent can navigate into project source and operate on files with path-safe, context-scoped tools
**Depends on**: Phase 31
**Requirements**: SRC-01, SRC-02, SRC-03, SRC-04, SRC-05
**Success Criteria** (what must be TRUE):
  1. Agent calls `source()` and enters source resourcespace scoped to project directory
  2. All 5 tools resolve paths relative to project root; out-of-scope paths (absolute, `../` traversal) are rejected with clear errors
  3. `read()` shows a budget-aware project file tree within 500 token cap
  4. `source.meta()` enters a subresourcespace for editing the resourcespace's own code
**Plans**: 7 plans

Plans:
- [x] 32-01-PLAN.md — SourceResourcespace core: protocol, module path resolution, path safety, read (TDD)
- [x] 32-02-PLAN.md — Glob and grep with module-path output (TDD)
- [x] 32-03-PLAN.md — Write, edit, hot-reload, rollback, and undo (TDD)
- [x] 32-04-PLAN.md — Subresources (deps, config, tests, meta) and shell registration
- [x] 32-05-PLAN.md — Gap closure: fix navigation stack replacement and inject tool callables into namespace
- [ ] 32-06-PLAN.md — Gap closure: fix package listing counts (submodules instead of class/function)
- [ ] 32-07-PLAN.md — Gap closure: rename homespace() to home() and make home a resource with tools

### Phase 32.1: Resourcespace Package Structure (INSERTED)

**Goal:** Restructure resourcespace code into bae/repl/spaces/ with dedicated home/ and source/ packages, preserving all behavior
**Depends on:** Phase 32
**Plans:** 2/2 plans complete

Plans:
- [ ] 32.1-01-PLAN.md — Create spaces/ package structure, move source and home code, backward-compat re-exports
- [ ] 32.1-02-PLAN.md — Migrate test imports to new paths, clean up ai.py, final audit

### Phase 32.1.1: Subresource Packages + Shim Removal (INSERTED)

**Goal:** Break subresources into own packages, remove all backward-compat shims, update all callsites, enforce package structure in source resourcespace operations
**Depends on:** Phase 32.1
**Plans:** 4/4 plans complete

Plans:
- [x] 32.1.1-01-PLAN.md — Relocate protocol to spaces/view.py, update callsites, delete shims
- [x] 32.1.1-02-PLAN.md — Extract subresource classes into own packages with view/service split
- [x] 32.1.1-03-PLAN.md — Split home/ into view.py + service.py convention
- [x] 32.1.1-04-PLAN.md — Structure enforcement: role-grouped read, tstring-templated write, meta guidance

### Phase 32.2: UserView Tool Call Stripping (INSERTED)

**Goal:** Strip tool call content from UserView and AI context history; prune everything but tool I/O and agent's last message; resource entry shows AI-native tool tags with docstring summaries
**Depends on:** Phase 32.1
**Plans:** 4/4 plans complete

Plans:
- [ ] 32.2-01-PLAN.md — Reformat tool summaries to `◆ name(args) -> type` and suppress intermediate AI responses
- [ ] 32.2-02-PLAN.md — Functions table with typed XML signatures and docstrings on resource entry
- [ ] 32.2-03-PLAN.md — Pydantic parameter validation on ToolRouter dispatch with helpful errors
- [ ] 32.2-04-PLAN.md — Gap closure: wire validation and summaries onto the run-block code path

### Phase 33: Task Resourcespace
**Goal**: Agent can manage persistent tasks through a navigable resource with CRUD and search
**Depends on**: Phase 31
**Requirements**: TSK-01, TSK-02, TSK-03, TSK-04, TSK-05, TSK-06, TSK-07, TSK-08
**Success Criteria** (what must be TRUE):
  1. Agent calls `tasks()` and enters task resourcespace; can create tasks with `.add()` and mark them done with `.done()`
  2. Agent can list all tasks, read individual task details, and update fields (status, priority, tags) via `.update()`
  3. Agent can search tasks via FTS with `.search()`
  4. Tasks persist across cortex sessions (SQLite-backed)
  5. Homespace entry shows outstanding task count
**Plans**: 3 plans

Plans:
- [x] 33-01-PLAN.md — TaskStore data layer (SQLite schema, CRUD, FTS5) + custom tool cleanup
- [x] 33-02-PLAN.md — TaskResourcespace service, view, shell registration, homespace count
- [ ] 33-03-PLAN.md — Gap closure: base36 task IDs, show IDs in listing, fix kwargs validator

### Phase 34: Memory Resourcespace
**Goal**: Agent can explore, search, and tag session history as navigable resources
**Depends on**: Phase 31
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04, MEM-05
**Success Criteria** (what must be TRUE):
  1. Agent calls `memory()` and enters memory resourcespace showing sessions organized by date/ID
  2. Agent can search across sessions via FTS5 and read individual session entries
  3. Agent can tag session entries for retrieval
**Plans**: TBD

Plans:
- [ ] 34-01: TBD
- [ ] 34-02: TBD

### Phase 35: Search Resourcespace
**Goal**: Agent can search across all resourcespaces and navigate directly to results
**Depends on**: Phase 32, Phase 33, Phase 34
**Requirements**: SCH-01, SCH-02, SCH-03, SCH-04
**Success Criteria** (what must be TRUE):
  1. Agent calls `search()` and enters search resourcespace
  2. Search federates across source, tasks, and memory; results grouped by resourcespace with `@resource()` navigation hyperlinks
  3. Results capped per-resourcespace to stay within token budget
**Plans**: TBD

Plans:
- [ ] 35-01: TBD

### Phase 36: Discovery + Integration
**Goal**: Homespace serves as a dynamic HATEOAS entry point and AI always knows its current resource context
**Depends on**: Phase 33, Phase 35
**Requirements**: RSP-12, DSC-01, DSC-02, DSC-03
**Success Criteria** (what must be TRUE):
  1. Homespace `read()` shows all available resourcespaces with descriptions (HATEOAS entry point)
  2. AI prompt includes current resource location, state, tools, and affordances on every invocation (not just first)
  3. Tool summaries in UserView include resource context (e.g., `[source] read ai.py (42 lines)`)
**Plans**: TBD

Plans:
- [ ] 36-01: TBD
- [ ] 36-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 31 -> 32 -> 33 -> 34 -> 35 -> 36

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
| 27. Graph Mode | v6.0 | 6/6 | Complete | 2026-02-15 |
| 28. Input Gates | v6.0 | 3/3 | Complete | 2026-02-15 |
| 29. Observability | v6.0 | 5/5 | Complete | 2026-02-15 |
| 30. Agent Core Extraction | v6.0 | 2/2 | Complete | 2026-02-15 |
| 31. Resource Protocol + Navigation | v7.0 | Complete    | 2026-02-16 | - |
| 32. Source Resourcespace | v7.0 | Complete    | 2026-02-16 | - |
| 32.1. Resourcespace Package Structure | v7.0 | Complete    | 2026-02-16 | - |
| 32.1.1. Subresource Packages + Shim Removal | v7.0 | 4/4 | Complete | 2026-02-16 |
| 33. Task Resourcespace | v7.0 | Complete    | 2026-02-17 | - |
| 34. Memory Resourcespace | v7.0 | 0/TBD | Not started | - |
| 35. Search Resourcespace | v7.0 | 0/TBD | Not started | - |
| 36. Discovery + Integration | v7.0 | 0/TBD | Not started | - |

---
