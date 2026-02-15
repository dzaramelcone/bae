# Feature Landscape: Cortex v6.0 Graph Runtime

**Domain:** Concurrent graph execution engine with human-in-the-loop input gates and observability, embedded in an async REPL
**Researched:** 2026-02-15
**Overall confidence:** HIGH for graph registry/lifecycle and TaskManager integration (well-understood asyncio patterns over proven primitives); HIGH for pending input via asyncio.Event (standard pattern); MEDIUM for debug views (novel composition of existing view system); MEDIUM for concurrent 10+ graphs (needs memory/backpressure profiling under load)

---

## Existing Foundation (Already Built)

Every v6.0 feature layers over existing v4.0/v5.0 primitives. No greenfield modules -- all new behavior composes what exists.

| Component | File | What It Does | v6.0 Hook Point |
|-----------|------|-------------|-----------------|
| `Graph.arun()` | `graph.py` | Async execution loop: resolve deps, recalls, LM fill, route | Graph engine wraps this with lifecycle events + input gates |
| `TaskManager` | `tasks.py` | Submit/revoke/shutdown asyncio tasks with process group cleanup | Graph runs become managed tasks; registry tracks by graph ID |
| `TrackedTask` | `tasks.py` | Dataclass: task, name, mode, task_id, state, process | Extended or wrapped for graph-specific metadata (graph type, node position) |
| `ChannelRouter` | `channels.py` | Registry of named output channels with write dispatch | Graph I/O flows through `[graph]` channel with metadata typing |
| `ViewFormatter` | `channels.py` | Protocol for pluggable channel display (render method) | New GraphDebugView renders timing, dep calls, validation errors |
| `UserView` | `views.py` | Rich Panel display for AI code execution | Extended to handle graph event metadata types |
| `DebugView` | `views.py` | Raw metadata display | Already shows all metadata -- graph events visible for free |
| `ToolbarConfig` | `toolbar.py` | Named widget registry for bottom toolbar | New pending-input badge widget + graph count widget |
| `Mode.GRAPH` | `modes.py` | REPL input mode (currently stub) | Becomes the management hub: list, inspect, cancel, provide input |
| `channel_arun()` | `shell.py` | Wraps graph.arun() with logging capture + channel routing | Replaced by full graph engine with lifecycle events |
| `SessionStore` | `store.py` | SQLite+FTS5 persistence for all I/O | Graph events persisted for cross-session graph history |

---

## Table Stakes

Features users expect from a graph runtime inside a REPL. Missing any of these makes the system feel broken or incomplete.

### 1. Graph Registry with Lifecycle Management

| Aspect | Detail |
|--------|--------|
| **Why expected** | Running 10+ concurrent graphs with no way to list, inspect, or cancel them is unusable. Every workflow engine (Prefect, Temporal, LangGraph) provides a run registry with lifecycle states. |
| **Complexity** | Low-Med |
| **Depends on** | `TaskManager` (wraps or extends), `ChannelRouter` (lifecycle events) |
| **What it is** | A `GraphRegistry` that tracks running graph instances by ID. Each entry holds: graph type (class name), start time, current node, state (running/waiting/done/failed/cancelled), the underlying `TrackedTask`, and input fields schema. |
| **Lifecycle states** | `PENDING` (created, not yet started), `RUNNING` (executing nodes), `WAITING` (paused at input gate), `DONE` (terminal node reached), `FAILED` (exception), `CANCELLED` (user-revoked) |
| **Ecosystem pattern** | LangGraph uses thread_id + checkpointer. Prefect uses flow run IDs with state transitions. Temporal uses workflow IDs with execution state. Our pattern is simpler: in-memory dict keyed by auto-incrementing ID, since all graphs run in one process. No need for distributed state. |
| **Key design** | Registry lives on `CortexShell` (like `TaskManager`). Each graph run gets an ID visible in toolbar and GRAPH mode. Registry delegates to `TaskManager.submit()` for the actual asyncio task, but adds graph-specific metadata on top. |

### 2. Graph Mode as Management Hub

| Aspect | Detail |
|--------|--------|
| **Why expected** | GRAPH mode currently prints a stub message. Users switching to GRAPH mode expect to interact with graphs. Without commands, the mode is dead weight. |
| **Complexity** | Med |
| **Depends on** | Graph Registry, text command parsing |
| **What it is** | GRAPH mode input is parsed as commands (not arbitrary text). Commands: `list` (show running/waiting/done graphs), `inspect <id>` (show trace, current node, timing), `cancel <id>` (revoke graph), `input <id> <value>` (provide pending input), `run <expr>` (start a graph from namespace). |
| **Ecosystem pattern** | LangGraph Studio provides a visual graph management UI. We provide the same capabilities as text commands in a REPL -- appropriate for a terminal-first tool. |
| **Key design** | Commands are simple string dispatch (not a parser framework). Pattern: split on first space, match verb, dispatch. No need for argparse or click -- YAGNI. |

### 3. Graph Execution Engine (arun wrapper with lifecycle hooks)

| Aspect | Detail |
|--------|--------|
| **Why expected** | `channel_arun()` in shell.py is a minimal wrapper that captures logs. A real engine needs to emit structured events at each node transition so the view system, registry, and store can react. |
| **Complexity** | Med |
| **Depends on** | `Graph.arun()`, `ChannelRouter`, Graph Registry |
| **What it is** | A coroutine that wraps `Graph.arun()` but intercepts the execution loop to emit events: `graph_started`, `node_entered`, `deps_resolved`, `lm_called`, `node_exited`, `input_requested`, `graph_completed`, `graph_failed`. Events flow through the `[graph]` channel with typed metadata. |
| **Ecosystem pattern** | LangGraph streams events via `astream_events()` with layered modes (values, updates, debug, custom). Langfuse captures spans with start/end times. Our approach: emit events through the existing channel system, which already records to store and renders through views. No need for a separate event streaming API. |
| **Key design** | The engine does NOT modify `Graph.arun()` in `bae/graph.py`. Instead, it wraps the execution by providing instrumented deps and callbacks. The graph module stays clean. The engine lives in `bae/repl/` (cortex layer, not framework layer). |

### 4. Pending Input System (Human-in-the-Loop Gate)

| Aspect | Detail |
|--------|--------|
| **Why expected** | Graphs with user gates (confirmation deps, input collection) currently have no way to pause and request input from the user inside cortex. The graph either blocks forever or skips the gate. This is the core reason for v6.0. |
| **Complexity** | Med-High |
| **Depends on** | Graph Registry (state transitions), asyncio.Event (pause/resume), ChannelRouter (notification), ToolbarConfig (badge) |
| **What it is** | When a graph node's dep function needs user input, it `await`s an `asyncio.Event`. The graph engine detects this, transitions the graph to `WAITING` state, emits an `input_requested` event with the input schema (field name, type, description), and the user provides input via GRAPH mode (`input <id> <value>`) or an inline prompt. The event is set, the dep resolves, and graph execution continues. |
| **Ecosystem pattern** | LangGraph uses `interrupt()` which raises a special exception caught by the runtime, saves state via checkpointer, and resumes via `Command(resume=value)`. Prefect uses `pause_flow_run(wait_for_input=MyModel)` with Pydantic model schemas. Temporal uses Signals. Our pattern is closest to Prefect's: the dep function defines what input it needs (via its return type or a parameter), and the engine provides a bridge between the dep's await and the REPL's input. |
| **Key design** | The input gate is a Dep function that receives an `InputBridge` (or similar) injected by the engine. The bridge holds an `asyncio.Event` and a value slot. `await bridge.request("Confirm deployment?")` sets the event to wait, emits the notification, and suspends until the user responds. This keeps the gate mechanism in dep-space (no changes to Node or Graph). |

### 5. Pending Input Notification UX

| Aspect | Detail |
|--------|--------|
| **Why expected** | If a graph is waiting for input and the user is in NL or PY mode, they need to know. Silent blocking is a UX failure. |
| **Complexity** | Low |
| **Depends on** | ToolbarConfig (badge widget), Graph Registry (waiting state query) |
| **What it is** | A toolbar widget that shows a badge when any graph is in WAITING state. Format: `[2 pending]` in a distinct color (e.g., yellow). The badge is a simple lambda that queries the registry for waiting count. prompt_toolkit's `refresh_interval=1.0` (already set on the PromptSession) ensures the toolbar updates within 1 second of state change. In GRAPH mode, pending inputs also print inline when the user enters the mode or types `list`. |
| **Ecosystem pattern** | LangGraph Studio shows interrupted threads in a sidebar. Prefect shows paused flow runs in the UI dashboard. Terminal REPLs have no standard pattern -- this is a differentiator for cortex. |
| **Key design** | The toolbar widget is the minimal notification. No sound, no interrupt of current mode, no forced mode switch. The user notices the badge and switches to GRAPH mode voluntarily. This respects the "shush mode" philosophy -- background graphs don't intrude. |

### 6. Graph I/O Through Channel/View System

| Aspect | Detail |
|--------|--------|
| **Why expected** | Graph output currently goes to a single `[graph]` channel write at the end. Real graphs produce intermediate output at each node -- users need to see progress, especially for long-running graphs. |
| **Complexity** | Low-Med |
| **Depends on** | `ChannelRouter`, `ViewFormatter` implementations, graph engine events |
| **What it is** | The graph engine writes structured events to the `[graph]` channel with metadata typing: `type: "node_transition"`, `type: "dep_resolved"`, `type: "input_requested"`, `type: "result"`, `type: "error"`. The existing view system renders these appropriately -- UserView shows concise progress lines, DebugView shows full metadata. |
| **Ecosystem pattern** | LangGraph's streaming modes (values, updates, debug) map directly to our view system. "updates" mode = UserView showing node transitions. "debug" mode = DebugView showing everything. We achieve the same separation with zero new infrastructure. |
| **Key design** | Metadata `type` field drives rendering, exactly as v5.0 established for AI execution display. No new rendering pipeline needed -- the pattern is proven. |

### 7. Graph Lifecycle Notifications

| Aspect | Detail |
|--------|--------|
| **Why expected** | When a graph starts, completes, fails, or needs input, the user should see a message even if they are in a different mode. Without notifications, graphs complete silently and the user has to poll via `list`. |
| **Complexity** | Low |
| **Depends on** | `ChannelRouter`, `[graph]` channel visibility |
| **What it is** | Key lifecycle transitions emit writes to `[graph]` channel: `"graph:3 started (AnalyzeRequest)"`, `"graph:3 completed in 4.2s"`, `"graph:3 failed: DepError on FetchData"`, `"graph:3 waiting for input: confirm_deploy"`. These appear in scrollback regardless of current mode (the `[graph]` channel is always visible by default). |
| **Ecosystem pattern** | Standard in all workflow engines. Prefect shows toast notifications. Temporal logs state transitions. Terminal UX: scrollback lines with channel prefix, same as current `[debug]` task notifications. |

### 8. Graphs as Managed Tasks (TaskManager Integration)

| Aspect | Detail |
|--------|--------|
| **Why expected** | Graphs are async coroutines. The TaskManager already handles async task lifecycle. Graphs must integrate with the existing Ctrl-C kill menu, task count widget, and graceful shutdown. |
| **Complexity** | Low |
| **Depends on** | `TaskManager.submit()`, Graph Registry |
| **What it is** | When a graph starts, the engine calls `tm.submit(engine_coro, name=f"graph:{id}:{graph_type}", mode="graph")`. The returned `TrackedTask` is stored in the Graph Registry entry. Ctrl-C menu shows graph tasks alongside other tasks. `tm.revoke(task_id)` cancels the graph and transitions registry state to CANCELLED. |
| **Ecosystem pattern** | Universal. Every async framework uses task tracking. The innovation here is zero -- this is wiring existing pieces together. |

---

## Differentiators

Features that set cortex apart from other graph runtime environments. Not expected, but transform the experience.

### 1. Graph Debug Views (Observability Without External Tools)

| Aspect | Detail |
|--------|--------|
| **Value proposition** | LangGraph requires LangSmith or Langfuse (external services) for graph observability. CrewAI requires AgentOps. Cortex provides observability inline in the terminal -- no external service, no API key, no dashboard tab. The DebugView already shows raw metadata; a GraphDebugView shows graph-specific observability: node timings, dep call durations, LM call durations, validation errors, memory usage per node. |
| **Complexity** | Med |
| **Depends on** | ViewFormatter protocol, graph engine events with timing metadata, `[graph]` channel |
| **What it is** | A specialized view (or UserView extension) that renders graph events with rich observability data. When the user is in debug view mode (Ctrl+V), graph events show: `[graph:3] AnalyzeRequest -> GenerateCode (1.2s, 2 deps resolved in 0.3s, LM fill in 0.9s)`. In user view, the same event shows: `[graph:3] -> GenerateCode`. Same data, different verbosity. |
| **Key metrics** | Node execution time, dep resolution time (per dep), LM call time, total graph time, node count, validation error count. All computed from event timestamps -- no external instrumentation library needed. |

### 2. Graph Inspect Command (Trace Explorer)

| Aspect | Detail |
|--------|--------|
| **Value proposition** | `inspect <id>` shows the full trace of a running or completed graph: each node visited, field values, timing, which deps were called, which path the LM chose at decision points. This is LangSmith's trace view, but in your terminal. |
| **Complexity** | Med |
| **Depends on** | Graph Registry (stores trace), Rich Table/Tree rendering |
| **What it is** | GRAPH mode command that renders the graph's trace as a Rich Table or Tree. Columns: node type, fields summary, timing, dep calls, LM decision. For running graphs, shows progress up to current node. For completed graphs, shows full trace with terminal node highlighted. |

### 3. Input Schema Display for Pending Inputs

| Aspect | Detail |
|--------|--------|
| **Value proposition** | When a graph is waiting for input, telling the user "graph:3 waiting for input" is insufficient. Showing the field name, type, and description (from the Pydantic model or dep function signature) tells them exactly what to provide. |
| **Complexity** | Low |
| **Depends on** | Pending input system, Pydantic field introspection |
| **What it is** | The `input_requested` event includes schema info extracted from the dep function or the awaited type. `list` command shows: `graph:3 WAITING - confirm_deploy: bool ("Confirm deployment to prod?")`. The user knows exactly what to type: `input 3 yes`. |
| **Ecosystem pattern** | Prefect's `wait_for_input` shows Pydantic model fields in the UI. LangGraph's `interrupt()` passes a JSON-serializable value as the prompt. Our approach: extract from the dep's type annotations and Field descriptions -- consistent with bae's "class name is instruction, Field description is hint" philosophy. |

### 4. Cross-Mode Input Shortcut

| Aspect | Detail |
|--------|--------|
| **Value proposition** | Requiring mode switch to GRAPH just to answer a pending input is friction. A quick shortcut from any mode (like NL's `@session` prefix) reduces the barrier. |
| **Complexity** | Low |
| **Depends on** | Pending input system, dispatch logic |
| **What it is** | In any mode, typing `!3 yes` (or similar prefix) routes input to graph 3's pending gate. The `!` prefix is parsed before mode dispatch in `_dispatch()`. If no pending input exists for that ID, it is a no-op with an error message. |

---

## Anti-Features

Features to explicitly NOT build for v6.0.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **State snapshots/restore (checkpointing)** | LangGraph's checkpointer is complex infrastructure (database-backed, thread-scoped, replay semantics). Bae graphs are short-lived (seconds to minutes, not hours). Checkpointing adds serialization requirements to every Node and dep result. YAGNI -- no use case demands resuming a graph after a process restart. | Graphs that fail can be re-run. The trace is persisted in the store for post-mortem. |
| **Distributed execution (Celery/Redis)** | Adding distributed task queues changes the architecture fundamentally (serialization, worker processes, result backends). The constraint says "architecture must not preclude it" -- which means keeping graph execution as a clean async coroutine, not building the distribution layer. | Keep `Graph.arun()` as a coroutine. If distribution is needed later, wrap in Celery/Temporal at the call site. |
| **Visual graph DAG rendering in terminal** | Mermaid diagrams are useful in docs but rendering a live graph DAG in a scrollback terminal is awkward. ASCII art graphs are hard to read for complex topologies. | `to_mermaid()` already exists for static visualization. `inspect` shows the trace as a table/list, which is more useful for debugging than a DAG picture. |
| **Auto-retry on validation errors** | Tempting to retry LM fills that fail Pydantic validation. But retry loops hide errors and consume LM tokens. The PROJECT.md explicitly defers this: "DSPy optimization may solve this." | Surface validation errors through the debug view. Let the user decide whether to re-run. Log the failed fill for debugging. |
| **Hot reload of graph definitions** | Watching .py files for changes and reloading graph classes at runtime. Fragile (module reload semantics in Python are unreliable), complex (invalidating running graphs), and unnecessary (the user can `exec()` new code in PY mode). | User redefines graphs in PY mode. The namespace is live -- new definitions take effect immediately for new runs. |
| **Graph-to-graph orchestration (meta-graphs)** | Building a system where one graph can spawn and manage sub-graphs with fan-out/fan-in. The PROJECT.md defers fan-out: "async __call__ with manual gather is the escape hatch." | Users compose graphs via custom `__call__` nodes that invoke `graph.arun()` on sub-graphs. Python is the orchestration layer. |
| **Token-level streaming from graph LM calls** | Streaming individual tokens from LM fills within graph nodes. Requires API client changes (PROJECT.md: "requires API client migration"). Graph nodes produce complete fills, not token streams. | Graph events show node transitions (coarser granularity). Token streaming is a separate milestone that benefits all LM usage, not just graphs. |
| **OTel/OpenTelemetry instrumentation** | Adding spans, traces, and exporters for external observability platforms. Adds dependency weight and configuration complexity. The inline debug view provides equivalent observability for a single-user REPL. | The graph engine emits timing data through channels. If OTel is needed later, wrap channel events as spans at the boundary -- the event data is the same. |
| **Custom graph channel per graph instance** | Creating a separate channel (e.g., `[graph:3]`) for each running graph. Proliferates channels, complicates visibility toggles, and the channel registry was designed for static categories. | All graphs share the `[graph]` channel. Metadata `graph_id` field distinguishes them. The view system can filter by graph_id if needed. |

---

## Feature Dependencies

```
Graph Registry                                    [new module, depends on TaskManager]
    |
    +---> Lifecycle states (RUNNING/WAITING/DONE/FAILED/CANCELLED)
    |
    +---> Graph Engine (arun wrapper)              [depends on Registry for state transitions]
    |         |
    |         +---> Lifecycle event emission        [events -> [graph] channel]
    |         |
    |         +---> Timing instrumentation          [start/end timestamps per node]
    |         |
    |         +---> Input gate integration          [asyncio.Event bridge in dep resolution]
    |
    +---> TaskManager integration                   [Registry entry holds TrackedTask ref]

Pending Input System                               [depends on Graph Registry + Engine]
    |
    +---> InputBridge (asyncio.Event + value slot)  [injected into dep functions by engine]
    |
    +---> input_requested event                     [channel notification with schema]
    |
    +---> GRAPH mode `input` command                [resolves pending gate]
    |
    +---> Toolbar pending badge                     [widget queries registry WAITING count]
    |
    +---> Cross-mode `!` shortcut                   [optional, depends on input system]

GRAPH Mode Commands                                [depends on Graph Registry]
    |
    +---> `list` command                            [queries registry]
    |
    +---> `inspect` command                         [queries registry trace data]
    |
    +---> `cancel` command                          [delegates to registry -> TaskManager]
    |
    +---> `run` command                             [evaluates expr, submits to engine]
    |
    +---> `input` command                           [resolves pending InputBridge]

Graph I/O Through Views                            [depends on Engine events + ViewFormatter]
    |
    +---> UserView graph event rendering            [concise node transition lines]
    |
    +---> DebugView graph event rendering           [full metadata, already works]
    |
    +---> Graph Debug View (timing/deps)            [optional extension of existing views]

Lifecycle Notifications                            [depends on Engine events + [graph] channel]
    (thin layer -- engine emits, channel displays)
```

**Critical ordering insight:** The Graph Registry is the foundation. The Engine wraps arun and needs the registry for state transitions. The pending input system needs the engine to inject the bridge. GRAPH mode commands need the registry to query. Views need the engine's events to render. Build registry first, engine second, input system third, commands and views in parallel after.

---

## MVP Recommendation

Build in this order, each phase usable independently:

### Phase 1: Graph Registry + Engine + TaskManager Integration

**Prioritize:**
1. `GraphRegistry` class: dict of `GraphRun` entries with lifecycle states
2. Graph engine coroutine wrapping `Graph.arun()` with lifecycle events
3. Events emitted to `[graph]` channel with metadata typing
4. `TaskManager.submit()` integration for each graph run
5. Timing data captured per node (start/end timestamps)

**Why first:** This is the skeleton everything else hangs on. Without a registry, there is nothing to list, inspect, or provide input to. Without the engine, there are no lifecycle events for views to render.

### Phase 2: GRAPH Mode Commands

**Prioritize:**
1. Command parsing in `_run_graph()` (split on space, match verb)
2. `list` -- show all graph runs with state, timing, current node
3. `run <expr>` -- evaluate expression, submit graph to engine
4. `cancel <id>` -- revoke via registry -> TaskManager
5. `inspect <id>` -- show trace summary

**Why second:** Commands make the registry usable. The user can start, monitor, and cancel graphs. This is a functional (if spartan) graph runtime.

### Phase 3: Pending Input System

**Prioritize:**
1. `InputBridge` class: asyncio.Event + value slot + schema info
2. Engine integration: detect input bridge in dep resolution, transition to WAITING
3. `input <id> <value>` command in GRAPH mode
4. Toolbar pending badge widget
5. Input schema display in `list` output

**Why third:** Input gates are the hardest feature and the core differentiator. Building them after the registry and commands means the infrastructure for state transitions, event emission, and command dispatch already exists. The input system plugs into proven primitives.

**Defer:**
- Cross-mode `!` shortcut (nice-to-have, add after core input works)
- Graph Debug View with rich timing display (add after basic events work)
- `inspect` with Rich Tree rendering (start with simple text, iterate)

---

## Sources

**Ecosystem Research (MEDIUM confidence -- WebSearch verified against multiple sources):**
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) -- interrupt()/Command(resume=) pattern for human-in-the-loop
- [LangGraph Streaming](https://docs.langchain.com/oss/python/langgraph/streaming) -- Event streaming modes (values, updates, debug, custom, messages)
- [LangSmith Observability](https://docs.langchain.com/oss/python/langgraph/observability) -- Tracing, debugging, latency/cost dashboards
- [Langfuse Agent Graphs](https://langfuse.com/docs/observability/features/agent-graphs) -- Graph structure visualization from observation timings
- [Prefect Interactive Workflows](https://docs.prefect.io/v3/advanced/interactive) -- pause_flow_run(wait_for_input=PydanticModel) pattern
- [Prefect Pause/Resume](https://docs.prefect.io/v3/develop/pause-resume) -- Flow pause with typed input schemas
- [Temporal Signals](https://james-carr.org/posts/2026-02-03-temporal-process-manager/) -- Signal-based wait patterns for durable workflows
- [LlamaIndex Workflows](https://developers.llamaindex.ai/python/llamaagents/workflows/) -- Event-driven step-based execution with num_workers concurrency
- [CrewAI Tasks](https://docs.crewai.com/en/concepts/tasks) -- async_execution, callbacks, context dependencies
- [CrewAI AgentOps](https://docs.crewai.com/how-to/AgentOps-Observability/) -- Step-by-step replay analytics, recursive thought detection

**Python Async Patterns (HIGH confidence -- official docs):**
- [asyncio Tasks](https://docs.python.org/3/library/asyncio-task.html) -- asyncio.Event, TaskGroup, gather patterns
- [prompt_toolkit Reference](https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html) -- refresh_interval, app.invalidate(), bottom_toolbar

**Codebase References (HIGH confidence):**
- `bae/graph.py` -- Graph class, arun() execution loop, routing strategies
- `bae/repl/tasks.py` -- TaskManager, TrackedTask, TaskState
- `bae/repl/channels.py` -- Channel, ChannelRouter, ViewFormatter protocol
- `bae/repl/views.py` -- UserView, DebugView, AISelfView, ViewMode
- `bae/repl/toolbar.py` -- ToolbarConfig, widget factories
- `bae/repl/shell.py` -- CortexShell, _run_graph(), channel_arun()
- `bae/repl/modes.py` -- Mode.GRAPH (currently stub)
- `bae/repl/store.py` -- SessionStore (event persistence)
- `bae/resolver.py` -- resolve_fields(), dep resolution with caching
- `bae/node.py` -- Node base class, successors(), is_terminal()

---

*Research conducted: 2026-02-15*
*Focus: Feature landscape for cortex v6.0 Graph Runtime milestone*
*Replaces: v5.0 Stream Views feature research*
