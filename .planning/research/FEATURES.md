# Feature Landscape: Cortex REPL for Bae v4.0

**Domain:** Augmented async Python REPL with AI agent integration, channel-based I/O, reflective namespace
**Researched:** 2026-02-13
**Confidence:** HIGH for REPL mechanics and namespace introspection (well-established Python patterns); MEDIUM for channel I/O multiplexing (novel design, Docker analogy verified); MEDIUM for AI agent object (emerging patterns, no standard yet)

## Ecosystem Survey: How Augmented REPLs Work

### Custom Python REPLs on prompt_toolkit

prompt_toolkit is the standard foundation for building custom Python REPLs. ptpython is the canonical example -- a full Python REPL built entirely on prompt_toolkit with syntax highlighting, multiline editing, and popup tab completion. Building a basic Python REPL on prompt_toolkit takes under an hour; most features come free from the framework.

**Async REPL pattern (verified via ptpython source):**
```python
async def interactive_shell():
    await embed(
        globals=globals(),
        return_asyncio_coroutine=True,
        patch_stdout=True,
    )
```

Key capabilities:
- `return_asyncio_coroutine=True` -- REPL runs as a coroutine, enabling top-level `await`
- `patch_stdout=True` -- background coroutines can safely print above the prompt
- `globals=globals()` -- custom namespace injection for the REPL session
- Dynamic prompt text via callables (re-evaluated each render cycle)
- Bottom toolbar for mode indicators, status, live info
- Custom keybindings via `KeyBindings` registry
- Full-screen layouts via `HSplit`/`VSplit`/`Window`/`BufferControl`

**What prompt_toolkit does NOT do:** Mode switching between NL/Py/Graph, channel multiplexing, AI integration. These are cortex's differentiators.

**Confidence:** HIGH (ptpython source, official docs at python-prompt-toolkit.readthedocs.io)

### Mode Switching in Existing Shells

**xonsh** is the closest prior art for multi-mode shells. It blends Python mode and subprocess mode using implicit heuristic detection -- if input looks like Python, it runs as Python; otherwise, it dispatches as a shell command. This works but creates ambiguity at mode boundaries.

**IPython** uses magic commands (% prefix for line magics, %% for cell magics) to escape from Python into special behaviors. The prefix-character approach is proven and unambiguous.

**Aider** (AI pair programming CLI) uses explicit mode switching -- `/code`, `/architect`, `/ask`, `/help` slash commands change the behavior of subsequent input. Claude Code operates as a REPL-style agent with a bash tool and file editing tool.

**Open Interpreter** uses natural language as the primary input mode, with the AI generating and executing code. No explicit mode switching -- the AI figures out what to do.

**Key insight for cortex:** Explicit mode switching with prefix characters is cleaner than heuristic detection. xonsh's implicit detection creates confusion at boundaries. IPython's `%` prefix and Aider's `/` slash commands are battle-tested patterns. For cortex, a single-character prefix per mode (like `>` for NL, no prefix for Py, `!` for graph) gives unambiguous dispatch without the complexity of auto-detection.

**Confidence:** HIGH for xonsh/IPython patterns (official docs); MEDIUM for Aider/Open Interpreter (WebSearch + GitHub verified)

### Channel-Based I/O Multiplexing

No existing Python REPL implements channel-based I/O. The design is novel, drawing from:

**Docker Compose** uses labeled, color-coded output streams for multi-container logs. Each container's output is prefixed with its name, and colors distinguish containers visually. The Docker Engine multiplexes stdout and stderr using a binary protocol (stdcopy) that tags each frame with its stream origin.

**tmux / pymux** (prompt_toolkit-based terminal multiplexer) multiplexes terminal sessions with labeled panes. pymux demonstrates that prompt_toolkit's layout system can handle multiple simultaneous output areas.

**Go channels / Trio memory channels** provide the concurrency primitive. Python's `asyncio.Queue` is the direct analog -- single-consumer by default. For fan-out (one message to multiple consumers), you need a subscriber list with per-subscriber queues.

**Key insight for cortex:** The channel abstraction is a labeled `asyncio.Queue` with a display prefix. Each channel is a named stream (`[ai]`, `[py]`, `[graph]`, `[otel]`). The REPL renders all channels in the output area with their label prefix. Muting a channel removes it from render without stopping the producer. This is simpler than a full pub/sub system -- it's just labeled output lines with filter predicates.

**Confidence:** MEDIUM (novel design; Docker and asyncio.Queue patterns are well-understood, but the combination for REPL output is untested)

### Reflective Python Namespaces

Python's introspection is comprehensive and well-documented:

- `dir(obj)` -- list attributes and methods
- `vars(obj)` / `obj.__dict__` -- namespace as dict
- `type(obj)`, `isinstance()`, `issubclass()` -- type checking
- `inspect.getmembers(obj, predicate)` -- filtered member listing
- `inspect.getsource(obj)` -- source code retrieval
- `inspect.signature(obj)` -- callable signatures
- `__getattr__` / `__dir__` -- proxy objects with custom introspection and tab completion

For REPL integration, the key pattern is `__dir__` customization. Tab completion in prompt_toolkit and ptpython calls `dir()` on namespace objects. If the AI agent or namespace proxy implements `__dir__`, it appears in tab completion naturally.

**Lazy loading via `__getattr__`:** PEP 562 (Python 3.7+) established the pattern of module-level `__getattr__` for lazy imports. The same technique works for namespace objects -- attributes resolve on first access, not at import time.

**Rich object display:** IPython defines `_repr_html_`, `_repr_pretty_`, `_repr_markdown_` protocols for custom display. The Rich library provides `__rich_repr__` and `__rich_console__` for terminal formatting. Since cortex uses prompt_toolkit (not IPython), the display protocol will be `__cortex_repr__` or similar -- a method that returns prompt_toolkit `FormattedText`.

**Confidence:** HIGH (Python stdlib docs, inspect module docs, PEP 562)

### AI Agent as REPL Object

No standard pattern exists for "AI as a first-class object in a Python namespace." The closest precedents:

**LangChain's agent.invoke()** -- agent is a callable Python object, but not integrated into a REPL namespace.

**Open Interpreter's `interpreter` object** -- exposed as a Python package with a chat interface, but lives in its own process, not in a shared namespace.

**Claude Code's architecture** -- a REPL-style interface where the AI has two tools (bash, file edit). The AI is the loop controller, not an object in a namespace.

**Key insight for cortex:** The AI agent is a Python object that lives in the REPL namespace alongside user variables, graph nodes, and resolved deps. It is callable (`ai("explain this graph")`) and has methods (`ai.fill(MyNode)`, `ai.choose(A | B)`) that map directly to bae's LM protocol. It participates in tab completion via `__dir__`. Its output goes to the `[ai]` channel. This is genuinely novel -- no existing tool exposes AI as a composable Python object in a shared, interactive namespace.

**Confidence:** MEDIUM (no precedent; design is sound but untested)

### OpenTelemetry for Interactive Sessions

OTel semantic conventions for GenAI are in Development status (not stable). Key span types:

- `invoke_agent` -- root span for agent invocation
- `gen_ai.operation.name` -- operation type attribute
- `gen_ai.agent.name` -- agent identifier
- `gen_ai.usage.input_tokens` / `output_tokens` -- token tracking
- `gen_ai.request.model` -- model identifier

For REPL context, the span hierarchy would be:
```
cortex.session (root)
  cortex.command (per user input)
    gen_ai.invoke_agent (if AI involved)
      gen_ai.fill / gen_ai.choose_type (LM calls)
    bae.graph.run (if graph execution)
      bae.node.resolve (per node)
```

Python's OTel SDK uses `contextvars` for span propagation, which works natively with asyncio. No special handling needed for async REPL -- spans propagate through `await` chains automatically.

**Confidence:** MEDIUM for GenAI semantic conventions (Development status, may change); HIGH for core OTel span mechanics (stable, well-documented)

---

## Table Stakes

Features that define what "an augmented REPL" must do. Missing any of these and the product feels broken.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|--------------|------------|------------|-------|
| **Async Python execution with top-level await** | Every modern Python REPL (ptpython, IPython, Python 3.13+ REPL) supports this. Users type `await graph.arun(node)` and it works. Without this, the REPL can't interact with bae's async API. | Low | prompt_toolkit `embed()` with `return_asyncio_coroutine=True` | ptpython solves this already. Cortex inherits it. |
| **Syntax highlighting and multiline editing** | ptpython, IPython, and Python 3.13+ REPL all have this. A REPL without syntax highlighting feels broken in 2026. | Low | prompt_toolkit (free) | Comes free from prompt_toolkit/Pygments. Zero effort. |
| **Tab completion on namespace objects** | Every REPL does this. Users expect `ai.<TAB>` to show methods, `graph.<TAB>` to show attributes. | Low | prompt_toolkit completer + `__dir__` on objects | Standard prompt_toolkit pattern. Needs `__dir__` on custom objects. |
| **Shared mutable namespace** | The REPL namespace must be a single Python dict that all modes (NL, Py, Graph) read and write. Variables set in Py mode are visible in NL mode. Graph results land in the namespace. | Low | `globals()` dict passed to REPL | ptpython async embed example demonstrates this exactly. |
| **History and persistence** | Command history across sessions. Up-arrow recalls previous inputs. | Low | prompt_toolkit `FileHistory` | One line of config. |
| **Error display with tracebacks** | When Python code fails, show a full traceback. When a graph fails, show the trace + error. Not just "error occurred." | Low | Python stdlib traceback + bae exception types | Bae already has typed exceptions (DepError, FillError, RecallError) with `.trace` attributes. |
| **Graceful Ctrl-C / Ctrl-D** | Ctrl-C cancels current operation (not the whole REPL). Ctrl-D exits. Running LM calls must be cancellable. | Low-Med | asyncio task cancellation | asyncio.Task.cancel() propagates CancelledError. Needs try/except around eval loop. |
| **Bae objects pre-loaded in namespace** | `Node`, `Graph`, `Dep`, `Recall`, `LM` etc. available without import. The REPL should feel like "bae is already imported." | Low | Populate namespace dict at startup | `namespace.update(bae.__dict__)` or selective import. |
| **Mode indicator in prompt** | User must always know which mode they're in. The prompt prefix changes: `py>`, `nl>`, `bae>` or similar. | Low | prompt_toolkit dynamic prompt callable | Callable that returns current mode prefix. One function. |

## Differentiators

Features that make cortex special. No existing tool does these.

| Feature | Value Proposition | Complexity | Depends On | Notes |
|---------|-------------------|------------|------------|-------|
| **Three-mode input: NL / Py / Graph** | Single REPL handles natural language ("what does this graph do?"), Python execution (`result = await graph.arun(node)`), and graph operations (`bae run ootd`). No context switching between tools. Users stay in one terminal. | Med | Mode dispatcher, prefix detection, prompt_toolkit input processing | **Core differentiator.** Mode detection via prefix character (explicit, not heuristic). Default mode is Py. NL mode sends input to AI. Graph mode wraps `bae` CLI commands. |
| **Channel-based I/O with labeled streams** | All output is tagged with a channel name. `[ai]` for AI responses, `[py]` for Python output, `[graph]` for graph execution traces, `[otel]` for span events. Users can mute/unmute channels to reduce noise. | Med | asyncio.Queue per channel, channel registry, render layer | **Novel.** Docker Compose's labeled output adapted for REPL. Each channel has a name, color, and mute state. Output lines carry channel metadata. Render filters by mute state. |
| **Channel surfing / muting** | `/mute otel` silences OTel span output. `/unmute otel` restores it. `/solo ai` shows only AI output. `/channels` lists all channels with status. | Low | Channel registry with boolean mute flags | Low complexity because it's just a filter on the render path. The channel abstraction does the heavy lifting. |
| **AI as a first-class namespace object** | `ai` lives in the namespace. `ai("explain this graph")` triggers NL interaction. `ai.fill(MyNode, context)` calls bae's LM fill directly. `ai.model` shows current model. Tab-completable. | Med | AI object wrapping bae's LM protocol, `__dir__` for completion, `__call__` for chat | **Novel.** AI is not a separate tool -- it's a Python object you compose with. `result = ai.fill(RecommendOOTD, {"weather": "rainy"})` works like any other Python call. |
| **Reflective namespace introspection** | `/ns` shows all namespace variables with types and summaries. `/ns graph` shows a specific object's structure. Objects added to namespace get automatic rich display. | Med | `inspect` module, custom `__repr__` on bae objects, formatted display | Builds on Python's introspection. Differentiator is the integration: bae `Node` classes show their fields and annotations, `Graph` objects show topology, `GraphResult` shows trace summary. |
| **Graph-aware REPL context** | When a graph runs, its trace lands in the namespace. `_` holds the last result (like Python REPL). `_trace` holds the last graph trace. Node instances from the trace are directly inspectable. | Low-Med | Graph execution populates namespace variables | Small feature, large usability impact. After `result = await graph.arun(start)`, `result.trace[-1]` is the terminal node with all fields accessible. |
| **OTel span instrumentation** | Every REPL command emits an OTel span. Graph executions emit nested spans per node. AI calls emit GenAI semantic convention spans. Spans go to the `[otel]` channel and optionally to a collector (Jaeger). | Med-High | opentelemetry-api, opentelemetry-sdk, OTel GenAI semantic conventions | Valuable for understanding what happened during a session. Not every user needs it, but the instrumentation foundation enables future observability features. |
| **Ephemeral spawned interfaces (HitL)** | During graph execution, a node that needs human input spawns a focused input UI (new terminal tab, browser form, VS Code panel). After human responds, execution resumes. | High | Terminal spawning (Ghostty AppleScript on macOS), async checkpoint/resume pattern | **Highest complexity differentiator.** Ghostty's AppleScript API supports new window/tab/split and send text, but the programmatic API is limited (discussion #2353). Needs robust fallback (inline prompt in REPL). Defer full implementation to later phase; start with inline HitL. |

## Anti-Features

Features to deliberately NOT build. These are tempting but wrong for cortex's scope.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Extending IPython** | IPython's architecture assumes it owns the event loop, the namespace, and the display system. Fighting IPython's assumptions to add channels and modes is harder than building on prompt_toolkit directly. ptpython proves custom REPLs can match IPython's UX without its baggage. | Build on prompt_toolkit + ptpython's patterns. Cherry-pick ideas (magic commands, rich display) without the framework coupling. |
| **Auto-detecting NL vs Python input** | xonsh's heuristic mode detection creates ambiguity. `print` -- is that a Python function call or a natural language request? `ast.parse()` can determine if input is valid Python, but many NL inputs are also valid Python identifiers. The heuristic will always have false positives. | Explicit mode prefix. Default to Python mode (the common case for a Python REPL). NL requires a prefix character or mode switch. Unambiguous. |
| **Full TUI / full-screen application** | prompt_toolkit supports full-screen layouts (HSplit/VSplit/Window), but building a full TUI is massive scope. tmux-style panes, scrollable output regions, resizable splits -- each adds complexity. | Scrollback terminal output with labeled lines (like Docker Compose). One input area, one output stream. Simple and sufficient. Full TUI is a v5 feature if needed. |
| **Persistent AI conversation memory** | Maintaining a full conversation history across REPL sessions requires storage, context window management, summarization. This is a product, not a feature. | AI context is the current REPL session. Namespace is the memory. When the session ends, the conversation ends. Users can save state explicitly (`import pickle; pickle.dump(namespace, f)`). |
| **Plugin / extension system** | Extensibility architectures (hooks, registries, plugin discovery) are complex to design and maintain. Bae is a framework, not a platform. | Python is the extension system. Users import what they need and add it to the namespace. `exec(open('my_setup.py').read(), namespace)` is the plugin system. |
| **Web-based REPL** | Jupyter already exists. Building a web frontend for cortex duplicates Jupyter's value while adding WebSocket complexity, frontend code, and browser compatibility issues. | Terminal-only. Users who want web can use Jupyter with bae imported. |
| **Voice / multimodal input** | Tempting with modern LLM capabilities, but adds audio capture, speech-to-text, latency, and platform-specific dependencies. | Text input only. NL mode handles natural language as text. |
| **Built-in graph visualization in terminal** | Rendering Mermaid diagrams in a terminal is either low-fidelity (ASCII art) or requires a separate viewer. The existing `bae graph show` opens mermaid.live in a browser. | Keep `bae graph show` for visualization. In the REPL, `graph.to_mermaid()` prints the Mermaid source. Users paste it into mermaid.live or use `bae graph show`. |

## Feature Dependencies

```
prompt_toolkit REPL shell (foundation)
    |
    +---> Async Python execution (top-level await)
    |         |
    |         +---> Shared mutable namespace
    |         |         |
    |         |         +---> Bae objects pre-loaded
    |         |         |
    |         |         +---> Graph-aware context (_, _trace)
    |         |         |
    |         |         +---> Reflective namespace introspection (/ns)
    |         |         |
    |         |         +---> AI agent object in namespace
    |         |                   |
    |         |                   +---> AI callable (__call__ for NL)
    |         |                   |
    |         |                   +---> AI methods (.fill, .choose_type)
    |         |                   |
    |         |                   +---> AI output -> [ai] channel
    |         |
    |         +---> Mode dispatcher
    |                   |
    |                   +---> Py mode (default): exec() / eval()
    |                   |
    |                   +---> NL mode (prefix): dispatch to AI agent
    |                   |
    |                   +---> Graph mode (prefix): dispatch to bae CLI
    |
    +---> Channel registry (foundation for I/O)
              |
              +---> Channel: [py] -- Python stdout/stderr capture
              |
              +---> Channel: [ai] -- AI responses
              |
              +---> Channel: [graph] -- Graph execution trace events
              |
              +---> Channel: [otel] -- OTel span events
              |
              +---> Mute/unmute/solo commands
              |
              +---> Render layer (label + color + filter)

OTel instrumentation (orthogonal, can be added anytime)
    |
    +---> Session span (root)
    |
    +---> Command spans (per input)
    |
    +---> GenAI spans (per LM call)
    |
    +---> Node spans (per graph step)
    |
    +---> [otel] channel output

Ephemeral spawned interfaces (highest complexity, defer)
    |
    +---> HitL checkpoint pattern (async wait for human input)
    |
    +---> Terminal spawning (Ghostty AppleScript, fallback to inline)
    |
    +---> Browser form spawning (future)
```

## Mode Switching: Expected Behavior

### Prefix-Based Dispatch

| Input | Mode | What Happens |
|-------|------|-------------|
| `x = 42` | Py (default) | Python exec. `x` added to namespace. |
| `result = await graph.arun(start)` | Py (default) | Async Python exec. Top-level await works. |
| `> what does this graph do?` | NL | Stripped prefix, sent to `ai("what does this graph do?")`. Response appears on `[ai]` channel. AI can read namespace for context. |
| `> explain _trace` | NL | AI inspects `_trace` from namespace, explains the last graph execution. |
| `! run ootd --input '{"msg": "rainy day"}'` | Graph | Dispatched as `bae run ootd ...`. Output on `[graph]` channel. Result lands in `_` and `_trace`. |
| `/mute otel` | Command | REPL meta-command. Mutes the `[otel]` channel. Not sent to any mode. |
| `/ns` | Command | REPL meta-command. Shows namespace contents. |

### Mode Persistence vs Per-Line

Two approaches, with a recommendation:

**Per-line prefix (recommended):** Each line declares its mode. Default is Py. `>` prefix for NL. `!` prefix for graph. `/` prefix for meta-commands. This is how IPython magics work -- each line is self-contained.

**Sticky mode:** `/mode nl` switches to NL mode. All subsequent input is NL until `/mode py`. This is how Aider works. More convenient for extended NL conversations, but confusing when switching frequently.

**Recommendation:** Per-line prefix as primary, with sticky mode as optional (`/mode nl` to stay in NL until `/mode py`). Default is Py mode. This gives unambiguous single-line dispatch with an escape hatch for extended conversations.

## Channel I/O: Expected Behavior

### Channel Lifecycle

1. Channels are registered at REPL startup: `py`, `ai`, `graph`, `otel`, `sys`
2. Each channel has: name, color, mute state (bool), asyncio.Queue
3. Background render task reads from all unmuted channel queues, prints with `[name]` prefix in channel color
4. `patch_stdout=True` ensures channel output appears above the prompt line

### Channel Surfing Commands

| Command | Effect |
|---------|--------|
| `/channels` | List all channels with mute status |
| `/mute <name>` | Silence a channel (output still queued, just not rendered) |
| `/unmute <name>` | Restore a channel to rendering |
| `/solo <name>` | Mute all channels except this one |
| `/unsolo` | Restore all channels to previous mute state |

### Output Format

```
[py]    x = 42
[ai]    The graph has 3 nodes: IsTheUserGettingDressed -> AnticipateUsersDay -> RecommendOOTD
[graph] Step 1: IsTheUserGettingDressed (resolved 2 deps)
[graph] Step 2: AnticipateUsersDay (resolved 1 dep, 1 recall)
[graph] Step 3: RecommendOOTD (terminal)
[otel]  span: bae.graph.run duration=3.2s nodes=3
```

### Channel as Python Object

Channels should also be accessible from the namespace:
```python
ch = channels["ai"]      # get channel object
ch.muted = True           # programmatic mute
ch.write("custom msg")    # write to channel from code
```

## Namespace Introspection: Expected Behavior

### What /ns Shows

```
py> /ns
Namespace (12 objects):

  Bae Types:
    Node          class    Base class for graph nodes
    Graph         class    Agent graph from type hints
    Dep           class    Field annotation for dep injection
    Recall        class    Field annotation for trace recall

  Session:
    ai            Agent    AI agent (claude-sonnet-4)
    graph         Graph    3 nodes, 1 terminal
    result        Result   GraphResult with 3-node trace
    _             Node     RecommendOOTD (terminal)
    _trace        list     [IsTheUser..., Anticipate..., Recommend...]

  User:
    x             int      42
    my_func       func     my_func(a: int, b: str) -> bool
```

### What /ns <object> Shows

```
py> /ns graph
Graph: 3 nodes, 1 terminal

  Start: IsTheUserGettingDressed
    Fields: user_message (str, plain), is_dressed (bool, plain)
    Returns: AnticipateUsersDay

  AnticipateUsersDay
    Fields: weather (Weather, Dep), dressed_status (str, Recall), ...
    Returns: RecommendOOTD

  RecommendOOTD (terminal)
    Fields: top (str, plain), bottom (str, plain), footwear (str, plain)
    Returns: None
```

### Implementation

Namespace introspection uses:
- `type(obj).__name__` for type names
- `inspect.signature(obj)` for callable signatures
- bae's `classify_fields(node_cls)` for field annotation info (Dep/Recall/plain)
- `Graph.nodes`, `Graph.edges`, `Graph.terminal_nodes` for topology
- Custom `__cortex_repr__` protocol on bae objects for rich display

## AI Agent Object: Expected Behavior

### The `ai` Object

```python
# Natural language interaction (same as NL mode)
ai("what does this graph do?")
# -> Reads namespace, generates response on [ai] channel

# Direct LM protocol access (wraps bae's LM)
node = await ai.fill(RecommendOOTD, {"weather": "rainy"})
# -> Calls lm.fill() with the given context

chosen = await ai.choose_type([OptionA, OptionB], context)
# -> Calls lm.choose_type()

# Configuration
ai.model                    # "claude-sonnet-4-20250514"
ai.backend                  # ClaudeCLIBackend instance
ai.temperature = 0.7        # Adjust generation params

# Introspection
dir(ai)                     # ['fill', 'choose_type', 'model', 'backend', ...]
```

### AI Context Assembly

When `ai("explain _trace")` is called, the agent needs context. The context assembly protocol:

1. Serialize the current namespace to a summary (not full dump -- too large)
2. Include specifically referenced variables (`_trace` was mentioned)
3. Include the REPL command history (last N commands)
4. Include bae graph topology if a graph is in namespace
5. Send assembled context + user message to LM

This is NOT a full RAG pipeline. It's a focused context window assembly that leverages the namespace as structured state.

## OTel Instrumentation: Expected Behavior

### Span Hierarchy

```
cortex.session                           # root span, entire REPL session
  cortex.command [input="x = 42"]        # per-input span
  cortex.command [input="> explain"]     # NL command
    gen_ai.invoke_agent                  # AI invocation
      gen_ai.fill [model=claude-sonnet]  # LM call
  cortex.command [input="! run ootd"]    # graph command
    bae.graph.run [graph=ootd]           # graph execution
      bae.node.resolve [node=IsThe...]   # per-node
      bae.node.resolve [node=Antic...]
      bae.node.resolve [node=Recom...]
```

### Attributes Following GenAI Semantic Conventions

| Attribute | Value Example | Convention |
|-----------|---------------|------------|
| `gen_ai.operation.name` | `invoke_agent`, `fill`, `choose_type` | OTel GenAI semconv |
| `gen_ai.agent.name` | `cortex.ai` | OTel GenAI semconv |
| `gen_ai.request.model` | `claude-sonnet-4-20250514` | OTel GenAI semconv |
| `gen_ai.usage.input_tokens` | `1234` | OTel GenAI semconv |
| `gen_ai.usage.output_tokens` | `567` | OTel GenAI semconv |
| `cortex.mode` | `py`, `nl`, `graph` | Custom |
| `cortex.channel` | `ai`, `py`, `graph` | Custom |
| `bae.node.type` | `RecommendOOTD` | Custom |
| `bae.graph.start` | `IsTheUserGettingDressed` | Custom |

### Integration Points

OTel spans are emitted via decorators or context managers on:
- REPL command dispatch (per input)
- LM backend calls (fill, choose_type) -- bae's existing LM protocol
- Graph execution loop steps (bae's graph.arun)
- Dep resolution (bae's resolver)

The `[otel]` channel receives human-readable span summaries. A Jaeger exporter sends structured trace data for visualization.

## MVP Recommendation

Build in this order, where each phase is independently useful:

### Phase 1: REPL Shell + Namespace
**Prioritize:**
1. prompt_toolkit async REPL with top-level await
2. Shared namespace with bae objects pre-loaded
3. Mode dispatcher (Py default, prefix-based NL and graph)
4. Mode indicator in prompt
5. History persistence

**Why first:** Everything else builds on having a working REPL with a namespace. This is the foundation.

### Phase 2: Channel I/O
**Prioritize:**
1. Channel registry and labeled output
2. Python stdout/stderr capture to `[py]` channel
3. Mute/unmute/solo commands
4. Render layer with color-coded prefixes

**Why second:** Without channels, all output is interleaved and noisy. Channels are the I/O primitive that every subsequent feature writes to.

### Phase 3: AI Agent Object
**Prioritize:**
1. `ai` object in namespace with `__call__` for NL
2. `ai.fill()` and `ai.choose_type()` wrapping bae's LM
3. AI output routed to `[ai]` channel
4. Context assembly from namespace

**Why third:** The AI agent depends on both the namespace (phase 1) and channels (phase 2). Building it third means it can leverage both.

### Phase 4: Namespace Introspection
**Prioritize:**
1. `/ns` command showing namespace contents
2. `/ns <object>` showing object details
3. Bae-aware display (Graph topology, Node fields, GraphResult trace)

**Why fourth:** Nice-to-have polish. The REPL is fully functional without it, but introspection makes it discoverable and learnable.

### Phase 5: OTel Instrumentation
**Prioritize:**
1. Span decorators on REPL command dispatch
2. Span decorators on LM calls (existing bae backends)
3. `[otel]` channel for human-readable span output
4. Optional Jaeger exporter

**Why fifth:** Observability is valuable but not load-bearing. It can be added without changing any existing code (decorators/context managers).

**Defer:**
- Ephemeral spawned interfaces (HitL) -- too complex for initial build, Ghostty API still evolving
- Sticky mode switching -- per-line prefix is sufficient for v4.0
- Full TUI layout -- scrollback terminal output is sufficient

## Key Insights From Research

### 1. prompt_toolkit is the Right Foundation

prompt_toolkit + ptpython patterns give you async REPL, syntax highlighting, multiline editing, tab completion, dynamic prompts, and bottom toolbars for free. Building on IPython would mean fighting its event loop ownership and display system. Building from stdlib `code.InteractiveConsole` would mean reimplementing everything prompt_toolkit gives for free.

### 2. Explicit Mode Switching Beats Heuristic Detection

xonsh proves that implicit mode detection creates ambiguity. IPython's `%` prefix and Aider's `/` slash commands prove that explicit prefix characters are intuitive and unambiguous. For cortex, Python should be the default mode (it's a Python REPL), with NL and graph as explicitly prefixed alternatives.

### 3. Channels are Labels on asyncio.Queues

The channel abstraction is simpler than it sounds. It's a dict of `{name: asyncio.Queue}` with a render loop that reads from unmuted queues and prints with colored prefixes. No pub/sub framework, no message broker. Just labeled queues with a filter.

### 4. AI-as-Object is the Real Innovation

Every existing AI coding tool treats the AI as "the system" -- it controls the loop, you give it instructions. Cortex inverts this: the AI is an object in YOUR namespace. You call it like a function. You compose it with Python code. You pass it bae types and get bae types back. This is the difference between "AI-first tool" and "Python-first tool with AI."

### 5. OTel GenAI Conventions Are Young but Directionally Correct

The semantic conventions for GenAI agent spans are in Development status. They may change. But the span hierarchy pattern (agent -> tool -> LM call) and key attributes (model, tokens, operation name) are stable enough to build against. Using them now means cortex's telemetry is compatible with Datadog, Jaeger, and other OTel consumers.

### 6. Ghostty's Programmatic API is Not Ready for HitL

Ghostty supports splits, tabs, and AppleScript on macOS, but the full programmatic scripting API is still under discussion (GitHub discussion #2353). Building HitL around Ghostty-specific APIs would be fragile. Start with inline prompts in the REPL (works everywhere), and add terminal spawning as a progressive enhancement.

## Sources

**Official Documentation (HIGH confidence):**
- [prompt_toolkit docs](https://python-prompt-toolkit.readthedocs.io/) -- REPL building, full-screen apps, async support
- [ptpython async embed example](https://github.com/prompt-toolkit/ptpython/blob/main/examples/asyncio-python-embed.py) -- Async REPL with custom namespace
- [Python `inspect` module](https://docs.python.org/3/library/inspect.html) -- Runtime introspection
- [Python `code` module](https://docs.python.org/3/library/code.html) -- InteractiveConsole namespace management
- [Python `ast` module](https://docs.python.org/3/library/ast.html) -- Code vs non-code detection
- [asyncio.Queue](https://docs.python.org/3/library/asyncio-queue.html) -- Channel primitive
- [asyncio.TaskGroup](https://docs.python.org/3/library/asyncio-task.html) -- Structured concurrency (Python 3.11+)
- [OTel GenAI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) -- Semantic conventions for agent tracing
- [OTel GenAI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) -- Semantic conventions for LM calls
- [OTel AI Agent Observability blog](https://opentelemetry.io/blog/2025/ai-agent-observability/) -- Evolving standards

**Framework References (MEDIUM confidence):**
- [xonsh shell](https://xon.sh/) -- Multi-mode shell (Python + subprocess)
- [Aider](https://aider.chat/docs/) -- Chat mode switching pattern
- [Open Interpreter](https://github.com/openinterpreter/open-interpreter) -- AI-as-REPL pattern
- [Rich library live display](https://rich.readthedocs.io/en/latest/live.html) -- Async terminal updates
- [Docker container logs](https://docs.docker.com/reference/cli/docker/container/logs/) -- Multiplexed stream protocol
- [Docker SDK multiplex docs](https://docker-py.readthedocs.io/en/stable/user_guides/multiplex.html) -- Labeled output streams
- [IPython rich display](https://ipython.readthedocs.io/en/stable/config/integrating.html) -- Custom object representation
- [Ghostty scripting discussion](https://github.com/ghostty-org/ghostty/discussions/2353) -- API status

**Architecture References (MEDIUM confidence):**
- [Claude Code vs Cursor comparison](https://www.qodo.ai/blog/claude-code-vs-cursor/) -- AI agent REPL architectures
- [Unbundled coding AI stack](https://arnav.tech/beyond-copilot-cursor-and-claude-code-the-unbundled-coding-ai-tools-stack) -- AI tool architecture patterns
- [PEP 762 - REPL-acing the default REPL](https://peps.python.org/pep-0762/) -- Python 3.13+ REPL improvements

---

*Research conducted: 2026-02-13*
*Focus: Feature landscape for cortex REPL — bae v4.0 milestone*
