# Bae

## What This Is

A framework for building agent graphs where nodes are Pydantic models and topology comes from type hints. Nodes are "context frames" -- their fields assemble the information the LLM needs to produce the next node. Class names are instructions, return types are output schemas, and Field(description=...) provides explicit per-field hints. Four field sources: Dep(callable) for external data, Recall() for graph state, Gate() for human-in-the-loop input, and plain fields for LLM generation. JSON structured output with constrained decoding for reliable fills. Fully async with parallel dep resolution and concurrent graph execution engine. Ships with cortex -- an NL-first augmented REPL where human and AI collaborate in a shared namespace, with pluggable view formatters, native tool call translation, and graph observability.

## Core Value

DSPy compiles agent graphs from type hints and class names - no manual prompt writing.

## Requirements

### Validated

- ✓ Node base class (Pydantic BaseModel) -- v1.0
- ✓ Graph discovery from return type hints -- v1.0
- ✓ Graph execution loop -- v1.0
- ✓ LM protocol (make, decide) -- v1.0
- ✓ PydanticAIBackend -- v1.0
- ✓ ClaudeCLIBackend -- v1.0
- ✓ Terminal node detection (returns None) -- v1.0
- ✓ node_to_signature() with DSPy Signature generation -- v1.0
- ✓ BootstrapFewShot optimization with trace collection -- v1.0
- ✓ OptimizedLM with compiled prompt loading -- v1.0
- ✓ Dep(callable) with DAG resolution and dep chaining -- v2.0
- ✓ Recall() for graph state via backward trace search -- v2.0
- ✓ Context marker removed -- v2.0
- ✓ Bind marker removed -- v2.0
- ✓ Implicit LM (graph-level config) -- v2.0
- ✓ Start node fields = caller-provided input -- v2.0
- ✓ Terminal node fields = response schema -- v2.0
- ✓ JSON structured fill with constrained decoding -- v2.0
- ✓ Field(description=...) for explicit LLM hints, docstrings inert -- v2.0
- ✓ All LM backends async (PydanticAI, ClaudeCLI, DSPy) -- v3.0
- ✓ Graph run/arun split with asyncio.run() CLI boundary -- v3.0
- ✓ Node.__call__() async -- v3.0
- ✓ Parallel dep resolution via asyncio.gather() -- v3.0
- ✓ Sync/async Dep(callable) mixing -- v3.0
- ✓ Nested model preservation in fill() -- v3.0
- ✓ Async REPL shell with 4 modes (NL/PY/GRAPH/BASH) -- v4.0
- ✓ Session store with SQLite + FTS5 for cross-session memory -- v4.0
- ✓ Channel-based labeled output with visibility toggle -- v4.0
- ✓ Reflective namespace with bae object seeding and introspection -- v4.0
- ✓ AI agent as namespace-callable with Claude CLI backend -- v4.0
- ✓ AI eval loop (extract-execute-feedback) with multi-session routing -- v4.0
- ✓ Task lifecycle with process group kill and customizable toolbar -- v4.0
- ✓ `<run>` execution convention with executable/illustrative separation -- v5.0
- ✓ Tool call translation (R, W, E, G, Grep) with native execution -- v5.0
- ✓ ViewFormatter protocol with pluggable channel display -- v5.0
- ✓ UserView Rich Panel execution display with buffered grouping -- v5.0
- ✓ DebugView raw metadata display -- v5.0
- ✓ AISelfView structured feedback tags -- v5.0
- ✓ Runtime view cycling (Ctrl+V) with toolbar indicator -- v5.0
- ✓ Concise tool call display with summaries -- v5.0
- ✓ GraphRegistry with concurrent lifecycle tracking (RUNNING/WAITING/DONE/FAILED/CANCELLED) -- v6.0
- ✓ Graph engine wraps arun() with lifecycle events, backend-agnostic -- v6.0
- ✓ Per-node timing and dep call duration capture via TimingLM -- v6.0
- ✓ dep_cache parameter on Graph.arun() for cortex injection -- v6.0
- ✓ Graphs as managed tasks via TaskManager (Ctrl-C menu) -- v6.0
- ✓ graph() factory with flattened params and auto-engine-registration -- v6.0
- ✓ Gate() marker for human-in-the-loop input via asyncio.Future -- v6.0
- ✓ Toolbar badge for pending gate count, @g cross-mode resolution -- v6.0
- ✓ OutputPolicy (VERBOSE/NORMAL/QUIET/SILENT) per graph run -- v6.0
- ✓ Graph lifecycle events through [graph] channel with typed metadata -- v6.0
- ✓ RSS memory delta measurement per graph run -- v6.0
- ✓ 10+ concurrent graphs without event loop starvation -- v6.0
- ✓ Graph events persist to SessionStore for cross-session history -- v6.0
- ✓ Agent core extraction (extract_executable, agent_loop) to bae/agent.py -- v6.0

### Active

(No active milestone -- planning next)

### Out of Scope

- Bind for explicit writes -- implicit trace search is clean enough (YAGNI)
- Validation error retry loops -- DSPy optimization may solve this
- Dynamic fan-out (runtime N) -- async __call__ with manual gather is the escape hatch
- Declarative fan-out (DepMap etc) -- deferred until real use case demands it
- Semantic/vector search on context -- deferred
- DuckDB query backends -- deferred
- Celery distribution -- YAGNI, architecture must not preclude it
- Hot reloading / self-augmenting code -- deferred
- State snapshots/restore -- deferred
- IPython extension -- owns event loop, conflicts with cortex architecture
- Full-screen TUI -- scrollback terminal sufficient
- Auto-detect NL vs Python -- ambiguous, explicit mode switching
- Plugin/extension system -- Python is the extension system
- AI bash dispatch -- security surface, AI uses Python only
- Token-by-token streaming -- requires API client migration
- Custom view plugins -- YAGNI, three built-in views sufficient
- GRAPH mode REPL commands -- built in v6.0, removed; programmatic API sufficient (v6.0 retro)

## Context

Shipped v6.0 Graph Runtime. 6,130 lines in bae/, 10,368 lines in tests/.

Tech stack: Python 3.14+, Pydantic, prompt_toolkit, Rich, Typer.

One LM backend: ClaudeCLIBackend with v1 (make/decide) and v2 (choose_type/fill) methods, all async. PydanticAIBackend and DSPyBackend removed — Claude CLI subprocess is the only backend.

Cortex architecture: Custom REPL on prompt_toolkit with 3 modes (NL/PY/BASH) sharing one Python namespace. Graph engine runs concurrent graphs as managed tasks with lifecycle tracking, per-node timing, and human-in-the-loop gates (asyncio.Future). All output flows through labeled channels with pluggable view formatters (UserView, DebugView, AISelfView). AI agent lives in namespace as callable object with extracted agent core (bae/agent.py). SessionStore (SQLite + FTS5) persists all I/O including graph lifecycle events for cross-session memory.

Reference implementation: `examples/ootd.py` -- outfit recommendation graph with graph() factory.

647 tests passing, 5 skipped.

**Field annotation summary:**

| Annotation | Meaning | Source |
|------------|---------|--------|
| `Dep(fn)` | Bae calls a function to fill this field | External service/function |
| `Recall()` | Bae searches the trace to fill this field | Prior node in graph execution |
| `Gate()` | Bae suspends and asks the user to fill this field | Human-in-the-loop input |
| *(none)* | LLM fills this field | Previous node's context -> LLM generation |

## Constraints

- **Python**: 3.14+ -- PEP 649 eliminates forward ref issues
- **Dependencies**: pydantic, prompt_toolkit, rich, typer, pygments
- **Interface**: Async -- parallel dep resolution, subgraph composition

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Class name as primary prompt source | Cleaner than docstring-heavy approach | ✓ Good -- enforced in v2.0, docstrings made inert |
| Two-step decide (pick type, then fill) | Avoids slow oneOf schemas | ✓ Good -- became choose_type/fill in v2.0 |
| Nodes are context frames | Fields ARE prompt context, class name IS instruction, return type IS output schema | ✓ Good -- core v2.0 paradigm |
| Dep(callable) for external data | Replaces v1 service injection via __call__ params | ✓ Good -- DAG resolution with topo sort |
| Recall() for graph state | Backward trace search with MRO type matching | ✓ Good -- replaced Bind |
| JSON structured fill | Claude CLI --json-schema for constrained decoding | ✓ Good -- replaced XML |
| Full async, not threading | Correct long-term play, formulaic conversion | ✓ Good -- native async across all backends |
| getattr over model_dump in fill | Preserves nested BaseModel instances | ✓ Good -- fixed v3.0 gap |
| prompt_toolkit REPL (not IPython) | Cortex owns event loop, full control | ✓ Good -- clean lifecycle |
| Claude CLI subprocess for AI | No API key needed, session persistence, prompt caching | ✓ Good -- zero config |
| Shared namespace across modes | Single Python dict, all objects accessible everywhere | ✓ Good -- enables AI eval loop |
| Channels for output, store.record for input | Clean separation: channels = display + persist, input = persist only | ✓ Good -- no bare print() |
| sys.modules cortex registration | REPL-defined classes resolve annotations without production changes | ✓ Good -- zero bae/ modifications |
| Eval loop inside AI.__call__ | Self-contained, testable, not in shell dispatch | ✓ Good -- clean separation |
| Inline task menu (not dialog) | Simpler UX, keyboard-driven, permanent scrollback | ✓ Good -- replaced checkboxlist_dialog |
| Process group kill | start_new_session + os.killpg for clean subprocess tree cleanup | ✓ Good -- no orphan processes |
| xml_tag convention for execution | 100% compliance across all Claude tiers, clean separation | ✓ Good -- `<run>` blocks only |
| Tool call interception over rejection | Translate and execute natively rather than reject with error | ✓ Good -- productive tool use |
| ViewFormatter as Protocol | Strategy pattern via structural typing, zero circular imports | ✓ Good -- pluggable display |
| dep_cache as hook injection | GATE_HOOK_KEY and DEP_TIMING_KEY sentinels in dep_cache | ✓ Good -- zero framework changes for cortex features |
| asyncio.Future for gates | Graph suspends cleanly, no busy-wait or polling | ✓ Good -- clean integration with event loop |
| _graph_ctx contextvar | graph() auto-registers with engine when called inside REPL | ✓ Good -- zero explicit setup for users |
| graph() flattens BaseModel params | Flat kwargs instead of constructing Pydantic models | ✓ Good -- natural CLI UX |
| GRAPH mode removal | Built then removed -- programmatic API via PY mode sufficient | ✓ Good -- reduced surface area, all capabilities survive |
| _lifecycle context manager | Shared engine lifecycle for _execute and _wrap_coro | ✓ Good -- eliminated duplication |
| Agent core as module functions | Stateless, no class -- caller owns session state | ✓ Good -- clean decoupling from REPL |

## Known Issues

- GraphRegistry.active() and .get() orphaned after GRAPH mode removal (functional, unused)
- Phase 30 VERIFICATION.md stale (AgenticBackend removed post-verification)

---
*Last updated: 2026-02-15 after stale reference cleanup*
