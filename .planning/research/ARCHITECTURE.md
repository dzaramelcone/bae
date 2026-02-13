# Architecture: Cortex REPL Integration

**Domain:** Augmented async Python REPL for bae agent graph framework
**Researched:** 2026-02-13
**Confidence:** HIGH (direct codebase analysis + verified prompt_toolkit/OTel docs)

## Executive Summary

Cortex is an async REPL that runs on the same asyncio event loop as bae's graph execution. The core architectural insight is that bae already has the async foundation (v3.0): `Graph.arun()` is async, all LM backends are async, dep resolution uses `asyncio.gather()`. Cortex does not wrap or adapt bae -- it shares the event loop and exposes bae objects directly in its namespace.

The integration is additive. No existing bae module needs modification. Cortex is a new `bae/repl/` package that imports from bae and runs alongside it. The only change to existing code is adding `bae/repl/` to `bae/__init__.py` exports and a new CLI entry point.

## Existing Architecture (What Cortex Plugs Into)

### Component Map (Current)

```
bae/
  node.py         -- Node base class (Pydantic BaseModel, async __call__)
  graph.py        -- Graph (discovery, run/arun, validate, to_mermaid)
  markers.py      -- Dep(fn), Recall()
  resolver.py     -- classify_fields, resolve_fields (async, gather-based)
  lm.py           -- LM Protocol, PydanticAIBackend, ClaudeCLIBackend
  dspy_backend.py -- DSPyBackend (async)
  optimized_lm.py -- OptimizedLM
  result.py       -- GraphResult[T]
  exceptions.py   -- BaeError hierarchy
  cli.py          -- Typer app (graph show/export/mermaid + run)
  compiler.py     -- DSPy compilation
  optimizer.py    -- Trace-to-examples, optimize_node
  __init__.py     -- Public API barrel
```

### Async Foundation (v3.0 -- Shipped)

| Component | Async Pattern | Cortex Relevance |
|-----------|---------------|------------------|
| `Graph.arun()` | `async def`, awaits LM + resolver | Can be awaited directly from REPL |
| `Graph.run()` | `asyncio.run(self.arun(...))` | Cannot be called from within running loop |
| `LM.fill()` | `async def` across all backends | Background LM calls while REPL waits |
| `resolve_fields()` | `asyncio.gather()` per topo level | Parallel dep resolution visible in REPL |
| `Node.__call__()` | `async def` | User can `await node(lm)` interactively |
| CLI boundary | `asyncio.run()` in Typer commands | Cortex replaces this with its own loop |

### Key Integration Points

| Existing | Cortex Uses It For | How |
|----------|-------------------|-----|
| `Graph(start=cls)` | Construct graphs interactively | Direct instantiation in namespace |
| `Graph.arun()` | Run graphs from REPL | `await graph.arun(node, lm=lm)` |
| `Node` subclasses | Inspect, instantiate, modify | Available in namespace |
| `LM` backends | Configure and swap LM | Namespace variable `lm = ClaudeCLIBackend()` |
| `GraphResult.trace` | Inspect execution history | Printed via channels |
| `classify_fields()` | Introspect node structure | Tab completion for fields |
| `Graph.to_mermaid()` | Visualize from REPL | `graph.to_mermaid()` call |
| `BaeError` hierarchy | Rich error display | Channel-formatted tracebacks |

## Proposed Architecture (New Components)

### New Module Structure

```
bae/repl/
  __init__.py     -- Public API: launch(), CortexShell
  shell.py        -- CortexShell: prompt_toolkit PromptSession + mode dispatch
  channels.py     -- ChannelBus: labeled async message routing
  namespace.py    -- build_namespace(): reflective bae object exposure
  ai.py           -- AiAgent: NL-to-action bridge (wraps LM backend)
  context.py      -- CortexContext: session state shared across modes
  spans.py        -- OTel span helpers for REPL + graph instrumentation
```

### Modified Existing Modules

| Module | Change | Why |
|--------|--------|-----|
| `bae/__init__.py` | Add repl exports | Package completeness |
| `bae/cli.py` | Add `bae cortex` command | CLI entry point |

No changes to node.py, graph.py, lm.py, resolver.py, or any core module.

### Component Architecture

```
                    CLI Entry (bae/cli.py)
                    ________________________
                   |                        |
                   |  bae cortex            |  <-- new command
                   |  (replaces asyncio.run |
                   |   with REPL event loop)|
                   |________________________|
                          |
                          v
                   CortexShell (bae/repl/shell.py)
                   _________________________________
                  |                                 |
                  |  PromptSession.prompt_async()   |
                  |  Mode dispatch (NL/Py/Bae)      |
                  |  Key bindings for mode switch   |
                  |  Completers per mode             |
                  |_________________________________|
                          |
             _____________|______________
            |             |              |
            v             v              v
     AiAgent         Python exec()   Graph.arun()
     (ai.py)         (namespace.py)  (graph.py)
     __________      ______________  _______________
    |          |    |              ||               |
    | NL->code |    | exec(code,   || await         |
    | NL->graph|    |   namespace) || graph.arun()  |
    | NL->help |    | async eval   ||               |
    |__________|    |______________||_______________|
            |             |              |
            |_____________|______________|
                          |
                          v
                   ChannelBus (bae/repl/channels.py)
                   _________________________________
                  |                                 |
                  |  Labeled message routing         |
                  |  "core.user.py.out:" -> stdout   |
                  |  "eng.Define.ai:" -> styled      |
                  |  Subscribers per channel pattern  |
                  |_________________________________|
                          |
                          v
                   CortexContext (bae/repl/context.py)
                   _________________________________
                  |                                 |
                  |  Session state: namespace,      |
                  |  history, active graph, lm,     |
                  |  trace, OTel tracer             |
                  |_________________________________|
```

## Component Detail

### 1. CortexShell (shell.py)

The shell is the REPL loop owner. It creates the `PromptSession`, dispatches input to the correct mode handler, and manages the prompt_toolkit event loop integration.

**Event Loop Architecture:**

prompt_toolkit 3.0 runs natively on asyncio. `PromptSession.prompt_async()` yields control to the event loop while waiting for user input. This means background tasks (graph execution, LM calls, AI agent processing) run concurrently with the prompt.

```python
class CortexShell:
    """Async REPL with mode dispatch."""

    def __init__(self, ctx: CortexContext):
        self.ctx = ctx
        self.session = PromptSession(
            completer=self._mode_completer(),
            key_bindings=self._mode_bindings(),
        )

    async def run(self) -> None:
        """Main REPL loop -- runs until EOF."""
        with patch_stdout():
            while True:
                text = await self.session.prompt_async(
                    self._build_prompt(),
                )
                await self._dispatch(text)
```

**Mode Detection:**

Three modes share one prompt. Mode is detected by input prefix, not modal switching. This avoids the complexity of vi-style modal prompts and keeps the UX discoverable.

| Prefix | Mode | Handler |
|--------|------|---------|
| (none / bare text) | NL chat | `AiAgent.handle(text)` |
| `>` or starts with Python syntax | Py exec | `exec(compile(text), namespace)` |
| `!` or `bae ...` | Graph bae-run | `Graph.arun(...)` |

Detection heuristic: if the line parses as valid Python (via `ast.parse`), treat as Py. If it starts with `!` or `bae `, treat as graph command. Otherwise, NL chat. The `>` prefix is an explicit Py escape when NL/Py is ambiguous.

**Why prefix-based, not modal:**
- No hidden state -- user always knows what mode they're in
- Tab completion adapts to detected mode
- History is shared but mode-tagged

**Completers:**

prompt_toolkit's `DynamicCompleter` wraps a callable that returns different completers based on context. The completer switches based on the first characters typed:

- NL mode: no completion (free text)
- Py mode: namespace-aware Python completer (variables, attributes, methods)
- Bae mode: `NestedCompleter` for graph commands (`bae run`, `bae inspect`, etc.)

### 2. ChannelBus (channels.py)

Channels are the I/O multiplexing layer. All output from all modes flows through labeled channels. This replaces raw `print()` with structured, subscribable streams.

**Design:**

A channel is a labeled `asyncio.Queue`. The bus routes messages from producers (graph execution, AI agent, Python exec) to consumers (terminal display, log file, OTel events).

```python
@dataclass
class Message:
    """Labeled message on a channel."""
    channel: str       # "eng.Define.ai:", "core.user.py.out:", etc.
    content: str       # The actual text
    timestamp: float   # monotonic time
    span_id: str = ""  # OTel span correlation

class ChannelBus:
    """Pub/sub message bus over asyncio.Queue."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def emit(self, channel: str, content: str) -> None:
        """Publish a message to a channel."""
        msg = Message(channel=channel, content=content, timestamp=time.monotonic())
        for queue in self._subscribers.get(channel, []):
            await queue.put(msg)
        # Wildcard subscribers
        for pattern, queues in self._subscribers.items():
            if pattern.endswith("*") and channel.startswith(pattern[:-1]):
                for queue in queues:
                    await queue.put(msg)

    def subscribe(self, pattern: str) -> asyncio.Queue:
        """Subscribe to channels matching pattern. Returns a Queue to read from."""
        queue = asyncio.Queue()
        self._subscribers.setdefault(pattern, []).append(queue)
        return queue
```

**Channel Naming Convention:**

```
{layer}.{source}.{kind}:
```

| Channel | Producer | Content |
|---------|----------|---------|
| `core.user.input:` | Shell | Raw user input |
| `core.user.py.out:` | Python exec | stdout from exec'd code |
| `core.user.py.err:` | Python exec | stderr from exec'd code |
| `eng.{NodeName}.fill:` | LM.fill() | Structured output from fill |
| `eng.{NodeName}.choose:` | LM.choose_type() | Type choice |
| `eng.graph.trace:` | Graph.arun() | Node transitions |
| `eng.graph.result:` | Graph.arun() | Final GraphResult |
| `ai.agent.thought:` | AiAgent | NL reasoning |
| `ai.agent.action:` | AiAgent | Code/command generated |
| `sys.otel.span:` | OTel | Span start/end events |

**Why channels instead of direct print():**
1. Background graph execution can emit while prompt is active (`patch_stdout` handles rendering)
2. Subscribers can filter: show only errors, only AI output, only graph trace
3. OTel can subscribe to all channels for event recording
4. Future: persist channel history for session replay

**Integration with prompt_toolkit output:**

The terminal display subscriber uses `print_formatted_text()` from prompt_toolkit with `patch_stdout()` context. This ensures channel output renders above the active prompt without corrupting the input line.

```python
async def terminal_renderer(bus: ChannelBus) -> None:
    """Render channel messages to terminal."""
    queue = bus.subscribe("*")
    while True:
        msg = await queue.get()
        styled = _style_for_channel(msg.channel, msg.content)
        print_formatted_text(styled)
```

### 3. Namespace (namespace.py)

The namespace is a dict that serves as both `globals` and `locals` for Python exec within the REPL. It exposes bae objects for interactive use.

**Design Principle:** The namespace is not a wrapper or proxy. It is a plain dict seeded with real bae objects. Users interact with actual Node classes, Graph instances, and LM backends -- not REPL-specific abstractions.

```python
def build_namespace(ctx: CortexContext) -> dict:
    """Build the REPL namespace with bae objects."""
    ns = {}

    # Core bae types
    ns["Node"] = Node
    ns["Graph"] = Graph
    ns["GraphResult"] = GraphResult
    ns["Dep"] = Dep
    ns["Recall"] = Recall

    # LM backends
    ns["PydanticAIBackend"] = PydanticAIBackend
    ns["ClaudeCLIBackend"] = ClaudeCLIBackend
    ns["DSPyBackend"] = DSPyBackend

    # Session state (mutable references)
    ns["lm"] = ctx.lm          # Current LM backend
    ns["graph"] = ctx.graph    # Current graph (if loaded)
    ns["trace"] = ctx.trace    # Last execution trace
    ns["result"] = ctx.result  # Last GraphResult
    ns["ctx"] = ctx            # Full context for power users

    # Convenience functions
    ns["run"] = ctx.run_graph       # async: await run(node)
    ns["inspect"] = ctx.inspect     # Show node/graph info
    ns["channels"] = ctx.bus        # Channel bus access

    # Standard library (convenience)
    ns["asyncio"] = asyncio
    ns["json"] = json

    return ns
```

**Reflective Features:**

The namespace enables reflection because bae objects are already introspectable:

| Want to... | In the REPL |
|------------|-------------|
| See a graph's nodes | `graph.nodes` |
| See a node's fields | `MyNode.model_fields` |
| See a node's successors | `MyNode.successors()` |
| Check if terminal | `MyNode.is_terminal()` |
| See field annotations | `classify_fields(MyNode)` |
| Visualize the graph | `graph.to_mermaid()` |
| Run a graph | `result = await run(MyNode(field="value"))` |
| Inspect last trace | `trace[-1].model_dump()` |
| Change LM | `ctx.lm = ClaudeCLIBackend(model="...")` |

No special "reflective namespace" machinery is needed. Pydantic models are already introspectable via `model_fields`, `model_json_schema()`, etc. Node topology is already introspectable via `successors()`, `is_terminal()`. Graph topology is already introspectable via `nodes`, `edges`, `to_mermaid()`.

**Auto-import of user graphs:**

When cortex launches with a module argument (`bae cortex examples.ootd`), all public names from that module are injected into the namespace. This means all Node subclasses, the graph instance, dep functions, and service models are immediately available.

```python
def inject_module(ns: dict, module_path: str) -> None:
    """Import a module and inject its public names into namespace."""
    module = importlib.import_module(module_path)
    for name in dir(module):
        if not name.startswith("_"):
            ns[name] = getattr(module, name)
```

### 4. AiAgent (ai.py)

The AI agent translates natural language into actions. It is a bae LM call -- not a separate system.

**Architecture:** AiAgent wraps the current LM backend. NL input becomes a prompt. The LM's structured output produces either Python code to execute or a graph command to run. The agent is an object in the namespace, not a hidden system.

```python
class AiAgent:
    """NL-to-action bridge using the session's LM."""

    def __init__(self, ctx: CortexContext):
        self.ctx = ctx

    async def handle(self, text: str) -> None:
        """Process NL input and emit results to channels."""
        # Build prompt with namespace context
        prompt = self._build_prompt(text, self.ctx.namespace)
        # Use session's LM for the call
        response = await self._call_lm(prompt)
        # Emit to channel
        await self.ctx.bus.emit("ai.agent.action:", response)
```

The AI agent is intentionally thin. It does not have its own graph or complex reasoning chain. It is a single LM call with context about the namespace (available variables, loaded graph, last trace). Complexity can grow later, but the v4.0 architecture should not over-engineer this.

**Why not a separate LM instance:**
- The whole point of cortex is that the AI is a Python object you can inspect and configure
- `ctx.lm` is the single source of truth for which model to use
- If users want a different model for the agent, they set `ctx.agent_lm`

### 5. CortexContext (context.py)

Session state container shared across all components. Not a god object -- a typed dataclass of references.

```python
@dataclass
class CortexContext:
    """Shared session state for cortex REPL."""
    bus: ChannelBus
    namespace: dict
    lm: LM
    graph: Graph | None = None
    trace: list[Node] = field(default_factory=list)
    result: GraphResult | None = None
    tracer: Tracer | None = None  # OTel tracer

    async def run_graph(self, start_node: Node, **kwargs) -> GraphResult:
        """Convenience: run the current graph with the current LM."""
        if self.graph is None:
            raise RuntimeError("No graph loaded. Set ctx.graph first.")
        result = await self.graph.arun(start_node, lm=self.lm, **kwargs)
        self.trace = result.trace
        self.result = result
        await self.bus.emit("eng.graph.result:", str(result))
        return result
```

### 6. OTel Spans (spans.py)

OTel instrumentation for both REPL interactions and graph execution. Uses `opentelemetry-api` and `opentelemetry-sdk`.

**Span Hierarchy:**

```
cortex.session                          # Root span: entire REPL session
  |
  +-- cortex.input                      # Each user input
  |     |
  |     +-- cortex.mode.py              # Python exec
  |     +-- cortex.mode.nl              # NL chat
  |     +-- cortex.mode.bae             # Graph command
  |           |
  |           +-- bae.graph.run         # Graph.arun() execution
  |                 |
  |                 +-- bae.node.{Name} # Each node step
  |                 |     |
  |                 |     +-- bae.resolve.{Name}  # Dep resolution
  |                 |     +-- bae.lm.fill         # LM fill call
  |                 |     +-- bae.lm.choose_type  # LM routing
  |                 |
  |                 +-- bae.node.{Name}
  |                       ...
  |
  +-- cortex.input                      # Next user input
        ...
```

**Implementation Approach:**

OTel spans use Python's `contextvars` for propagation, which works correctly with asyncio (each task inherits the context of its parent). This means spans created in `Graph.arun()` automatically nest under the REPL input span without explicit context passing.

```python
from opentelemetry import trace

tracer = trace.get_tracer("bae.cortex")

async def traced_dispatch(shell, text: str) -> None:
    """Dispatch user input with OTel span."""
    with tracer.start_as_current_span("cortex.input") as span:
        span.set_attribute("input.text", text[:200])
        span.set_attribute("input.mode", detect_mode(text))
        await shell._dispatch(text)
```

**Graph execution instrumentation:**

Graph.arun() instrumentation is done via a wrapping pattern, not by modifying graph.py. A `TracedGraph` or a context manager wraps `arun()`:

```python
async def traced_arun(graph, start_node, lm, **kwargs):
    """Wrap Graph.arun() with OTel spans per node step."""
    with tracer.start_as_current_span("bae.graph.run") as span:
        span.set_attribute("graph.start", type(start_node).__name__)
        # Delegate to real arun
        result = await graph.arun(start_node, lm=lm, **kwargs)
        span.set_attribute("graph.steps", len(result.trace))
        return result
```

For per-node spans, a `TracedLM` wrapper (similar to the existing `TracingClaudeCLI` pattern in `run_ootd_traced.py`) wraps the LM and creates child spans for each `fill()` and `choose_type()` call.

**Why wrapper, not modification:**
- No changes to graph.py, lm.py, or node.py
- OTel is opt-in: if `opentelemetry-sdk` is not installed, spans are no-ops
- Follows the existing `TracingClaudeCLI` pattern already in the codebase
- Keeps core execution path free of instrumentation overhead

**Python 3.14 Compatibility:**

opentelemetry-python has merged Python 3.14 support (PR #4798). prompt_toolkit 3.0.52 supports Python 3.6+ and works on 3.14. Both are compatible with bae's `requires-python = ">=3.14"`.

## Data Flow

### REPL Input to Graph Execution

```
User types: "run the ootd graph for 'heading to brunch'"
     |
     v
CortexShell.prompt_async() returns text
     |
     v
Mode detection: starts with "run" -> Bae mode
     |
     v
Parse: graph=ootd, input={user_message: "heading to brunch"}
     |
     v
ChannelBus.emit("core.user.input:", text)
     |
     v
OTel: start span "cortex.input" (mode=bae)
     |
     v
ctx.run_graph(IsTheUserGettingDressed(user_message="heading to brunch"))
     |
     v
Graph.arun() -- on the SAME event loop
     |
     +-- resolve_fields() -> asyncio.gather(get_location, get_weather, get_schedule)
     |     |
     |     v  (each dep emits to "eng.{dep}.resolve:" channel)
     |
     +-- lm.choose_type([AnticipateUsersDay, No], context)
     |     |
     |     v  (emits to "eng.IsTheUserGettingDressed.choose:" channel)
     |
     +-- lm.fill(AnticipateUsersDay, resolved, instruction, source)
     |     |
     |     v  (emits to "eng.AnticipateUsersDay.fill:" channel)
     |
     +-- ... (continues through graph)
     |
     v
GraphResult returned
     |
     v
ctx.trace = result.trace
ctx.result = result
     |
     v
ChannelBus.emit("eng.graph.result:", formatted_result)
     |
     v
Terminal renderer: styled output above prompt
     |
     v
OTel: end span "cortex.input"
     |
     v
Prompt reappears, user can now:
  - `trace[-1].model_dump()` (inspect result)
  - `graph.to_mermaid()` (visualize)
  - NL: "what was the weather?" (AI answers from context)
```

### Event Loop Sharing (Critical Detail)

prompt_toolkit's `prompt_async()` and bae's `Graph.arun()` share the same asyncio event loop. This is NOT two event loops or thread bridging. The sequence is:

1. `asyncio.run(shell.run())` starts the loop
2. `await session.prompt_async()` suspends the shell coroutine, loop handles other tasks
3. User types input, shell coroutine resumes
4. `await ctx.run_graph(node)` suspends shell, `Graph.arun()` runs on the SAME loop
5. During `arun()`, `asyncio.gather()` fires parallel deps concurrently
6. `arun()` completes, shell resumes, prompt reappears

No `asyncio.to_thread()`, no nested `asyncio.run()`, no thread pools. Pure single-loop cooperative async.

**The one exception:** `Graph.run()` (sync wrapper) calls `asyncio.run()` which would fail inside an already-running loop. Cortex must always use `Graph.arun()`. This is already the correct API -- `run()` is a convenience for sync callers, `arun()` is the real implementation.

### Background Tasks

Some operations can run in the background while the prompt is active:

```python
# User kicks off a long graph run
task = asyncio.create_task(ctx.run_graph(start_node))
# Prompt reappears immediately
# Channel emissions render above prompt via patch_stdout
# User can inspect partial results or do other work
# When task completes, result is in ctx.result
```

This is enabled by `patch_stdout()` which ensures background output renders cleanly above the active prompt.

## Patterns to Follow

### Pattern 1: Wrapper Instrumentation (Not Monkey-Patching)

**What:** Instrument existing objects by wrapping, not modifying.
**When:** Adding OTel spans to Graph.arun(), LM.fill(), etc.
**Example:** `TracedLM` wraps any `LM` implementation and adds spans around each method call. Same pattern as `TracingClaudeCLI` already in the codebase.

```python
class TracedLM:
    """LM wrapper that adds OTel spans."""

    def __init__(self, inner: LM, tracer: Tracer):
        self._inner = inner
        self._tracer = tracer

    async def fill(self, target, resolved, instruction, source=None):
        with self._tracer.start_as_current_span("bae.lm.fill") as span:
            span.set_attribute("target", target.__name__)
            return await self._inner.fill(target, resolved, instruction, source)
```

### Pattern 2: Channel-Driven Output (Not Direct Print)

**What:** All REPL output goes through the ChannelBus, never raw `print()`.
**When:** Any component that produces user-visible output.
**Why:** Enables filtering, styling, logging, OTel event recording, and clean interaction with `patch_stdout`.

### Pattern 3: Namespace is the API

**What:** The REPL's interactive API is whatever is in the namespace dict.
**When:** Adding new functionality to the REPL.
**Why:** No special command system needed. Adding a function to the namespace makes it callable. Adding a class makes it instantiable. Standard Python semantics apply.

### Pattern 4: Context Dataclass, Not Singleton

**What:** `CortexContext` is a dataclass passed by reference, not a module-level singleton.
**When:** Accessing shared state across shell, agent, namespace, channels.
**Why:** Testable (inject mock context), composable (multiple sessions), explicit dependencies.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Nested Event Loops

**What:** Using `asyncio.run()` inside an already-running loop, or nesting `loop.run_until_complete()`.
**Why bad:** RuntimeError. asyncio does not support nested loops.
**Instead:** Always `await` coroutines. Use `asyncio.create_task()` for fire-and-forget. Never call `Graph.run()` from cortex -- always `Graph.arun()`.

### Anti-Pattern 2: Thread-Based REPL

**What:** Running prompt_toolkit in a separate thread with a second event loop.
**Why bad:** Thread safety issues with shared namespace. Context propagation (OTel) breaks across threads. Complexity explosion.
**Instead:** Single asyncio loop. prompt_toolkit 3.0 supports this natively via `prompt_async()`.

### Anti-Pattern 3: Custom Command Parser

**What:** Building a grammar/parser for REPL commands (click-style, argparse, etc.)
**Why bad:** Reinvents shell badly. Users already know Python syntax.
**Instead:** Bae commands are thin wrappers that call Python functions. `!run ootd "text"` is syntactic sugar for `await run(StartNode(msg="text"))`. Keep the command surface minimal.

### Anti-Pattern 4: Modal State Machine

**What:** Explicit mode state that users must toggle (like vi insert/normal modes).
**Why bad:** Hidden state. Users forget which mode they're in. Mode-switch bugs.
**Instead:** Prefix-based detection. Every input is unambiguously one mode. `>` for explicit Python. `!` for explicit bae command. Bare text defaults to NL or auto-detects Python.

### Anti-Pattern 5: Modifying graph.py for Instrumentation

**What:** Adding OTel imports and span creation directly in `Graph.arun()`.
**Why bad:** Couples core execution to optional dependency. Adds overhead to non-REPL usage.
**Instead:** Wrapper pattern (`TracedLM`, `traced_arun`). Core stays clean. Instrumentation is opt-in.

### Anti-Pattern 6: ChannelBus as Mandatory Middleware

**What:** Requiring all bae operations to go through channels, even outside the REPL.
**Why bad:** Couples framework to REPL infrastructure. Non-REPL usage should not need channels.
**Instead:** Channels are a REPL-only concern. `Graph.arun()` returns `GraphResult` as always. The REPL wraps calls and emits to channels. Core bae knows nothing about channels.

## Scalability Considerations

| Concern | REPL (1 user) | Future: Multi-session | Future: Remote |
|---------|---------------|----------------------|----------------|
| Event loop | Single asyncio loop | One loop per session | Loop per process |
| Namespace | Single dict | Isolated dicts | Serialized state |
| Channels | In-process Queue | Per-session bus | WebSocket bridge |
| OTel | Local exporter | Shared collector | OTLP exporter |
| LM concurrency | Sequential prompts | Independent sessions | Rate limiting |

For v4.0, only the "REPL (1 user)" column matters. The architecture supports the other columns but should not build for them yet (YAGNI).

## Integration Summary: New vs Modified

### New Components

| Component | File | LOC Estimate | Depends On |
|-----------|------|-------------|------------|
| CortexShell | `bae/repl/shell.py` | ~150 | prompt_toolkit, CortexContext |
| ChannelBus | `bae/repl/channels.py` | ~80 | asyncio.Queue |
| Namespace builder | `bae/repl/namespace.py` | ~60 | bae.* imports |
| AiAgent | `bae/repl/ai.py` | ~100 | bae.lm.LM, CortexContext |
| CortexContext | `bae/repl/context.py` | ~50 | bae.graph, bae.lm, bae.node |
| OTel spans | `bae/repl/spans.py` | ~80 | opentelemetry-api (optional) |
| Package init | `bae/repl/__init__.py` | ~15 | All above |

### Modified Components

| Component | File | Change | LOC Delta |
|-----------|------|--------|-----------|
| CLI | `bae/cli.py` | Add `bae cortex` command | ~20 |
| Package init | `bae/__init__.py` | Export repl if available | ~3 |

### Zero-Change Components

Every existing bae module: node.py, graph.py, lm.py, resolver.py, markers.py, result.py, exceptions.py, compiler.py, optimizer.py, dspy_backend.py, optimized_lm.py.

## Suggested Build Order

Based on dependency analysis:

### Phase 1: Shell Foundation + Context

Build CortexContext and CortexShell with basic prompt_async loop. Single mode (Python exec). No channels, no AI, no OTel.

**Why first:** Everything depends on the shell loop running. This validates that prompt_toolkit + asyncio + bae's async foundation work together on one event loop.

**Deliverables:**
- `bae/repl/context.py` -- CortexContext dataclass
- `bae/repl/namespace.py` -- build_namespace() with bae objects
- `bae/repl/shell.py` -- CortexShell with prompt_async loop, Py exec only
- `bae/repl/__init__.py` -- launch() entry point
- `bae/cli.py` -- `bae cortex` command

**Critical validation:** `await graph.arun(node, lm=lm)` works from the REPL prompt. This proves event loop sharing.

### Phase 2: Channel Bus + Multi-Mode

Add ChannelBus for labeled I/O. Add mode detection (NL/Py/Bae). Wire output through channels.

**Why second:** Channels are the I/O backbone. Mode detection needs channels for output routing. AI agent (Phase 3) needs channels to emit its output.

**Deliverables:**
- `bae/repl/channels.py` -- ChannelBus with emit/subscribe
- Shell update: mode detection, channel-routed output
- Terminal renderer task (background, reads from bus)

### Phase 3: AI Agent

Add AiAgent for NL mode. Wraps the session LM. Emits to channels.

**Why third:** Requires working shell (Phase 1) and channels (Phase 2). The agent is a consumer of both.

**Deliverables:**
- `bae/repl/ai.py` -- AiAgent with handle()
- Shell update: NL mode dispatches to agent

### Phase 4: OTel Instrumentation

Add span helpers. TracedLM wrapper. Session-level spans.

**Why last:** Instrumentation is observability over working code. Requires all other components to be functional. OTel is optional -- cortex works without it.

**Deliverables:**
- `bae/repl/spans.py` -- tracer setup, TracedLM, traced_arun
- Shell update: wrap dispatch in spans
- Optional dependency: `opentelemetry-api`, `opentelemetry-sdk`

## Open Design Questions

### 1. Python exec: `exec()` vs embedded ptpython

**Option A:** Raw `exec(compile(text, ...), namespace)` with custom async eval for `await` expressions.
**Option B:** Embed ptpython via `embed(globals=namespace, return_asyncio_coroutine=True)`.

**Recommendation:** Option A for v4.0. ptpython adds a heavy dependency (its own REPL loop, configuration system, toolbar). Raw exec with `ast.parse` for async detection is simpler and gives full control over how output routes through channels. ptpython can be explored later if users want richer Python editing.

**Async exec pattern:**
```python
async def async_exec(code: str, ns: dict) -> object:
    """Execute code that may contain await expressions."""
    tree = ast.parse(code, mode="exec")
    # If the last statement is an expression, capture its value
    # If any node contains Await, wrap in async def and await it
    ...
```

### 2. Channel persistence: in-memory only or disk?

**Recommendation:** In-memory only for v4.0. Channel history lives in the bus's subscriber queues. Session replay and persistence are future features.

### 3. OTel exporter: console or OTLP?

**Recommendation:** Console exporter for v4.0 (spans print to a `sys.otel.span:` channel). OTLP exporter as a configuration option for users with Jaeger/Grafana Tempo.

## Sources

- [prompt_toolkit asyncio docs](https://python-prompt-toolkit.readthedocs.io/en/master/pages/advanced_topics/asyncio.html) -- HIGH confidence
- [prompt_toolkit asking for input](https://python-prompt-toolkit.readthedocs.io/en/master/pages/asking_for_input.html) -- HIGH confidence
- [prompt_toolkit asyncio-prompt.py example](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/asyncio-prompt.py) -- HIGH confidence
- [ptpython asyncio embed example](https://github.com/prompt-toolkit/ptpython/blob/main/examples/asyncio-python-embed.py) -- HIGH confidence
- [ptpython embedding docs (DeepWiki)](https://deepwiki.com/prompt-toolkit/ptpython/5-embedding-ptpython) -- MEDIUM confidence
- [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/) -- HIGH confidence
- [OTel asyncio context example](https://github.com/open-telemetry/opentelemetry-python/blob/main/docs/examples/basic_context/async_context.py) -- HIGH confidence
- [OTel asyncio instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asyncio/asyncio.html) -- HIGH confidence
- [OTel Python 3.14 support (GitHub issue #4789)](https://github.com/open-telemetry/opentelemetry-python/issues/4789) -- HIGH confidence
- [prompt_toolkit 3.0.52 on PyPI](https://pypi.org/project/prompt-toolkit/) -- HIGH confidence
- Direct codebase analysis of all bae/ source files -- HIGH confidence
- bae v3.0 roadmap and requirements (shipped async foundation) -- HIGH confidence

---
*Architecture research: 2026-02-13 -- cortex REPL integration*
