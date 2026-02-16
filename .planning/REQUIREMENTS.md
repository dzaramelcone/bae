# Requirements: Bae v7.0 Hypermedia Resourcespace

**Defined:** 2026-02-16
**Core Value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing

## v7.0 Requirements

Requirements for the Hypermedia Resourcespace milestone. Each maps to roadmap phases.

### Resourcespace Protocol

- [ ] **RSP-01**: Agent can call a resource as a function to navigate into it (e.g., `source()` enters source resourcespace)
- [ ] **RSP-02**: On entry, resource displays a table of its functions with short procedural docstrings
- [ ] **RSP-03**: Each resource has a `.nav()` affordance listing navigation targets as `@resource()` hyperlinks
- [ ] **RSP-04**: `@resource()` mentions in any resource output serve as hyperlinks the agent can call to navigate
- [ ] **RSP-05**: Resources can contain subresourcespaces (e.g., `source.meta()` to edit the resourcespace's own code)
- [ ] **RSP-06**: `homespace()` is universally available and returns agent to root resourcespace
- [ ] **RSP-07**: Agent tools (read/write/edit/glob/grep) operate on the current resource context when navigated in
- [ ] **RSP-08**: Each resource declares which tools it supports; unsupported tools return clear errors
- [ ] **RSP-09**: All resourcespace tool output capped at 500 tokens with summary-based pruning (not truncation)
- [ ] **RSP-10**: Error outputs are never pruned (preserved in full for agent learning)
- [ ] **RSP-11**: Resources provide contextual Python hints on entry for operations beyond standard tools (e.g., batch writes via `<run>`)
- [ ] **RSP-12**: Current resource location injected into every AI invocation (not just first)

### Source Resourcespace

- [ ] **SRC-01**: Agent can navigate into source resourcespace scoped to project directory
- [ ] **SRC-02**: All 5 tools (read/write/edit/glob/grep) resolve paths relative to project root
- [ ] **SRC-03**: `read()` shows project file tree (budget-aware, within 500 token cap)
- [ ] **SRC-04**: Out-of-scope paths (absolute, `../` traversal) are rejected with clear errors
- [ ] **SRC-05**: Subresourcespace exists for editing the resourcespace's own source code

### Task Resourcespace

- [ ] **TSK-01**: Agent can navigate into task resourcespace for task management
- [ ] **TSK-02**: Agent can create tasks with title (`.add()`)
- [ ] **TSK-03**: Agent can read task details or list all tasks (`.read()`)
- [ ] **TSK-04**: Agent can update task fields — status, priority, tags (`.update()`)
- [ ] **TSK-05**: Agent can mark tasks complete (`.done()`)
- [ ] **TSK-06**: Agent can search tasks via FTS (`.search()`)
- [ ] **TSK-07**: Tasks persist across sessions
- [ ] **TSK-08**: Homespace shows outstanding task count on entry

### Memory Resourcespace

- [ ] **MEM-01**: Agent can navigate into memory resourcespace to explore session history
- [ ] **MEM-02**: Agent can browse sessions (children organized by date/ID)
- [ ] **MEM-03**: Agent can search across sessions via FTS5
- [ ] **MEM-04**: Agent can tag session entries for retrieval
- [ ] **MEM-05**: Agent can read individual session entries

### Search Resourcespace

- [ ] **SCH-01**: Agent can navigate into search resourcespace for cross-resourcespace search
- [ ] **SCH-02**: Search federates across source, tasks, and memory resourcespaces
- [ ] **SCH-03**: Results grouped by resourcespace with `@resource()` navigation hyperlinks
- [ ] **SCH-04**: Results capped per-resourcespace to stay within token budget

### Discovery & Context

- [ ] **DSC-01**: Homespace `read()` shows available resourcespaces with descriptions (HATEOAS entry point)
- [ ] **DSC-02**: AI prompt shows only current resource's state/tools/affordances (replaces flat namespace dump)
- [ ] **DSC-03**: Tool summaries in UserView include resource context (e.g., `[source] read ai.py (42 lines)`)

## Future Requirements

Deferred to v8.0+. Tracked but not in current roadmap.

### Autonomous Operation

- **AUT-01**: Goal priority queue with blocker handling
- **AUT-02**: Heartbeat/cycle invocation for autonomous operation
- **AUT-03**: Blocker escalation (notify Dzara when stuck)

### Graph Conversation Loop

- **GCL-01**: Replace NL turn loop with bae graph
- **GCL-02**: Selective Recall for context management (pruned tool call history)
- **GCL-03**: Vibe mode on nodes (raw text capture, schema as scaffold)

### Enhanced Cognition

- **COG-01**: Clinical cognition scaffold (assumptions/reasoning/confidence per action)
- **COG-02**: Few-shot optimization for vibe nodes (BootstrapFewShot adapted)

## Out of Scope

| Feature | Reason |
|---------|--------|
| MCP protocol compliance | In-process Python objects, not client-server. Wrap later if needed. |
| Vector/semantic search | FTS5 sufficient for cortex memory volume. YAGNI. |
| Resource permissions/ACLs | Single-user REPL, no security boundary. |
| Persistent navigation across sessions | Homespace re-orientation is fast enough. |
| Custom resourcespace plugin system | Python IS the extension system. |
| Resource versioning/history | Git for source, timestamps for store entries. |
| Automatic resource suggestion | HATEOAS discovery is the design — AI reads and decides. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| RSP-01 | Phase 31 | Pending |
| RSP-02 | Phase 31 | Pending |
| RSP-03 | Phase 31 | Pending |
| RSP-04 | Phase 31 | Pending |
| RSP-05 | Phase 31 | Pending |
| RSP-06 | Phase 31 | Pending |
| RSP-07 | Phase 31 | Pending |
| RSP-08 | Phase 31 | Pending |
| RSP-09 | Phase 31 | Pending |
| RSP-10 | Phase 31 | Pending |
| RSP-11 | Phase 31 | Pending |
| RSP-12 | Phase 36 | Pending |
| SRC-01 | Phase 32 | Pending |
| SRC-02 | Phase 32 | Pending |
| SRC-03 | Phase 32 | Pending |
| SRC-04 | Phase 32 | Pending |
| SRC-05 | Phase 32 | Pending |
| TSK-01 | Phase 33 | Pending |
| TSK-02 | Phase 33 | Pending |
| TSK-03 | Phase 33 | Pending |
| TSK-04 | Phase 33 | Pending |
| TSK-05 | Phase 33 | Pending |
| TSK-06 | Phase 33 | Pending |
| TSK-07 | Phase 33 | Pending |
| TSK-08 | Phase 33 | Pending |
| MEM-01 | Phase 34 | Pending |
| MEM-02 | Phase 34 | Pending |
| MEM-03 | Phase 34 | Pending |
| MEM-04 | Phase 34 | Pending |
| MEM-05 | Phase 34 | Pending |
| SCH-01 | Phase 35 | Pending |
| SCH-02 | Phase 35 | Pending |
| SCH-03 | Phase 35 | Pending |
| SCH-04 | Phase 35 | Pending |
| DSC-01 | Phase 36 | Pending |
| DSC-02 | Phase 36 | Pending |
| DSC-03 | Phase 36 | Pending |

**Coverage:**
- v7.0 requirements: 37 total
- Mapped to phases: 37
- Unmapped: 0

---
*Requirements defined: 2026-02-16*
*Last updated: 2026-02-16 after roadmap creation*
