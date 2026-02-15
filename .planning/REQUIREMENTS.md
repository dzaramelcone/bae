# Requirements: Bae

**Defined:** 2026-02-14
**Core Value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing

## v6.0 Requirements

Requirements for v6.0 Graph Runtime. Each maps to roadmap phases.

### Graph Engine

- [ ] **ENG-01**: Graph registry tracks concurrent graph instances by ID with lifecycle states (RUNNING/WAITING/DONE/FAILED/CANCELLED)
- [ ] **ENG-02**: Graph engine wraps `Graph.arun()` with lifecycle event emission without modifying the framework layer
- [ ] **ENG-03**: Engine captures per-node timing (start/end) and dep call durations
- [ ] **ENG-04**: Engine is backend-agnostic -- works with any LM conforming to the protocol
- [ ] **ENG-05**: `Graph.arun()` accepts `dep_cache` parameter for cortex injection (additive, backward compatible)

### Graph Mode

- [ ] **MODE-01**: GRAPH mode parses commands: `run`, `list`, `cancel`, `inspect`, `trace`
- [ ] **MODE-02**: `run <expr>` evaluates namespace expression and submits graph to engine
- [ ] **MODE-03**: `list` shows all graph runs with state, timing, current node
- [ ] **MODE-04**: `cancel <id>` revokes graph via registry and TaskManager
- [ ] **MODE-05**: `inspect <id>` shows full trace with node timings and field values
- [ ] **MODE-06**: Cross-mode input shortcut (`@gid <value>`) routes input from any mode

### Input Gates

- [ ] **GATE-01**: asyncio.Future-based input gate suspends graph execution until user responds
- [ ] **GATE-02**: Pending inputs display in toolbar badge with count, visible in all modes
- [ ] **GATE-03**: `input <id> <value>` command in GRAPH mode resolves pending gate
- [ ] **GATE-04**: Input schema display shows field name, type, and description from Pydantic
- [ ] **GATE-05**: Shush mode (toolbar badge only) vs inline notification is toggleable

### Observability

- [ ] **OBS-01**: Graph I/O flows through `[graph]` channel with typed metadata
- [ ] **OBS-02**: Lifecycle notifications (start/complete/fail/transition) visible in all modes
- [ ] **OBS-03**: Debug view shows node timings, dep durations, LM call times, validation errors
- [ ] **OBS-04**: Memory metrics (RSS delta per graph run)
- [ ] **OBS-05**: `asyncio.capture_call_graph()` integration for debugging stuck graphs
- [ ] **OBS-06**: Per-graph output policy (verbose/normal/quiet/silent) controlling channel verbosity

### Integration

- [ ] **INT-01**: Graphs are managed tasks via TaskManager -- appear in Ctrl-C menu, graceful shutdown
- [ ] **INT-02**: Graph events persist to SessionStore for cross-session history
- [ ] **INT-03**: 10+ concurrent graphs run without event loop starvation or channel flooding

## Future Requirements

### Namespace Restructuring (v7.0+)

- **NS-01**: CRUD protocol objects as navigable namespace entry points
- **NS-02**: Hypermedia-like directives in object help/repr for AI navigation
- **NS-03**: Breadcrumb tags on tools for guided discovery
- **NS-04**: B-tree structured session navigation with summaries and filterable tags

### Session Indexer (v7.0+)

- **IDX-01**: Indexer graph partitions conversations recursively with summaries + tags
- **IDX-02**: Session store navigable like a B-tree
- **IDX-03**: Indexer agents run as background graphs with lifecycle management

## Out of Scope

| Feature | Reason |
|---------|--------|
| State snapshots/checkpointing | Bae graphs are short-lived (seconds to minutes). YAGNI. |
| Distributed execution (Celery/Redis) | Architecture must not preclude it, but don't build it. |
| Visual DAG rendering in terminal | ASCII art graphs are awkward. Mermaid exists for static viz. |
| Auto-retry on validation errors | Deferred to DSPy optimization work. |
| Hot reload of graph definitions | Python namespace is live -- user redefines in PY mode. |
| Graph-to-graph orchestration | Python is the orchestration layer (custom __call__ nodes). |
| Token-level streaming | Requires API client migration, separate milestone. |
| OTel instrumentation | Inline debug view sufficient for single-user REPL. |
| Custom channel per graph instance | All graphs share `[graph]` channel, metadata distinguishes them. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENG-01 | Phase 26 | Pending |
| ENG-02 | Phase 26 | Pending |
| ENG-03 | Phase 26 | Pending |
| ENG-04 | Phase 26 | Pending |
| ENG-05 | Phase 26 | Pending |
| MODE-01 | Phase 27 | Pending |
| MODE-02 | Phase 27 | Pending |
| MODE-03 | Phase 27 | Pending |
| MODE-04 | Phase 27 | Pending |
| MODE-05 | Phase 27 | Pending |
| MODE-06 | Phase 28 | Pending |
| GATE-01 | Phase 28 | Pending |
| GATE-02 | Phase 28 | Pending |
| GATE-03 | Phase 28 | Pending |
| GATE-04 | Phase 28 | Pending |
| GATE-05 | Phase 28 | Pending |
| OBS-01 | Phase 29 | Pending |
| OBS-02 | Phase 29 | Pending |
| OBS-03 | Phase 29 | Pending |
| OBS-04 | Phase 29 | Pending |
| OBS-05 | Phase 29 | Pending |
| OBS-06 | Phase 29 | Pending |
| INT-01 | Phase 26 | Pending |
| INT-02 | Phase 29 | Pending |
| INT-03 | Phase 29 | Pending |

**Coverage:**
- v6.0 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-02-14*
*Last updated: 2026-02-15 after roadmap creation -- all requirements mapped to phases*
