# Architecture: Graph Runtime in Cortex

**Domain:** Concurrent graph execution engine integrated with async REPL
**Researched:** 2026-02-15
**Confidence:** HIGH (direct codebase analysis, all integration points verified against existing source)

## Existing Architecture (What We Build On)

### Current Component Map

```
bae/graph.py         Graph class with arun() loop, type-hint topology
bae/node.py          Node base (Pydantic), __call__ routing
bae/resolver.py      Dep/Recall field resolution, topo-sorted DAG
bae/result.py        GraphResult(node, trace)
bae/markers.py       Dep, Recall, Effect annotations
bae/lm.py            LM protocol, ClaudeCLIBackend
bae/work/prompt.py   Prompt protocol, TerminalPrompt, gate deps

bae/repl/shell.py    CortexShell: 4 modes, prompt_toolkit REPL
bae/repl/tasks.py    TaskManager: asyncio task lifecycle
bae/repl/channels.py ChannelRouter: labeled I/O, ViewFormatter protocol
bae/repl/views.py    UserView, DebugView, AISelfView formatters
bae/repl/ai.py       AI agent with eval loop
bae/repl/store.py    SessionStore (SQLite+FTS5)
bae/repl/toolbar.py  ToolbarConfig, named widgets
bae/repl/modes.py    Mode enum (NL, PY, GRAPH, BASH)
bae/repl/exec.py     async_exec with top-level await
bae/repl/namespace.py  Seed namespace, NsInspector
```

### Current Graph-REPL Integration (Stub)

Graph mode exists but is a stub. The existing integration point in `shell.py`:

```python
# shell.py lines 333-351
async def _run_graph(self, text: str) -> None:
    graph = self.namespace.get("graph")
    if not graph:
        self.router.write("graph", "(Graph mode stub) Not yet implemented.", mode="GRAPH")
        return
    try:
        result = await channel_arun(graph, self.router, text=text)
        if result and result.trace:
            self.namespace["_trace"] = result.trace
    except asyncio.CancelledError:
        self.router.write("debug", "cancelled graph task", mode="DEBUG")
    except Exception as exc:
        trace = getattr(exc, "trace", None)
        if trace:
            self.namespace["_trace"] = trace
        tb = traceback.format_exc()
        self.router.write("graph", tb.rstrip("\n"), mode="GRAPH", metadata={"type": "error"})
```

And `channel_arun` captures graph logger output and routes through `[graph]` channel:

```python
# shell.py lines 468-488
async def channel_arun(graph, router, *, lm=None, max_iters=10, **kwargs):
    # Captures bae.graph logger -> [graph] channel
    # Writes terminal node repr as result
```

### Current Input Gate Mechanism

`bae/work/prompt.py` defines the `Prompt` protocol with `ask()` and `confirm()`. `TerminalPrompt` blocks on `input()` via `run_in_executor`. Graphs use `PromptDep = Annotated[Prompt, Dep(get_prompt)]` to inject the prompt callback. Gate deps like `ContinueGate = Annotated[bool, Dep(confirm_continue)]` wrap confirm calls.

**Critical observation:** `TerminalPrompt.ask()` calls `input()` in an executor, which blocks waiting for stdin. This works standalone but **collides with cortex** because cortex owns stdin via `prompt_toolkit.PromptSession.prompt_async()`. Two things cannot read stdin at once.

### Key Constraints

1. **prompt_toolkit owns stdin.** All user input must flow through `prompt_async()`. Background tasks cannot call `input()`.
2. **patch_stdout context.** All terminal output must go through `print_formatted_text()` for prompt compatibility.
3. **TaskManager is fire-and-forget.** Tasks are submitted, tracked, and cancellable. No built-in mechanism for task-to-prompt communication.
4. **Graph.arun() is a blocking loop.** It runs node-by-node sequentially. When a node's dep calls `prompt.ask()`, the entire graph blocks waiting for user response.

## Architecture: Graph Runtime Integration

### Design Principle

The graph runtime is **not a new subsystem** -- it is the graph's `arun()` adapted to cortex's existing primitives. The new components are:

1. **GraphRegistry** -- tracks graphs and their running instances (like `_ai_sessions` but for graphs)
2. **CortexPrompt** -- a Prompt implementation that suspends the graph via asyncio.Future and creates a pending input notification
3. **GraphRunner** -- wraps a single graph execution, bridging channels and input gates
4. **Toolbar badge** -- pending input count widget

### Component Diagram

```
                   User types in GRAPH mode
                           |
                           v
                    CortexShell._dispatch()
                           |
                           v
                    _run_graph(text)
                           |
                    +------+------+
                    |             |
              (launch cmd)   (respond cmd)
                    |             |
                    v             v
              GraphRegistry   GraphRegistry
              .launch(name)   .respond(gid, text)
                    |             |
                    v             v
              GraphRunner     runner._pending_future
              (new task)      .set_result(text)
                    |             |
                    v             v
              graph.arun()    node resumes
                    |             execution
                    v
              Node.__call__()
                    |
                    v
              prompt.ask(question)
                    |
                    v
              CortexPrompt.ask()
                    |
                    +-- creates asyncio.Future
                    +-- writes notification to [graph] channel
                    +-- increments pending count (toolbar badge)
                    +-- awaits Future (graph suspends here)
                    |
                    v
              [user sees notification, types response]
                    |
                    v
              GraphRegistry.respond(gid, text)
                    |
                    v
              Future.set_result(text)
                    |
                    v
              CortexPrompt.ask() returns PromptResult
                    |
                    v
              node continues execution
```

### New Components

#### 1. GraphRegistry (`bae/repl/graphs.py` -- NEW)

The registry tracks graph definitions and running instances. It is the graph-mode analog of `_ai_sessions` in shell.py.

```python
@dataclass
class RunningGraph:
    """A single graph execution in progress."""
    gid: str                              # short id: "g1", "g2", ...
    graph: Graph                          # the Graph object
    runner: GraphRunner                   # wraps the async execution
    task: TrackedTask                     # TaskManager handle
    prompt: CortexPrompt                  # the prompt implementation for this run
    started: float                        # time.time()
    name: str                             # display name (graph.start.__name__)

class GraphRegistry:
    """Tracks graph definitions and running instances."""

    def __init__(self, router: ChannelRouter, tm: TaskManager, lm: LM):
        self._definitions: dict[str, Graph] = {}   # name -> Graph
        self._running: dict[str, RunningGraph] = {} # gid -> RunningGraph
        self._next_id: int = 1
        self._router = router
        self._tm = tm
        self._lm = lm

    def register(self, name: str, graph: Graph) -> None:
        """Register a graph definition by name."""
        self._definitions[name] = graph

    def launch(self, name: str, **kwargs) -> RunningGraph:
        """Launch a registered graph. Returns the running instance."""
        graph = self._definitions[name]
        gid = f"g{self._next_id}"
        self._next_id += 1
        prompt = CortexPrompt(gid, self._router)
        runner = GraphRunner(graph, prompt, self._router, self._lm)
        coro = runner.run(**kwargs)
        tt = self._tm.submit(coro, name=f"graph:{gid}:{name}", mode="graph")
        rg = RunningGraph(
            gid=gid, graph=graph, runner=runner,
            task=tt, prompt=prompt, started=time.time(), name=name,
        )
        self._running[gid] = rg
        return rg

    def respond(self, gid: str, text: str) -> bool:
        """Deliver user input to a suspended graph. Returns True if delivered."""
        rg = self._running.get(gid)
        if rg is None or not rg.prompt.is_pending:
            return False
        rg.prompt.deliver(text)
        return True

    def pending(self) -> list[RunningGraph]:
        """Graphs waiting for user input."""
        return [rg for rg in self._running.values() if rg.prompt.is_pending]

    def active(self) -> list[RunningGraph]:
        """All running graphs (pending + executing)."""
        return [
            rg for rg in self._running.values()
            if rg.task.state == TaskState.RUNNING
        ]

    @property
    def pending_count(self) -> int:
        return len(self.pending())
```

**Why a registry and not just namespace?** Multiple graphs can run concurrently. Each needs its own `CortexPrompt` instance and its own `gid` for input routing. The registry manages this multiplexing -- `respond(gid, text)` routes input to the right graph's pending future.

**Why not reuse `_ai_sessions`?** AI sessions are conversation state. Graph runs are task executions with lifecycle (start, suspend, resume, complete). Different semantics, different data.

#### 2. CortexPrompt (`bae/repl/graphs.py` -- NEW, in same file)

Implements the `Prompt` protocol from `bae/work/prompt.py`. Instead of blocking on `input()`, it creates an `asyncio.Future`, writes a notification to the `[graph]` channel, and awaits the future. The future is resolved when the user responds via graph mode.

```python
class CortexPrompt:
    """Prompt implementation that suspends graph execution via asyncio.Future.

    When a graph node calls prompt.ask(), this:
    1. Creates an asyncio.Future
    2. Writes the question to [graph] channel as a pending notification
    3. Awaits the future (graph coroutine suspends)
    4. Returns when deliver() is called with the user's response
    """

    def __init__(self, gid: str, router: ChannelRouter):
        self._gid = gid
        self._router = router
        self._pending: asyncio.Future | None = None
        self._pending_question: str = ""

    @property
    def is_pending(self) -> bool:
        return self._pending is not None and not self._pending.done()

    @property
    def pending_question(self) -> str:
        return self._pending_question if self.is_pending else ""

    async def ask(
        self,
        question: str,
        *,
        choices: list[PromptChoice] | None = None,
        multi_select: bool = False,
    ) -> PromptResult:
        loop = asyncio.get_event_loop()
        self._pending = loop.create_future()
        self._pending_question = question

        # Format notification with choices
        display = question
        if choices:
            for i, c in enumerate(choices, 1):
                desc = f" -- {c.description}" if c.description else ""
                display += f"\n  {i}. {c.label}{desc}"

        self._router.write(
            "graph", display, mode="GRAPH",
            metadata={"type": "input_gate", "gid": self._gid},
        )

        # Graph suspends here until deliver() is called
        text = await self._pending
        self._pending = None
        self._pending_question = ""
        return PromptResult(text=text)

    async def confirm(self, message: str) -> bool:
        result = await self.ask(message)
        return result.text.strip().lower() in ("y", "yes", "")

    def deliver(self, text: str) -> None:
        """Called by GraphRegistry.respond() to resume the graph."""
        if self._pending is not None and not self._pending.done():
            self._pending.set_result(text)
```

**Why asyncio.Future, not asyncio.Event?** `Event` is boolean -- it signals but carries no data. `Future` carries the user's response text as its result value. The graph needs the response content, not just a signal.

**Why not asyncio.Queue?** Queue allows multiple items. A graph gate expects exactly one response per ask. Future is the right primitive -- one producer, one consumer, one value.

**Thread safety:** Both the graph (awaiting the future) and the REPL input handler (calling `deliver()`) run on the same event loop. `Future.set_result()` is safe to call from the same loop. No threading concerns.

#### 3. GraphRunner (`bae/repl/graphs.py` -- NEW, in same file)

Wraps a single graph execution, bridging between `graph.arun()` and cortex's channel system. Handles prompt injection, channel output, error capture, and trace storage.

```python
class GraphRunner:
    """Wraps a single graph.arun() execution for cortex integration."""

    def __init__(
        self,
        graph: Graph,
        prompt: CortexPrompt,
        router: ChannelRouter,
        lm: LM,
    ):
        self.graph = graph
        self.prompt = prompt
        self._router = router
        self._lm = lm
        self.trace: list[Node] | None = None
        self.result: GraphResult | None = None
        self.error: Exception | None = None

    async def run(self, **kwargs) -> GraphResult | None:
        """Execute the graph with cortex-integrated prompt and channel output."""
        # Inject CortexPrompt as the prompt implementation
        from bae.work.prompt import _prompt
        import bae.work.prompt as prompt_mod
        old_prompt = prompt_mod._prompt
        prompt_mod._prompt = self.prompt
        try:
            self.result = await self.graph.arun(lm=self._lm, **kwargs)
            self.trace = self.result.trace
            if self.result and self.result.trace:
                terminal = self.result.trace[-1]
                self._router.write(
                    "graph", repr(terminal), mode="GRAPH",
                    metadata={"type": "result", "gid": self.prompt._gid},
                )
            return self.result
        except asyncio.CancelledError:
            self._router.write(
                "debug", f"graph {self.prompt._gid} cancelled", mode="DEBUG",
            )
            raise
        except Exception as exc:
            self.error = exc
            self.trace = getattr(exc, "trace", None)
            self._router.write(
                "graph", str(exc), mode="GRAPH",
                metadata={"type": "error", "gid": self.prompt._gid},
            )
            raise
        finally:
            prompt_mod._prompt = old_prompt
```

**Why swap the module-level `_prompt`?** The `get_prompt()` function returns `prompt_mod._prompt`. All `PromptDep = Annotated[Prompt, Dep(get_prompt)]` annotations resolve through this. By swapping the module-level singleton before `arun()` and restoring after, all nodes in the graph transparently use `CortexPrompt` without any changes to node code or the Dep resolution system.

**Why not pass prompt through kwargs?** `graph.arun()` passes kwargs as start node fields. Prompt injection happens at the dep resolution layer, not the field layer. Nodes don't have a `prompt: Prompt` plain field -- they have `prompt: PromptDep` which resolves via `Dep(get_prompt)`. The dep system calls `get_prompt()` which reads the module global.

**Concern: concurrent graphs sharing the module global.** If two graphs run simultaneously, they both swap `_prompt`. Solution: each `GraphRunner.run()` sets `_prompt` to its own `CortexPrompt` instance. Since `arun()` resolves deps at each node step, and we swap before calling `arun()`, the prompt is correct for the duration. However, if two graphs interleave node resolutions, they could read each other's prompt. This is a real concern addressed in Pitfalls.

**Better approach: dep_cache injection.** The graph's `arun()` already maintains a `dep_cache` dict. If we add the prompt to the dep_cache keyed by `get_prompt`, it bypasses the module global entirely. This requires a small change to `Graph.arun()` to accept an initial dep_cache:

```python
# graph.py arun() modification
async def arun(self, *, lm=None, max_iters=10, dep_cache=None, **kwargs):
    ...
    dep_cache_internal: dict = {LM_KEY: lm}
    if dep_cache:
        dep_cache_internal.update(dep_cache)
    ...
```

Then `GraphRunner` injects prompt via dep_cache:

```python
from bae.work.prompt import get_prompt

dep_cache = {get_prompt: self.prompt}
self.result = await self.graph.arun(lm=self._lm, dep_cache=dep_cache, **kwargs)
```

This is clean, concurrent-safe, and requires a one-line change to `graph.py`. **Recommended approach.**

#### 4. Graph Mode Input Handling (`shell.py` -- MODIFIED)

Graph mode input needs to route between graph commands and graph input responses. The dispatch uses simple prefix conventions:

```python
async def _run_graph(self, text: str) -> None:
    """GRAPH mode: graph management and input response."""

    # Command dispatch
    if text.startswith("/"):
        await self._graph_command(text)
        return

    # Input response: route to graph with pending input
    # Format: @gid response  OR  just response (routes to only pending graph)
    if text.startswith("@"):
        parts = text[1:].split(" ", 1)
        gid = parts[0]
        response = parts[1] if len(parts) > 1 else ""
        if self.graphs.respond(gid, response):
            return
        self.router.write("graph", f"no pending input for {gid}", mode="GRAPH")
        return

    # Single pending graph: route input directly
    pending = self.graphs.pending()
    if len(pending) == 1:
        self.graphs.respond(pending[0].gid, text)
        return

    # Multiple pending: require @gid prefix
    if len(pending) > 1:
        labels = ", ".join(f"@{rg.gid}" for rg in pending)
        self.router.write(
            "graph", f"multiple graphs waiting. prefix with: {labels}",
            mode="GRAPH",
        )
        return

    # No pending graphs, no command: treat as launch
    self.router.write("graph", "no graphs running. use /run <name>", mode="GRAPH")

async def _graph_command(self, text: str) -> None:
    """Handle /commands in graph mode."""
    parts = text.split()
    cmd = parts[0]

    if cmd == "/run" and len(parts) >= 2:
        name = parts[1]
        kwargs_text = " ".join(parts[2:]) if len(parts) > 2 else ""
        # Parse kwargs from text (simple key=value pairs)
        kwargs = _parse_graph_kwargs(kwargs_text) if kwargs_text else {}
        try:
            rg = self.graphs.launch(name, **kwargs)
            self.router.write(
                "graph", f"launched {rg.gid} ({rg.name})",
                mode="GRAPH", metadata={"type": "lifecycle", "gid": rg.gid},
            )
        except KeyError:
            self.router.write("graph", f"unknown graph: {name}", mode="GRAPH")

    elif cmd == "/graphs":
        active = self.graphs.active()
        if not active:
            self.router.write("graph", "no graphs running", mode="GRAPH")
        else:
            for rg in active:
                status = "waiting" if rg.prompt.is_pending else "running"
                q = f": {rg.prompt.pending_question[:60]}" if rg.prompt.is_pending else ""
                self.router.write(
                    "graph", f"  {rg.gid} {rg.name} [{status}]{q}",
                    mode="GRAPH",
                )

    elif cmd == "/kill" and len(parts) >= 2:
        gid = parts[1]
        # Cancel via TaskManager
        rg = self.graphs._running.get(gid)
        if rg:
            self.graphs._tm.revoke(rg.task.task_id)

    elif cmd == "/trace" and len(parts) >= 2:
        gid = parts[1]
        rg = self.graphs._running.get(gid)
        if rg and rg.runner.trace:
            for i, node in enumerate(rg.runner.trace):
                self.router.write(
                    "graph", f"  {i+1}. {type(node).__name__}",
                    mode="GRAPH", metadata={"type": "trace"},
                )
```

**Why /commands?** Graph mode serves two purposes: managing graphs and responding to input gates. The `/` prefix disambiguates management commands from input responses. This matches common REPL conventions (IRC `/join`, Redis `CLI commands`).

**Why @gid for input routing?** With 10+ concurrent graphs, the user needs to address specific graphs. `@g1 yes` is terse and unambiguous. When only one graph is pending, the prefix is optional -- bare text goes to the only pending graph.

#### 5. Toolbar Badge (`toolbar.py` -- MODIFIED)

A pending input count on the toolbar, visible in all modes (not just graph mode). This is "shush mode" -- the user sees `2 pending` while working in NL or PY mode, knowing graphs are waiting.

```python
def make_pending_widget(shell) -> ToolbarWidget:
    """Built-in widget: pending graph input count (hidden when zero)."""
    def widget():
        n = shell.graphs.pending_count
        if n == 0:
            return []
        return [("class:toolbar.pending", f" {n} pending ")]
    return widget
```

Registered in `CortexShell.__init__()`:

```python
self.toolbar.add("pending", make_pending_widget(self))
```

Style:

```python
"toolbar.pending": "fg:ansimagenta bold",
```

#### 6. Graph Channel Metadata Types

The `[graph]` channel already exists in `CHANNEL_DEFAULTS`. The new metadata types flowing through it:

| Metadata Type | When | Content |
|---------------|------|---------|
| `input_gate` | Node calls prompt.ask() | The question text with choices |
| `result` | Graph completes normally | Terminal node repr |
| `error` | Graph raises exception | Error message |
| `lifecycle` | Graph launched/completed/cancelled | Status message |
| `trace` | User requests /trace | Node name list |
| `log` | Graph logger output (existing) | Debug log lines |

Metadata includes `gid` for all graph-specific writes, enabling view formatters to scope rendering per graph.

### Integration with Existing View System

The existing `UserView`, `DebugView`, and `AISelfView` formatters render based on `metadata["type"]`. Graph writes flow through the same pipeline:

```
CortexPrompt.ask()
    |
    v
router.write("graph", question, metadata={"type": "input_gate", "gid": "g1"})
    |
    v
Channel("graph").write(...)
    |
    v
Channel._display(...)
    |
    v
active_formatter.render("graph", "#ffaf87", question, metadata={...})
    |
    +-- UserView: render question with visual indicator (waiting icon)
    +-- DebugView: raw content with all metadata
    +-- AISelfView: graph-perspective tags
```

**UserView additions for graph:**

```python
# In UserView.render(), add graph-specific handling:
if content_type == "input_gate":
    gid = meta.get("gid", "?")
    self._render_prefixed(channel_name, color, f"[{gid}] {content}", meta)
    return
```

Minimal -- the existing `_render_prefixed` handles it. No new Rich panels needed for graph output. Graph I/O is text, not code execution.

## Data Flow

### Graph Launch Flow

```
User: /run new_project
    |
    v
_graph_command("/run new_project")
    |
    v
graphs.launch("new_project")
    |
    v
GraphRegistry:
    1. Create CortexPrompt(gid="g1", router)
    2. Create GraphRunner(graph, prompt, router, lm)
    3. dep_cache = {get_prompt: prompt}
    4. coro = runner.run(dep_cache=dep_cache)
    5. tm.submit(coro, name="graph:g1:new_project", mode="graph")
    |
    v
[graph] launched g1 (new_project)
```

### Input Gate Suspension Flow

```
graph.arun() executing...
    |
    v
Node: AgreeOnProblem.__call__()
    |
    v
self.prompt.ask("What is the problem?")
    |  (self.prompt resolves to CortexPrompt via Dep)
    v
CortexPrompt.ask():
    1. self._pending = loop.create_future()
    2. router.write("graph", "What is the problem?",
                    metadata={"type": "input_gate", "gid": "g1"})
    3. toolbar badge: 1 pending
    4. await self._pending    <-- graph suspends here
    |
    v
[user sees notification, switches to graph mode or already in it]
    |
    v
User types: "Users can't find the search button"
    |
    v
_run_graph("Users can't find the search button")
    |
    v
graphs.respond("g1", "Users can't find the search button")
    |
    v
CortexPrompt._pending.set_result("Users can't find the search button")
    |
    v
CortexPrompt.ask() returns PromptResult(text="Users can't find...")
    |
    v
AgreeOnProblem continues execution
    |
    v
toolbar badge: 0 pending
```

### Concurrent Graph Flow (10+ graphs)

```
graphs.launch("project_a")  -> g1
graphs.launch("project_b")  -> g2
graphs.launch("project_c")  -> g3
    |
    v
All three run as separate asyncio tasks via TaskManager.
Each has its own CortexPrompt, its own dep_cache, its own trace.
    |
    v
g1 hits input gate -> toolbar: 1 pending
g3 hits input gate -> toolbar: 2 pending
g2 still running   -> toolbar shows "3 tasks" (existing widget)
    |
    v
User in GRAPH mode:
    /graphs
    [graph]   g1 new_project [waiting]: What is the problem?
    [graph]   g2 quick [running]
    [graph]   g3 plan_phase [waiting]: Approve requirements?
    |
    v
User: @g3 yes              -> routes to g3, g3 resumes
User: The search UX sucks  -> only g1 pending, routes to g1
```

## Modified Components Summary

### New Files

| File | Component | Purpose |
|------|-----------|---------|
| `bae/repl/graphs.py` | CortexPrompt | Prompt implementation using asyncio.Future |
| `bae/repl/graphs.py` | GraphRunner | Wraps graph.arun() for cortex integration |
| `bae/repl/graphs.py` | GraphRegistry | Tracks definitions and running instances |
| `bae/repl/graphs.py` | RunningGraph | Dataclass for a running graph instance |

### Modified Files

| File | Change | Risk |
|------|--------|------|
| `bae/graph.py` | Add `dep_cache` param to `arun()` | LOW -- additive, backward compatible |
| `bae/repl/shell.py` | Replace `_run_graph` stub, add GraphRegistry to `__init__`, add pending widget | MEDIUM -- new control flow |
| `bae/repl/toolbar.py` | Add `make_pending_widget()` | LOW -- new function |
| `bae/repl/views.py` | Add `input_gate` rendering in UserView | LOW -- additive case |

### Unchanged Files

| File | Why Unchanged |
|------|---------------|
| `bae/node.py` | Nodes don't know about cortex |
| `bae/resolver.py` | Dep resolution unchanged, dep_cache injection handles routing |
| `bae/markers.py` | Dep, Recall, Effect unchanged |
| `bae/result.py` | GraphResult unchanged |
| `bae/lm.py` | LM protocol unchanged |
| `bae/work/prompt.py` | Prompt protocol unchanged, TerminalPrompt unchanged |
| `bae/work/new_project.py` | Graph definitions unchanged |
| `bae/repl/channels.py` | Channel system unchanged |
| `bae/repl/tasks.py` | TaskManager unchanged, used as-is |
| `bae/repl/store.py` | SessionStore unchanged |
| `bae/repl/ai.py` | AI agent unchanged |
| `bae/repl/modes.py` | Mode enum unchanged |

## Patterns to Follow

### Pattern 1: dep_cache Injection for Prompt Routing

**What:** Pass a pre-populated `dep_cache` to `graph.arun()` that maps `get_prompt` to the cortex-specific `CortexPrompt` instance.

**When:** Any time a graph runs inside cortex.

**Why:** The dep resolution system already checks `dep_cache` before calling dep functions. By pre-seeding the cache, `get_prompt` never runs -- the cached `CortexPrompt` is returned directly. This avoids module-global mutation and is safe for concurrent graphs.

```python
from bae.work.prompt import get_prompt

dep_cache = {get_prompt: cortex_prompt}
await graph.arun(dep_cache=dep_cache, **kwargs)
```

### Pattern 2: Future-Based Suspension

**What:** Use `asyncio.Future` to suspend graph execution at input gates.

**When:** A graph node needs user input inside cortex.

**Why:** The graph's `arun()` loop is a single coroutine. When it awaits a future, the entire graph suspends but the event loop continues. Other graphs, AI sessions, and the REPL prompt all keep running. When the future resolves, the graph resumes exactly where it left off.

**Not Event, not Queue:** Future carries exactly one result value (the user's text response). Event is boolean. Queue allows multiple items. Future matches the "one question, one answer" semantics of `prompt.ask()`.

### Pattern 3: Registry for Multiplexed State

**What:** Use a registry (GraphRegistry) to track multiple running instances of the same type of object (graphs), each with independent state.

**When:** Multiple concurrent graphs need independent prompts, traces, and lifecycle.

**Why:** This is the same pattern as `_ai_sessions` in `shell.py` -- a dict keyed by identifier, with factory methods for creation and lookup methods for access. The registry owns the lifecycle: create, track, clean up.

### Pattern 4: Prefix-Based Input Routing

**What:** Use `@gid` prefix to route user input to a specific graph, with implicit routing when only one graph is pending.

**When:** User responds to graph input gates in graph mode.

**Why:** Terse, familiar (IRC/Slack @mentions), and the single-pending optimization means most of the time the user just types the answer without any prefix.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Module-Global Prompt Swap

**What:** Setting `bae.work.prompt._prompt = cortex_prompt` before `arun()` and restoring after.

**Why bad:** Not concurrent-safe. If two graphs run simultaneously, they overwrite each other's prompt. Race condition: graph A swaps prompt, graph B swaps prompt, graph A's nodes resolve graph B's prompt.

**Instead:** dep_cache injection. Each graph gets its own dep_cache with its own prompt instance. No shared mutable state.

### Anti-Pattern 2: Synchronous Input in Background Tasks

**What:** Calling `input()` from a background asyncio task.

**Why bad:** prompt_toolkit owns stdin via `prompt_async()`. A concurrent `input()` call either blocks forever (stdin already consumed) or corrupts the prompt display.

**Instead:** CortexPrompt creates a Future, writes a notification, and awaits the Future. The REPL's `prompt_async()` loop reads user input and calls `deliver()` on the Future.

### Anti-Pattern 3: Graph Mode as Full-Screen TUI

**What:** Switching to a different screen/layout when entering graph mode.

**Why bad:** Violates the cortex principle of "minimal TUI -- no screen transitions." Users expect the scrollback-based REPL to persist. Full-screen mode loses scrollback context and creates jarring transitions.

**Instead:** Graph notifications appear inline in scrollback via `[graph]` channel. Toolbar badge shows pending count. Graph management is via /commands. No mode transitions beyond Shift+Tab.

### Anti-Pattern 4: Custom Event Loop for Graph Execution

**What:** Running graphs in a separate event loop or thread.

**Why bad:** Cross-loop Future resolution is undefined. The asyncio.Future must be created and resolved on the same event loop. A separate loop would require thread-safe primitives (threading.Event, queue.Queue) and lose async composability.

**Instead:** Graphs run as regular asyncio tasks on the same event loop as cortex. TaskManager.submit() handles this. The event loop multiplexes graph execution, AI sessions, and REPL input naturally.

### Anti-Pattern 5: Polling for Input

**What:** Graph execution loop periodically checking "is there input available?"

**Why bad:** Wastes CPU. Creates latency (input sits unprocessed until next poll). Complicates the clean suspension semantics.

**Instead:** Future-based suspension. Zero CPU while waiting. Instant resumption when input arrives.

## Scalability Considerations

| Concern | At 1 graph | At 10 graphs | At 50+ graphs |
|---------|------------|--------------|---------------|
| Memory | Negligible | ~10 traces in memory | Consider trace trimming |
| Event loop | No contention | Low contention (graphs mostly await LM calls) | LM call queuing needed |
| Input routing | Implicit (no @gid needed) | @gid prefix required | /graphs listing + @gid |
| Toolbar | "1 pending" | "5 pending" | Badge is sufficient, no per-graph breakdown |
| TaskManager | Standard tracking | Standard tracking | May need task pagination (already exists) |

The 10-graph target is well within asyncio's capacity. Each graph spends most of its time awaiting LM subprocess calls (`ClaudeCLIBackend._run_cli_json`), not doing CPU work. The event loop handles this naturally.

## Suggested Build Order

### Phase 1: dep_cache Injection

Add `dep_cache` parameter to `Graph.arun()`. One-line change. Unlocks concurrent prompt injection.

**Deliverables:**
- Modified `graph.py`: `arun()` accepts optional `dep_cache` dict
- Tests: `arun(dep_cache={get_prompt: mock_prompt})` uses injected prompt

### Phase 2: CortexPrompt + GraphRunner

Build the Future-based prompt and the runner wrapper. Test in isolation (no shell integration yet).

**Deliverables:**
- `bae/repl/graphs.py` with CortexPrompt, GraphRunner, RunningGraph
- Tests: CortexPrompt.ask() suspends, deliver() resumes, confirm() works
- Tests: GraphRunner.run() executes a simple graph with CortexPrompt

### Phase 3: GraphRegistry + Shell Integration

Wire GraphRegistry into CortexShell. Replace `_run_graph` stub. Add /commands.

**Deliverables:**
- GraphRegistry class in graphs.py
- Modified shell.py: `_run_graph()` with command dispatch and input routing
- Toolbar pending widget
- Tests: launch, respond, /graphs, /kill, @gid routing

### Phase 4: Graph Observability

Add /trace command, lifecycle metadata, DebugView rendering for graph events.

**Deliverables:**
- /trace command shows node execution history
- Lifecycle events (launched, completed, failed, cancelled) logged to [graph] channel
- UserView renders input_gate with visual indicator
- Completed graphs cleaned up from registry

## Sources

- Direct codebase analysis of all files listed in component map (HIGH confidence)
- `asyncio.Future` semantics: Python 3.12+ stdlib docs (HIGH confidence)
- `prompt_toolkit.patch_stdout` behavior: verified in existing codebase usage (HIGH confidence)
- Dep resolution via `dep_cache`: traced through `resolver.py` `resolve_fields()` -> `_resolve_one()` -> cache lookup (HIGH confidence)
- Concurrent asyncio task patterns: standard asyncio patterns, verified against `TaskManager` implementation (HIGH confidence)

---
*Architecture research: 2026-02-15 -- Graph runtime in cortex*
