# Project Research Summary

**Project:** Cortex v6.0 Graph Runtime
**Domain:** Concurrent graph execution engine with human-in-the-loop gates integrated in async REPL
**Researched:** 2026-02-15
**Confidence:** HIGH

## Executive Summary

Cortex v6.0 adds concurrent graph execution to the REPL, allowing 10+ graphs to run simultaneously with human input gates, observability, and lifecycle management. The research demonstrates this entire milestone can be built using Python 3.14 stdlib plus existing dependencies (Rich, prompt-toolkit, Pydantic). Zero new packages required. Two new stdlib APIs in Python 3.14 (`asyncio.capture_call_graph` and `asyncio.format_call_graph`) provide purpose-built observability for async task relationships.

The recommended approach uses asyncio.TaskGroup for structured concurrency, asyncio.Future for input gate suspension, and a registry pattern to track running graphs (analogous to existing `_ai_sessions`). Each graph gets its own CortexPrompt implementation that suspends execution via Future instead of blocking on stdin. The graph engine wraps `Graph.arun()` but does NOT modify it — integration happens through dep_cache injection and channel routing, keeping the framework layer clean.

The critical risk is **input gate deadlock**: graphs using `TerminalPrompt.ask()` will compete with prompt_toolkit for stdin, freezing the REPL. Prevention requires a Future-based CortexPrompt that routes through the channel system rather than calling `input()`. Secondary risks include subprocess orphans from cancelled LM calls, channel flooding from concurrent output, and memory leaks from retained graph traces. All have clear mitigation strategies based on existing cortex patterns.

## Key Findings

### Recommended Stack

Zero new dependencies. The entire milestone uses Python 3.14 stdlib + existing packages: Rich 14.3.2, prompt-toolkit 3.0.52, Pydantic 2.12.5.

**Core technologies:**
- **asyncio.TaskGroup** (stdlib): Structured concurrency for multiple graph runs — cancels siblings on failure, preventing runaway LM calls when one graph errors
- **asyncio.Future** (stdlib): Input gate suspension — graph awaits Future, user responds via GRAPH mode, Future resolves with response text
- **asyncio.Semaphore** (stdlib): Throttle concurrent LM calls across all graphs to prevent API saturation
- **asyncio.capture_call_graph** (NEW in 3.14): Debug stuck graphs by showing which tasks await which, zero instrumentation needed
- **dataclasses + time.perf_counter_ns** (stdlib): Metrics collection for per-node timing, LM call counts, dep resolution durations
- **Rich Table + Console(file=StringIO())** (existing dep): Render metrics as ANSI via existing ViewFormatter protocol

**Key integration points:**
- TaskManager.submit() wraps each graph run — existing Ctrl-C menu shows graphs alongside AI/PY/BASH tasks
- ChannelRouter writes graph events to `[graph]` channel with typed metadata — persists to SessionStore automatically
- ViewFormatter protocol renders events — UserView shows summaries, DebugView shows full metadata, no new view types needed initially
- Toolbar gets `make_graphs_widget()` showing active count + pending input badge

### Expected Features

**Must have (table stakes):**
- **Graph Registry with lifecycle management** — track 10+ concurrent graph instances by ID, states (RUNNING/WAITING/DONE/FAILED/CANCELLED), start time, current node
- **GRAPH mode as management hub** — commands for `/run`, `/graphs`, `/kill`, `/trace`, with input routing to pending gates
- **Pending input system** — asyncio.Future-based suspension when graph needs user response, toolbar badge shows waiting count, notification via `[graph]` channel
- **Graph I/O through channels** — structured events (`node_transition`, `dep_resolved`, `input_requested`, `result`, `error`) flow through existing view system
- **Graphs as managed tasks** — integrate with TaskManager for Ctrl-C menu, graceful shutdown, task tracking

**Should have (competitive):**
- **Graph debug views** — inline observability without external tools (LangGraph requires LangSmith/Langfuse) — show node timings, dep durations, LM call times, validation errors
- **Inspect command** — Rich Table showing full trace of running/completed graph with timing and field values
- **Input schema display** — pending gates show field name, type, description from Pydantic so user knows what to provide
- **Cross-mode input shortcut** — `@g1 yes` routes input to graph 1 from any mode, reducing friction

**Defer (v2+):**
- **State snapshots/checkpointing** — LangGraph feature for resuming graphs after process restart. Bae graphs are short-lived (seconds to minutes). YAGNI.
- **Distributed execution** — architecture must not preclude it (keep Graph.arun() as clean coroutine) but don't build Celery/Redis layer now
- **Visual DAG rendering** — Mermaid diagrams exist for static viz, ASCII art in terminal is awkward
- **Auto-retry on validation errors** — defer to DSPy optimization work, don't build retry loops that hide errors
- **Token-level streaming** — requires API client migration, separate milestone
- **Graph-to-graph orchestration** — users compose via custom `__call__` nodes, Python is the orchestration layer

### Architecture Approach

The graph runtime is NOT a new subsystem — it adapts `Graph.arun()` to cortex via four new components: GraphRegistry (tracks definitions and running instances), CortexPrompt (Future-based Prompt implementation), GraphRunner (wraps single execution with channel integration), and toolbar badge. Integration uses existing primitives: dep_cache injection routes CortexPrompt to all nodes without modifying Node or Graph, TaskManager handles lifecycle, ChannelRouter displays events.

**Major components:**
1. **GraphRegistry** (`bae/repl/graphs.py`, NEW) — tracks running graphs by ID, multiplexes input routing, provides `/run`, `/graphs`, `/kill`, `/trace` commands
2. **CortexPrompt** (`bae/repl/graphs.py`, NEW) — implements Prompt protocol using asyncio.Future instead of stdin, writes notifications to `[graph]` channel, suspends graph until user responds
3. **GraphRunner** (`bae/repl/graphs.py`, NEW) — wraps `Graph.arun()` with dep_cache injection (maps `get_prompt` -> CortexPrompt), captures result/error, routes terminal node repr through channel
4. **Graph mode dispatch** (`shell.py`, MODIFIED) — `/commands` for management, `@gid response` for targeted input routing, bare text routes to only pending graph
5. **Toolbar pending widget** (`toolbar.py`, MODIFIED) — shows `[N pending]` badge when any graph waits for input, visible in all modes

**Modified files (minimal surface):**
- `bae/graph.py`: Add `dep_cache` param to `arun()` (additive, backward compatible)
- `bae/repl/shell.py`: Replace `_run_graph` stub, add GraphRegistry to `__init__`, add pending widget
- `bae/repl/toolbar.py`: Add `make_pending_widget()`
- `bae/repl/views.py`: Add `input_gate` rendering in UserView

**Unchanged files:** `bae/node.py`, `bae/resolver.py`, `bae/markers.py`, `bae/result.py`, `bae/lm.py`, `bae/work/prompt.py`, `bae/work/new_project.py`, `bae/repl/channels.py`, `bae/repl/tasks.py`, `bae/repl/store.py`

### Critical Pitfalls

1. **Input gate deadlock** — graphs calling `TerminalPrompt.ask()` compete with prompt_toolkit for stdin, freezing REPL. **Mitigation:** CortexPrompt creates asyncio.Future, writes notification to `[graph]` channel, awaits Future (graph suspends), user responds via GRAPH mode, Future resolves. Never call `input()` from background tasks.

2. **Subprocess orphans on cancellation** — cancelling graph task doesn't kill Claude CLI subprocesses from LM calls. **Mitigation:** Wrap `process.communicate()` with `try/except CancelledError: process.kill(); await process.wait(); raise`. Track processes per graph in registry for bulk cleanup.

3. **Event loop starvation** — `Graph.arun()` loop with many synchronous Pydantic validations between `await` points blocks event loop, freezing toolbar. **Mitigation:** Add `await asyncio.sleep(0)` at top of each graph iteration to yield to event loop.

4. **Channel flooding** — 10+ concurrent graphs writing to `[graph]` channel creates unreadable interleaved output. **Mitigation:** Use existing `metadata["label"]` support for per-graph prefixes (`[graph:g1]`), add output policy (visible/quiet/silent), buffer output and flush on completion.

5. **Memory leak from retained traces** — GraphResult.trace holds every node instance with resolved deps and LM responses. **Mitigation:** Registry distinguishes running/completed/archived states, archives old graphs (drops trace, keeps terminal node + metadata), max_completed limit triggers auto-archival.

## Implications for Roadmap

Based on research, suggested phase structure prioritizes foundation (registry + engine) before UX features (commands, debug views). Input gate system is hardest and most critical — build after infrastructure exists.

### Phase 1: Foundation (Registry + Engine + TaskManager Integration)

**Rationale:** GraphRegistry is the skeleton everything hangs on. Without registry, nothing to list/inspect/input. Without engine emitting events, views have nothing to render. This phase delivers usable concurrent graph execution (no input gates yet) and integrates with TaskManager for Ctrl-C menu.

**Delivers:**
- `GraphRegistry` class tracking running graphs by ID with lifecycle states
- Graph engine coroutine wrapping `Graph.arun()` with lifecycle event emission
- Events to `[graph]` channel with typed metadata (`node_transition`, `result`, `error`, `lifecycle`)
- `TaskManager.submit()` integration — graphs appear in Ctrl-C menu
- Timing instrumentation per node (start/end timestamps via perf_counter_ns)
- Modified `Graph.arun()` accepting `dep_cache` parameter

**Addresses features:** Graph Registry, Graphs as Managed Tasks, Graph I/O Through Channels, Graph Lifecycle Notifications

**Avoids pitfalls:** #3 (event loop starvation via sleep(0)), #2 (subprocess cleanup on CancelledError), #10 (TaskManager pruning)

**Research flag:** Standard patterns, well-documented asyncio primitives. Skip research-phase.

### Phase 2: GRAPH Mode Commands

**Rationale:** Commands make the registry usable. User can start, monitor, cancel graphs. This is a functional graph runtime without input gates yet — graphs that don't need user input work end-to-end.

**Delivers:**
- Command parsing in `_run_graph()` (split on space, match verb)
- `/run <name>` — evaluate expression, submit graph to engine
- `/graphs` — show all running graphs with state, timing, current node
- `/kill <id>` — revoke via registry -> TaskManager
- `/trace <id>` — show node execution history as Rich Table
- Lifecycle events logged to `[graph]` channel (launched, completed, failed, cancelled)

**Addresses features:** GRAPH Mode as Management Hub, Inspect Command (basic), Graph Debug Views (foundation)

**Avoids pitfalls:** #4 (channel flooding via per-graph labels in metadata)

**Research flag:** Standard patterns (command dispatch, Rich Table rendering). Skip research-phase.

### Phase 3: Pending Input System (Human-in-the-Loop Gates)

**Rationale:** Input gates are the hardest feature and core differentiator. Building after registry/commands means infrastructure for state transitions, event emission, command dispatch already exists. Input system plugs into proven primitives.

**Delivers:**
- `CortexPrompt` class: asyncio.Future + value slot + schema info
- Engine integration: detect input bridge in dep resolution, transition to WAITING state
- `@gid <value>` input routing in GRAPH mode (with implicit routing when single pending graph)
- Toolbar pending badge widget (`make_pending_widget()`)
- Input schema display in `/graphs` output (field name, type, description from Pydantic)
- `input_requested` event to `[graph]` channel with question text

**Addresses features:** Pending Input System, Pending Input Notification UX, Input Schema Display

**Avoids pitfalls:** #1 (input gate deadlock — Future-based, not stdin), #5 (Event race — per-request Futures, not shared), #8 (cancellation during deps — fresh dep_cache per run)

**Research flag:** Novel composition of existing patterns (Future + Prompt protocol + dep_cache). Standard asyncio but unique to this codebase. Suggest `/gsd:research-phase` focused on dep injection and concurrent prompt routing.

### Phase 4: Observability & Polish

**Rationale:** After core functionality (registry, commands, input gates) works, layer on enhanced observability using Python 3.14's new introspection APIs and Rich formatting.

**Delivers:**
- Graph Debug View with node timings, dep durations, LM call times
- `/inspect <id>` with Rich Tree rendering (upgrade from basic `/trace`)
- `asyncio.capture_call_graph()` integration for debugging stuck graphs
- Per-graph output policy (visible/quiet/silent)
- Cross-mode `!<id>` shortcut for quick input responses
- Memory metrics (RSS delta per graph run via resource.getrusage)

**Addresses features:** Graph Debug Views (full), Inspect Command (enhanced), Cross-Mode Input Shortcut

**Avoids pitfalls:** #6 (memory leak — archive completed graphs), #7 (SessionStore contention — batch commits), #9 (print interleaving — single print calls)

**Research flag:** Python 3.14 `capture_call_graph` API is new (verified in docs). Standard patterns otherwise. Skip research-phase, consult docs during implementation.

### Phase Ordering Rationale

- **Foundation first (Phase 1):** Registry and engine are dependencies for everything else. Can't build commands without registry to query, can't build input gates without engine to emit events.
- **Commands before input gates (Phase 2):** Input gates are the hardest problem (Future suspension, routing, schema extraction). Building commands first proves the registry/engine work for simpler cases (graphs without input gates).
- **Input gates third (Phase 3):** Once registry, events, commands exist, input gates are "just" a Future-based Prompt implementation + routing logic. The infrastructure supports it.
- **Observability last (Phase 4):** Enhanced views, metrics, debugging tools are polish on a working system. Users can run graphs, manage them, respond to input gates without these. Nice-to-have, not blocking.

This avoids pitfalls by tackling the hardest integration point (input gates + event loop + stdin contention) only after simpler infrastructure is proven. Each phase is independently testable and deliverable.

### Research Flags

Phases needing deeper research during planning:
- **Phase 3 (Pending Input System):** Novel composition — Future-based prompt + dep_cache injection + concurrent routing. Standard primitives but unique integration. Suggest focused research on: dep injection patterns for graph-scoped resources, asyncio.Future suspension semantics under cancellation, prompt_toolkit output from background tasks.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** asyncio.TaskGroup, dataclasses, perf_counter_ns, TaskManager integration — all well-documented stdlib patterns
- **Phase 2 (GRAPH Mode Commands):** String dispatch, Rich Table rendering, registry query methods — established patterns in existing codebase
- **Phase 4 (Observability):** capture_call_graph API is new but documented, Rich formatting is proven, metrics are dataclass + timing — standard

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations verified against Python 3.14.3 docs, existing pyproject.toml, installed packages. Zero dependencies inferred, all verified. |
| Features | HIGH | LangGraph, Prefect, Temporal, CrewAI patterns researched via WebSearch + official docs. Table stakes vs differentiators derived from ecosystem comparison. |
| Architecture | HIGH | Direct codebase analysis of all integration points (TaskManager, ChannelRouter, ViewFormatter, Graph.arun(), resolver). dep_cache injection verified via code trace. |
| Pitfalls | HIGH | Input gate deadlock traced through prompt.py + shell.py source. Subprocess orphan confirmed via TaskManager.revoke() + lm.py analysis. Event loop starvation verified via Graph.arun() loop structure. |

**Overall confidence:** HIGH

All four research areas grounded in verifiable sources: official Python docs, installed package versions, direct codebase inspection, documented ecosystem patterns. No speculative recommendations.

### Gaps to Address

**Optimal LM call concurrency limit:** STACK.md recommends `asyncio.Semaphore` with `max_concurrent_lm_calls` but notes empirical tuning needed. Claude CLI backend latency characteristics unknown. **Mitigation:** Start with conservative limit (3), expose as runtime config, adjust based on observed behavior.

**dep_cache injection thread safety under high concurrency:** Architecture verified via code trace that dep_cache is per-run (local variable in arun(), graph.py:308). But with 10+ graphs, race conditions possible if dep functions have shared mutable state. **Mitigation:** Document that dep functions must be stateless or return new instances. Test with 20+ concurrent graphs.

**SessionStore write throughput at scale:** PITFALLS.md identifies synchronous commits as bottleneck. Batch commit mitigation proposed but not validated. **Mitigation:** Instrument store.record() during Phase 1 testing, implement batching if cumulative time exceeds 50ms/second.

**Input gate timeout policy:** Prevention for Pitfall #1 suggests `asyncio.wait_for(gate_event.wait(), timeout=300)`. Correct timeout value unknown — depends on use case (quick confirmation vs long-form input). **Mitigation:** Make timeout configurable per graph or per gate, default to 5 minutes, log timeouts as warnings not errors.

## Sources

### Primary (HIGH confidence)
- [Python 3.14 What's New](https://docs.python.org/3/whatsnew/3.14.html) — asyncio TaskGroup improvements, introspection APIs
- [asyncio Call Graph Introspection](https://docs.python.org/3/library/asyncio-graph.html) — capture_call_graph, format_call_graph, print_call_graph API
- [asyncio Tasks](https://docs.python.org/3/library/asyncio-task.html) — TaskGroup, timeout, Future, Event, Queue, Semaphore
- [prompt_toolkit 3.0.52 docs](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/reference.html) — patch_stdout, print_formatted_text, refresh_interval
- [Rich Tables](https://rich.readthedocs.io/en/stable/tables.html) — Table API for metrics rendering
- Direct codebase analysis: `bae/graph.py`, `bae/repl/tasks.py`, `bae/repl/channels.py`, `bae/repl/views.py`, `bae/repl/shell.py`, `bae/repl/toolbar.py`, `bae/resolver.py`, `bae/work/prompt.py` (all integration points verified)

### Secondary (MEDIUM confidence)
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) — interrupt()/Command(resume=) pattern
- [LangGraph Streaming](https://docs.langchain.com/oss/python/langgraph/streaming) — Event streaming modes (values, updates, debug)
- [Prefect Interactive Workflows](https://docs.prefect.io/v3/advanced/interactive) — pause_flow_run(wait_for_input=PydanticModel)
- [Temporal Signals](https://james-carr.org/posts/2026-02-03-temporal-process-manager/) — Signal-based wait patterns
- [SQLite WAL docs](https://sqlite.org/wal.html) — Concurrent read/write behavior
- [CPython #88050](https://github.com/python/cpython/issues/88050) — Subprocess orphans on task cancellation
- [prompt-toolkit #1866](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1866) — Thread safety of print_formatted_text
- [Trio #637](https://github.com/python-trio/trio/issues/637) — Event.clear() race conditions

---
*Research completed: 2026-02-15*
*Ready for roadmap: yes*
