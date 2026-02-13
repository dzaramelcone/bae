# Requirements: Bae — Cortex REPL

**Defined:** 2026-02-13
**Core Value:** DSPy compiles agent graphs from type hints and class names — no manual prompt writing

## v4.0 Requirements

Requirements for cortex REPL. Each maps to roadmap phases.

### REPL (Shell Foundation)

- [ ] **REPL-01**: `bae` with no args launches cortex (default typer command)
- [ ] **REPL-03**: User can execute Python code with top-level await support
- [ ] **REPL-04**: Shift+Tab cycles between NL / Py / Graph / Bash modes
- [ ] **REPL-05**: User sees a mode indicator in the prompt showing current mode
- [ ] **REPL-06**: User can configure custom prompt content (CPU, running tasks, costs, etc.)
- [ ] **REPL-07**: User gets syntax highlighting and multiline editing in Py mode
- [ ] **REPL-08**: User gets tab completion on namespace objects
- [ ] **REPL-10**: Ctrl-C opens a menu to kill running tasks
- [ ] **REPL-11**: Double Ctrl-C kills all tasks, returns to bare cortex
- [ ] **REPL-12**: Ctrl-C with no tasks running exits the process
- [ ] **REPL-13**: Ctrl-D exits with graceful shutdown (tasks cancelled, queues drained)
- [ ] **REPL-14**: Bash mode executes shell commands, output routed to `[bash]` channel

### STORE (Session Store)

- [ ] **STORE-01**: All I/O (input, output, every channel) is labeled, indexed, and persisted to a session store
- [ ] **STORE-02**: Session data is structured for RAG queries (not opaque blobs)
- [ ] **STORE-03**: Context persists across cortex sessions — AI retains project state between launches
- [ ] **STORE-04**: User can inspect what context is stored

### CHAN (Channel I/O)

- [ ] **CHAN-01**: All output is tagged with a channel label and rendered with color-coded prefix
- [ ] **CHAN-02**: User can open a TUI select menu to toggle channel visibility (prompt_toolkit widget)
- [ ] **CHAN-03**: User can access channels as Python objects in the namespace
- [ ] **CHAN-04**: User can enable debug logging mode that captures all channel streams to file
- [ ] **CHAN-05**: Channel integration with bae graph execution without modifying bae source (wrapper pattern)

### NS (Namespace)

- [ ] **NS-01**: Namespace is pre-loaded with bae objects (Node, Graph, Dep, Recall)
- [ ] **NS-02**: `_` holds the last expression result, `_trace` holds the last graph trace
- [ ] **NS-03**: `ns()` callable in namespace lists all objects with types and summaries
- [ ] **NS-04**: `ns(obj)` inspects an object (Graph shows topology, Node shows fields)

### AI (Agent)

- [ ] **AI-01**: `ai` is an async callable object in the namespace — `await ai("question")`
- [ ] **AI-02**: `await ai.fill(NodeClass, context)` calls bae's LM fill directly
- [ ] **AI-03**: `await ai.choose_type([TypeA, TypeB], context)` calls bae's LM choose_type
- [ ] **AI-04**: AI output is routed to the `[ai]` channel
- [ ] **AI-05**: AI receives namespace context (referenced variables, graph topology) when answering
- [ ] **AI-06**: AI can parse and extract Python code from NL conversation for integration into codebase
- [ ] **AI-07**: Prompt engineering for AI operating in NL while producing correct Python/bash/system calls

## v5.0 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Observability

- **OTEL-01**: Session/command/graph/node/LM span hierarchy with OTel instrumentation
- **OTEL-02**: `[otel]` channel for human-readable span output
- **OTEL-03**: InMemorySpanExporter for programmatic span access
- **OTEL-04**: TracedLM wrapper pattern for opt-in instrumentation

### Advanced

- **ADV-01**: Ephemeral spawned interfaces for HitL checkpoints (Ghostty tabs, browser)
- **ADV-02**: Engineering method graph (define/specify/research/brainstorm/choose/implement/test/verify/improve)
- **ADV-03**: Semantic/vector search on context
- **ADV-04**: State snapshots and restore
- **ADV-05**: Celery distribution backend
- **ADV-06**: Hot reloading modules and self-augmenting code

## Out of Scope

| Feature | Reason |
|---------|--------|
| IPython extension | Owns event loop, conflicts with cortex architecture |
| Full-screen TUI | Scrollback terminal sufficient, massive scope |
| Web-based REPL | Jupyter exists, terminal-first |
| Voice/multimodal input | Platform-specific deps, text sufficient |
| Auto-detect NL vs Python | Ambiguous (xonsh proved this), explicit mode switching |
| Prefix-based mode switching | Needless complexity, hotkey cycling is cleaner |
| Plugin/extension system | Python is the extension system — import and add to namespace |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REPL-01 | — | Pending |
| REPL-03 | — | Pending |
| REPL-04 | — | Pending |
| REPL-05 | — | Pending |
| REPL-06 | — | Pending |
| REPL-07 | — | Pending |
| REPL-08 | — | Pending |
| REPL-10 | — | Pending |
| REPL-11 | — | Pending |
| REPL-12 | — | Pending |
| REPL-13 | — | Pending |
| REPL-14 | — | Pending |
| STORE-01 | — | Pending |
| STORE-02 | — | Pending |
| STORE-03 | — | Pending |
| STORE-04 | — | Pending |
| CHAN-01 | — | Pending |
| CHAN-02 | — | Pending |
| CHAN-03 | — | Pending |
| CHAN-04 | — | Pending |
| CHAN-05 | — | Pending |
| NS-01 | — | Pending |
| NS-02 | — | Pending |
| NS-03 | — | Pending |
| NS-04 | — | Pending |
| AI-01 | — | Pending |
| AI-02 | — | Pending |
| AI-03 | — | Pending |
| AI-04 | — | Pending |
| AI-05 | — | Pending |
| AI-06 | — | Pending |
| AI-07 | — | Pending |

**Coverage:**
- v4.0 requirements: 32 total
- Mapped to phases: 0
- Unmapped: 32 ⚠️

---
*Requirements defined: 2026-02-13*
*Last updated: 2026-02-13 after reframe — session store, NL-first, clean bae integration*
