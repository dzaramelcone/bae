# Phase 27: Graph Mode - Research

**Researched:** 2026-02-15
**Domain:** REPL command interface for graph lifecycle management, Graph API callable redesign
**Confidence:** HIGH

## Summary

Phase 27 delivers the GRAPH mode command interface (run, list, cancel, inspect, trace) AND a significant API redesign: graphs must declare their run parameters as a typed callable signature decoupled from start node fields. Currently `Graph(start=NodeClass).arun(**kwargs)` maps kwargs directly to start node fields. The new design makes each graph's run/arun a callable with a typed parameter signature, and `engine.submit()` accepts this new form.

This phase sits on top of Phase 26's foundation: GraphRegistry, GraphRun, TimingLM, and TaskManager integration. The command parsing and dispatch in GRAPH mode is straightforward string parsing -- no external libraries needed. The harder design work is the Graph API redesign and wiring it through to the engine and shell.

The entire phase uses Python 3.14 stdlib plus the existing codebase. Zero new dependencies. The command interface follows the existing mode dispatch pattern in `shell.py`. Output flows through the `[graph]` channel. The `inspect` and `trace` commands read data from `GraphRun` and `GraphResult` objects already captured by the engine.

**Primary recommendation:** Split into two concerns: (1) Graph API redesign -- make Graph produce typed callables for run/arun, update engine.submit to accept them, (2) GRAPH mode command parser and handlers for run/list/cancel/inspect/trace. The API redesign must land first since `run <expr>` depends on it.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `str.split()`/`shlex` | stdlib 3.14 | GRAPH mode command parsing | Commands are simple verb + args, no complex grammar needed |
| `time.perf_counter_ns` | stdlib 3.14 | Elapsed time display for list/inspect | Already used in GraphRun.started_ns/ended_ns |
| `inspect.signature` | stdlib 3.14 | Introspect Graph callable signatures for completions and validation | Standard tool for callable introspection |
| `prompt_toolkit.FormattedText` | existing dep | Formatted output for list/inspect/trace | Already used everywhere in shell.py |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rich.table.Table` | existing dep | Formatted tables for list/inspect output | When displaying tabular data (run list, node timings) |
| `rich.text.Text` | existing dep | Styled text for trace/inspect display | When displaying node details with field values |
| `textwrap.shorten` | stdlib 3.14 | Truncate field values in inspect display | When field values are long (e.g. LLM-generated text) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Simple str.split parsing | click/argparse subcommands | Overkill for 5 commands with 0-1 args each. str.split is the pattern used by _dispatch already. |
| Rich tables | Raw FormattedText | Rich tables auto-align columns, handle wrapping. Worth it for list/inspect. |
| Custom command registry | Dict[str, Callable] dispatch | Simple dict dispatch is cleaner than a framework for 5 commands |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Recommended Project Structure

```
bae/graph.py              # MODIFIED: Graph produces typed callables
bae/repl/engine.py        # MODIFIED: engine.submit() accepts new callable form
bae/repl/shell.py         # MODIFIED: _run_graph() becomes command dispatcher
bae/repl/graph_commands.py # NEW: command handlers for run/list/cancel/inspect/trace
tests/repl/test_graph_mode.py  # NEW: tests for command parsing and dispatch
tests/test_graph.py       # MODIFIED: tests for new Graph callable API
```

### Pattern 1: Graph API Redesign -- Typed Callable Signature

**What:** Instead of `Graph(start=NodeClass).arun(**kwargs)` where kwargs map to start node fields, each Graph exposes `run` and `arun` as callables with typed parameter signatures derived from the start node's required plain fields. This decouples the run interface from the start node's internal structure.

**When to use:** This is the core API change for Phase 27.

**Why (Dzara's design):** Run params must be loosely coupled from any node. Each graph run/arun export should be a callable with typed param signature, not an opaque object.

**Current API:**
```python
graph = Graph(start=IsTheUserGettingDressed)
result = graph.run(user_info=UserInfo(), user_message="ugh i just got up", lm=lm)
# ^^ kwargs mapped directly to start node fields -- tightly coupled
```

**New API (recommended design):**
```python
graph = Graph(start=IsTheUserGettingDressed)
# graph.arun is now a callable with typed signature:
# async def arun(user_info: UserInfo, user_message: str, *, lm: LM | None = None, ...) -> GraphResult
result = await graph.arun(user_info=UserInfo(), user_message="ugh i just got up")
# ^^ same call surface, but the signature is introspectable

# In GRAPH mode:
# > run graph.arun(user_info=UserInfo(), user_message="get dressed")
# The expression evaluates to a coroutine, engine.submit() runs it
```

**Implementation approach -- lightweight:**

The current `Graph.arun()` already accepts `**kwargs` that map to required plain fields on the start node. The `_input_fields` dict already captures these. The typed callable is simply `arun` itself, with its signature derivable from `_input_fields`.

Rather than generating a new callable object, we can:
1. Keep `Graph.arun()` as-is (it already works as a typed callable)
2. Add a `__signature__` property to Graph that exposes the typed parameter list
3. In GRAPH mode, `run <expr>` evaluates the expression in the namespace (which may call `graph.arun(...)` or any callable), and the resulting coroutine is submitted to the engine

The key insight: **the expression in `run <expr>` is just Python evaluated in the namespace.** The "typed callable" is whatever Python expression Dzara writes. The Graph object just needs to make its callable signature discoverable for tab completion and `ns()` inspection.

**Simplest implementation that satisfies Dzara's requirement:**
```python
class Graph:
    def __init__(self, start: type[Node]):
        # ... existing ...
        self._input_fields: dict[str, FieldInfo] = {}  # already computed

    @property
    def params(self) -> dict[str, FieldInfo]:
        """Run parameters -- required plain fields on the start node."""
        return dict(self._input_fields)

    # run() and arun() already accept **kwargs and validate against _input_fields
    # No change to their actual behavior
```

Then in GRAPH mode:
```
> run graph.arun(user_info=UserInfo(), user_message="get dressed")
```
This evaluates the expression, gets a coroutine, and submits it.

### Pattern 2: GRAPH Mode Command Dispatcher

**What:** GRAPH mode input is parsed as `command [args...]`. A simple dispatcher maps command names to handler functions.

**When to use:** All GRAPH mode input goes through this dispatcher.

**Example:**
```python
# bae/repl/graph_commands.py

async def dispatch_graph(text: str, shell) -> None:
    """Parse and dispatch GRAPH mode commands."""
    parts = text.strip().split(None, 1)
    if not parts:
        return

    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    handlers = {
        "run": _cmd_run,
        "list": _cmd_list,
        "ls": _cmd_list,      # alias
        "cancel": _cmd_cancel,
        "inspect": _cmd_inspect,
        "trace": _cmd_trace,
    }

    handler = handlers.get(cmd)
    if handler is None:
        shell.router.write(
            "graph", f"unknown command: {cmd}. try: run, list, cancel, inspect, trace",
            mode="GRAPH",
        )
        return

    await handler(arg, shell)
```

### Pattern 3: `run <expr>` Evaluates Namespace Expression

**What:** The `run` command evaluates a Python expression in the shell namespace. If the result is a Graph, it submits it (no-args). If it's a coroutine (from calling `graph.arun(...)`), it submits that coroutine. If it's another callable, it calls it.

**When to use:** MODE-02 implementation.

**Why:** This leverages the existing PY mode's `async_exec` for expression evaluation, but routes the result to the engine instead of displaying it.

**Example:**
```python
async def _cmd_run(expr: str, shell) -> None:
    """Evaluate namespace expression and submit resulting graph to engine."""
    if not expr.strip():
        shell.router.write("graph", "usage: run <expr>", mode="GRAPH")
        return

    try:
        result, captured = await async_exec(expr, shell.namespace)

        if asyncio.iscoroutine(result):
            # Expression returned a coroutine (e.g. graph.arun(field=val))
            run = shell.engine.submit_coro(result, shell.tm, lm=shell._lm)
        elif isinstance(result, Graph):
            # Expression returned a Graph object -- submit with no args
            run = shell.engine.submit(result, shell.tm, lm=shell._lm)
        else:
            shell.router.write(
                "graph", f"expected Graph or coroutine, got {type(result).__name__}",
                mode="GRAPH",
            )
            return

        shell.router.write(
            "graph", f"submitted {run.run_id}", mode="GRAPH",
            metadata={"type": "lifecycle", "run_id": run.run_id},
        )
        _attach_done_callback(run, shell)
    except Exception:
        import traceback
        tb = traceback.format_exc()
        shell.router.write("graph", tb.rstrip("\n"), mode="GRAPH", metadata={"type": "error"})
```

### Pattern 4: engine.submit() Accepting Coroutines

**What:** GraphRegistry gains a `submit_coro()` method that accepts an already-constructed coroutine (from `graph.arun(...)`) instead of a Graph object + kwargs.

**When to use:** When `run <expr>` evaluates to a coroutine.

**Why:** The expression `graph.arun(user_info=UserInfo(), user_message="hello")` returns a coroutine. The engine needs to wrap it with lifecycle tracking without unpacking it back into a Graph + kwargs.

**Implementation:**
```python
class GraphRegistry:
    def submit_coro(
        self, coro, tm: TaskManager, *, graph: Graph | None = None, lm: LM | None = None,
    ) -> GraphRun:
        """Submit a pre-built coroutine (from graph.arun(...)) as a managed run."""
        run_id = f"g{self._next_id}"
        self._next_id += 1
        name = graph.start.__name__ if graph else "graph"
        run = GraphRun(run_id=run_id, graph=graph)
        self._runs[run_id] = run
        wrapped = self._wrap_coro(run, coro)
        tm.submit(wrapped, name=f"graph:{run_id}:{name}", mode="graph")
        return run

    async def _wrap_coro(self, run: GraphRun, coro):
        """Wrap a coroutine with lifecycle tracking."""
        try:
            result = await coro
            run.state = GraphState.DONE
            return result
        except asyncio.CancelledError:
            run.state = GraphState.CANCELLED
            raise
        except Exception as e:
            run.state = GraphState.FAILED
            run.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            run.ended_ns = time.perf_counter_ns()
            self._archive(run)
```

**Tradeoff:** `submit_coro` cannot inject TimingLM since the coroutine is already constructed. This is acceptable -- the user can explicitly use a TimingLM if they want timing. The engine's `submit()` method (Graph + kwargs) still injects TimingLM automatically. An alternative is to have `run <expr>` evaluate the expression but NOT call arun -- instead extract the Graph and kwargs, then use `submit()`. But this fights against Dzara's design goal of "each graph run/arun export should be a callable."

**Better alternative -- hybrid approach:**
Since `run <expr>` in GRAPH mode is the primary UX, and we want timing, the recommended flow is:

1. `run <expr>` evaluates `<expr>` which should produce a Graph object
2. If additional kwargs are needed: `run graph.arun(field=val)` -- here expr is the full call
3. The engine wraps with TimingLM regardless

For case 2, instead of returning a coroutine, we intercept the pattern:
- If expr evaluates to a Graph: `engine.submit(graph, tm, lm=...)`
- If expr evaluates to a coroutine: `engine.submit_coro(coro, tm)` -- no timing injection possible, but acceptable for advanced use
- If expr is like `graph(field=val)` syntax: parse it as graph + kwargs

**Simplest correct approach:** Make `run <expr>` always evaluate in the namespace. Document that `run graph` (for no-arg graphs) and `run graph.arun(x=1, y=2)` both work. The first uses `submit()` with TimingLM; the second uses `submit_coro()` without. This is honest and composable.

### Pattern 5: List/Cancel/Inspect/Trace as Registry Queries

**What:** The remaining commands are simple reads from GraphRegistry and GraphRun data.

**list:** Queries `registry.active()` + `registry._completed`, formats as a table.
```
  ID     STATE    ELAPSED   NODE
  g1     running  3.2s      AnticipateUsersDay
  g2     done     12.1s     RecommendOOTD
  g3     failed   0.1s      (TypeError: ...)
```

**cancel <id>:** Finds the run's TaskManager task and revokes it.
```python
async def _cmd_cancel(arg, shell):
    run = shell.engine.get(arg.strip())
    if not run:
        shell.router.write("graph", f"no run {arg}", mode="GRAPH")
        return
    # Find matching task in TaskManager
    for tt in shell.tm.active():
        if tt.name.startswith(f"graph:{run.run_id}:"):
            shell.tm.revoke(tt.task_id)
            shell.router.write("graph", f"cancelled {run.run_id}", mode="GRAPH")
            return
    shell.router.write("graph", f"{run.run_id} not running", mode="GRAPH")
```

**inspect <id>:** Shows the full GraphRun with node timings and (if available) trace data.
```
  Run g1 (done, 12.1s)
  Graph: IsTheUserGettingDressed -> AnticipateUsersDay -> RecommendOOTD
  Node timings:
    AnticipateUsersDay   4.2s
    RecommendOOTD        7.9s
  Terminal: RecommendOOTD
    overall_vision: "..."
    top: "..."
```

**trace <id>:** Shows node transition history.
```
  g1 trace:
    1. IsTheUserGettingDressed (0ms)
    2. AnticipateUsersDay (4200ms)
    3. RecommendOOTD (7900ms)
```

### Anti-Patterns to Avoid

- **Building a full CLI framework for 5 commands:** str.split + dict dispatch is sufficient. No click, no typer, no argparse inside GRAPH mode.
- **Storing GraphResult on GraphRun:** The trace is available on GraphResult which is the return value of the task coroutine. Store it on GraphRun for inspection, but keep it lightweight (reference, not copy).
- **Blocking the event loop in inspect/trace formatting:** Rich rendering can be slow for large traces. Use `_rich_to_ansi()` pattern from views.py to render to string then print.
- **Re-implementing expression evaluation:** Use `async_exec` from exec.py -- it already handles top-level await, `_` capture, and namespace registration.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Expression evaluation | Custom parser for `run graph(x=1)` | `async_exec` from exec.py | Already handles top-level await, AST transforms, namespace scoping |
| Task cancellation | Custom cancel logic | `TaskManager.revoke()` | Already handles process group kill, task state transitions |
| Formatted tables | Manual column alignment | `rich.table.Table` via `_rich_to_ansi()` | Auto-aligns, handles overflow, renders to ANSI for prompt_toolkit |
| Elapsed time formatting | Custom formatter | `f"{(end - start) / 1e9:.1f}s"` | Inline is simpler than a utility |
| Tab completion for commands | Custom completer | Extend `NamespaceCompleter` or add `GraphCompleter` | prompt_toolkit's Completer protocol handles the heavy lifting |

**Key insight:** Phase 27 is mostly wiring. The data is already captured (GraphRun, NodeTiming, trace). The execution infrastructure exists (engine, TaskManager). The display infrastructure exists (channels, views, Rich). The work is: (1) command parsing, (2) Graph API tweak, (3) rendering the data as formatted output.

## Common Pitfalls

### Pitfall 1: Coroutine Never Awaited When run <expr> Returns a Coroutine

**What goes wrong:** If `run graph.arun(x=1)` evaluates the expression and gets a coroutine, but then the handler path that handles it doesn't await or submit it, Python raises "coroutine was never awaited" RuntimeWarning.
**Why it happens:** `async_exec` returns the raw result. If it's a coroutine and no code path submits it, it gets garbage collected.
**How to avoid:** Every code path in `_cmd_run` must either submit the coroutine or explicitly close it with `coro.close()`.
**Warning signs:** RuntimeWarning in stderr, silent failures.

### Pitfall 2: GraphResult Not Stored on GraphRun for Inspect/Trace

**What goes wrong:** `inspect` and `trace` commands need the execution trace (list of Node instances). Currently `_execute()` in engine.py returns the GraphResult but doesn't store it on GraphRun.
**Why it happens:** GraphRun was designed in Phase 26 as metadata-only (state, timing). The actual trace is the return value of the asyncio.Task.
**How to avoid:** Store the GraphResult on GraphRun in `_execute()` before returning:
```python
run.result = result  # Add result field to GraphRun
```
This gives inspect/trace access to the full trace.
**Warning signs:** `inspect` command can show timing but not field values.

### Pitfall 3: _run_graph Still Called Directly in _dispatch

**What goes wrong:** Currently `_dispatch` calls `await self._run_graph(text)` for GRAPH mode. If we add command parsing, the entire text goes to the dispatcher. But if someone types just bare text (not a command), it should probably show a help message.
**Why it happens:** Phase 26 made `_run_graph` a simple "submit whatever graph is in namespace" function. Phase 27 replaces this with command dispatch.
**How to avoid:** Replace `_run_graph` entirely with `dispatch_graph` that parses commands. Unknown input gets a "try: run, list, cancel, inspect, trace" message.

### Pitfall 4: Completed Runs Not Accessible to inspect/trace

**What goes wrong:** `GraphRegistry._archive()` moves completed runs from `_runs` to `_completed` deque. But the `_completed` deque has maxlen=20. If more than 20 runs complete, older runs are evicted and can't be inspected.
**Why it happens:** Bounded deque was designed for memory safety in Phase 26.
**How to avoid:** This is acceptable behavior. Document that only the last 20 completed runs are inspectable. `registry.get()` already searches both active and completed. Keep the bounded deque.

### Pitfall 5: Namespace Expression Evaluation Side Effects

**What goes wrong:** `run <expr>` evaluates arbitrary Python. `run import os; os.system("rm -rf /")` would be catastrophic. But this is PY mode's trust model too -- Dzara is the operator.
**Why it happens:** Expression evaluation is inherently powerful.
**How to avoid:** This is by design. GRAPH mode's `run` evaluates in the same namespace as PY mode. No sandboxing needed -- same trust model.

## Code Examples

Verified patterns from the existing codebase:

### Current _run_graph (to be replaced)
```python
# shell.py lines 336-372
async def _run_graph(self, text: str) -> None:
    """GRAPH mode: graph execution via engine."""
    graph = self.namespace.get("graph")
    if not graph:
        self.router.write("graph", "(no graph in namespace)", mode="GRAPH")
        return
    try:
        run = self.engine.submit(graph, self.tm, lm=self._lm)
        # ... callback attachment ...
```

### Current GRAPH dispatch (to be replaced)
```python
# shell.py line 455-456
elif self.mode == Mode.GRAPH:
    await self._run_graph(text)
```

### async_exec Pattern (to reuse for run <expr>)
```python
# exec.py -- already supports expression evaluation with top-level await
result, captured = await async_exec(expr, shell.namespace)
# result is the expression value (coroutine, object, etc.)
# captured is stdout from print() calls
```

### Channel Output Pattern (for command handlers)
```python
# All output goes through router.write with graph channel
shell.router.write(
    "graph", content, mode="GRAPH",
    metadata={"type": "lifecycle", "run_id": run.run_id},
)
```

### Rich Table to ANSI Pattern (from views.py)
```python
from rich.table import Table
from bae.repl.views import _rich_to_ansi

table = Table(show_header=True, header_style="bold")
table.add_column("ID", style="yellow")
table.add_column("STATE")
table.add_column("ELAPSED", justify="right")
table.add_column("NODE")

for run in runs:
    elapsed = _format_elapsed(run)
    table.add_row(run.run_id, run.state.value, elapsed, run.current_node)

ansi = _rich_to_ansi(table)
print_formatted_text(ANSI(ansi))
```

### GraphRun Data Already Available
```python
# engine.py -- all this data exists
run = registry.get("g1")
run.run_id       # "g1"
run.state        # GraphState.DONE
run.started_ns   # perf_counter_ns at start
run.ended_ns     # perf_counter_ns at end
run.current_node # "RecommendOOTD"
run.node_timings # [NodeTiming(node_type="...", start_ns=..., end_ns=...)]
run.error        # "" or "TypeError: ..."
run.graph        # Graph object (has .start, .nodes, .edges)
# MISSING: run.result (GraphResult with .trace) -- needs to be added
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GRAPH mode submits namespace["graph"] with no args | GRAPH mode command dispatcher with run/list/cancel/inspect/trace | Phase 27 | Full graph management UX |
| Graph.arun(**kwargs) as opaque interface | Graph exposes typed callable signature via params property | Phase 27 | Introspectable, composable |
| No graph inspection in REPL | inspect/trace commands query GraphRun data | Phase 27 | Full observability from GRAPH mode |
| No graph cancel from GRAPH mode | cancel command revokes via TaskManager | Phase 27 | Clean lifecycle management |

**Deprecated/outdated:**
- `_run_graph()` in shell.py -- replaced by `dispatch_graph()` command dispatcher
- Bare text submission in GRAPH mode -- replaced by explicit `run <expr>` command

## Open Questions

1. **Should `run` without args submit namespace["graph"] for backwards compat?**
   - What we know: Phase 26's `_run_graph` submitted `self.namespace.get("graph")` regardless of text input. Phase 27 adds `run <expr>` syntax.
   - What's unclear: Whether `run` with no expression should default to `namespace["graph"]` or require an explicit expression.
   - Recommendation: `run` with no args could default to `run graph` (looks up `graph` in namespace). This preserves the Phase 26 UX while adding the new syntax. If `graph` isn't in namespace, show usage.

2. **Should submit_coro inject TimingLM?**
   - What we know: `engine.submit()` injects TimingLM. `submit_coro()` gets a pre-built coroutine where the LM is already bound.
   - What's unclear: Whether users care about timing when using `run graph.arun(x=1)` directly.
   - Recommendation: Accept the tradeoff. `submit()` (Graph + kwargs) gets timing. `submit_coro()` (pre-built coroutine) doesn't. For the common case (`run graph` or `run Graph(start=X)`), `submit()` is used and timing works. For the advanced case (`run graph.arun(x=val)`), timing is lost but flexibility is gained.

3. **Should GraphResult be stored on GraphRun?**
   - What we know: inspect/trace need the trace (list of Node instances). Currently only available as Task.result().
   - What's unclear: Memory implications of storing full traces on all GraphRuns in the completed deque.
   - Recommendation: Store it. The bounded deque (maxlen=20) already limits memory. Node instances are small. The alternative (reaching into Task.result()) is fragile and may not work for cancelled/failed runs.

4. **How should the trace command differ from inspect?**
   - What we know: Requirements say inspect shows "full execution trace with node timings and field values" and trace shows "node transition history."
   - Recommendation: `inspect` is detailed (field values, timing, deps). `trace` is concise (just node names + timing). Think of trace as the compact view and inspect as the deep-dive.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `bae/graph.py` (Graph class, _input_fields, arun), `bae/repl/engine.py` (GraphRegistry, GraphRun, submit, _execute), `bae/repl/shell.py` (_run_graph, _dispatch, CortexShell), `bae/repl/exec.py` (async_exec), `bae/repl/views.py` (_rich_to_ansi), `bae/repl/tasks.py` (TaskManager.revoke)
- `.planning/phases/26-engine-foundation/26-02-PLAN.md` -- engine design decisions
- `.planning/phases/26-engine-foundation/26-04-PLAN.md` -- error surfacing, kwarg fix
- `.planning/STATE.md` -- accumulated decisions, pending todos
- `.planning/ROADMAP.md` -- Phase 27 requirements and success criteria

### Secondary (MEDIUM confidence)
- Phase context from Dzara: Graph API redesign requirement (typed callable signature, loose coupling from start node)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib/existing deps, zero new packages, patterns verified in codebase
- Architecture: HIGH -- command dispatch follows existing mode patterns, engine wrapper follows Phase 26 patterns, expression evaluation reuses async_exec
- Pitfalls: HIGH -- all identified from direct code analysis of the files that will be modified, cross-referenced with Phase 26 decisions
- API redesign: MEDIUM -- the exact form of the Graph callable API depends on Dzara's feedback on the tradeoffs. The research presents the options.

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (stable domain, internal codebase patterns)
