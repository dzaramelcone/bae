# Phase 26: Engine Foundation - Research

**Researched:** 2026-02-15
**Domain:** Concurrent graph execution engine with lifecycle tracking, integrated into async REPL
**Confidence:** HIGH

## Summary

Phase 26 builds the foundation for running bae graphs as managed concurrent tasks inside cortex. The core work is: (1) a GraphRegistry that tracks running graph instances by ID with lifecycle states, (2) an engine wrapper around `Graph.arun()` that emits lifecycle events and captures per-node timing without modifying the framework layer, (3) a `dep_cache` parameter on `Graph.arun()` for cortex injection, and (4) TaskManager integration so graphs appear in the Ctrl-C menu.

This phase does NOT include GRAPH mode commands, input gates, or observability views -- those are Phase 27-29. Phase 26 delivers the plumbing: Dzara submits a graph from PY mode (e.g. `tm.submit(engine.run_graph(graph, text="hello"), name="graph:g1", mode="graph")`), it runs in the background, she sees it in Ctrl-C, and timing/lifecycle data is captured for later phases to display.

The entire phase uses Python 3.14 stdlib (`asyncio`, `time.perf_counter_ns`, `dataclasses`, `enum`) plus existing dependencies. Zero new packages. The existing TaskManager already handles task lifecycle, cancellation, and Ctrl-C menu display. The engine wraps `Graph.arun()` as a coroutine submitted via `TaskManager.submit()`.

**Primary recommendation:** Build a thin engine layer (`bae/repl/engine.py`) containing GraphRegistry, GraphRun dataclass, and NodeTiming metrics. The engine wraps `Graph.arun()` by intercepting node transitions via a timing-instrumented dep_cache and lifecycle callbacks. Keep `Graph.arun()` clean -- add only the `dep_cache` parameter (one-line additive change). All engine logic lives outside the framework layer.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio.Task` | stdlib 3.14 | Each graph run is an asyncio task via TaskManager.submit() | Already the pattern for NL/PY/BASH mode tasks in shell.py |
| `time.perf_counter_ns` | stdlib 3.14 | Nanosecond timing for per-node start/end and dep durations | Monotonic, integer, zero overhead. Standard for instrumentation. |
| `dataclasses` | stdlib 3.14 | GraphRun, NodeTiming, RunMetrics structs | Lightweight, no validation needed for internal bookkeeping |
| `enum.Enum` | stdlib 3.14 | GraphState lifecycle states | Same pattern as TaskState in tasks.py |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `asyncio.sleep(0)` | stdlib 3.14 | Yield to event loop between graph iterations | Insert at top of arun() loop to prevent event loop starvation |
| `collections.deque` | stdlib 3.14 | Bounded history of completed graph runs | Archive completed runs to prevent memory leaks |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Wrapper engine approach | Modifying Graph.arun() directly | Wrapper keeps framework clean, testable independently. Direct modification couples runtime to REPL. |
| dict-based registry | WeakValueDictionary | WeakRef complicates inspection of running graphs. Plain dict + explicit cleanup is simpler and fits the TaskManager pattern. |
| Separate TaskGroup per engine | TaskManager.submit() | TaskManager already handles what we need (submit, cancel, list active, Ctrl-C menu). TaskGroup would be a parallel system. |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Recommended Project Structure

```
bae/repl/engine.py     # NEW: GraphRegistry, GraphRun, engine wrapper
bae/graph.py           # MODIFIED: add dep_cache param to arun()
```

### Pattern 1: Engine as Wrapper, Not Modification

**What:** The engine wraps `Graph.arun()` in an async function that captures timing and emits lifecycle events. `Graph.arun()` itself gains only one additive parameter (`dep_cache`). All instrumentation lives in the engine layer.

**When to use:** Always -- this is the core pattern for the entire phase.

**Why:** `Graph.arun()` is the framework API. Cortex-specific concerns (registry, timing, channels) must not leak into it. The engine is a cortex integration layer, not a framework feature.

**Example:**
```python
# bae/repl/engine.py
import time
from dataclasses import dataclass, field

@dataclass
class NodeTiming:
    node_type: str
    start_ns: int
    end_ns: int = 0
    dep_duration_ns: int = 0

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1_000_000

@dataclass
class GraphRun:
    run_id: str
    graph: Graph
    state: GraphState = GraphState.RUNNING
    node_timings: list[NodeTiming] = field(default_factory=list)
    current_node: str = ""
    started_ns: int = field(default_factory=time.perf_counter_ns)
    ended_ns: int = 0

class GraphRegistry:
    def __init__(self):
        self._runs: dict[str, GraphRun] = {}
        self._next_id: int = 1
        self._completed: deque[GraphRun] = deque(maxlen=20)

    def submit(self, graph: Graph, tm: TaskManager, **kwargs) -> GraphRun:
        run_id = f"g{self._next_id}"
        self._next_id += 1
        run = GraphRun(run_id=run_id, graph=graph)
        self._runs[run_id] = run
        coro = self._execute(run, **kwargs)
        tt = tm.submit(coro, name=f"graph:{run_id}:{graph.start.__name__}", mode="graph")
        return run

    async def _execute(self, run: GraphRun, **kwargs) -> GraphResult:
        try:
            result = await run.graph.arun(dep_cache=run.dep_cache, **kwargs)
            run.state = GraphState.DONE
            return result
        except asyncio.CancelledError:
            run.state = GraphState.CANCELLED
            raise
        except Exception:
            run.state = GraphState.FAILED
            raise
        finally:
            run.ended_ns = time.perf_counter_ns()
            self._archive(run)
```

### Pattern 2: dep_cache Injection for External Resources

**What:** `Graph.arun()` accepts an optional `dep_cache` dict that seeds the resolver's per-run cache. Pre-seeded entries bypass dep function calls entirely -- the resolver finds them already cached and returns them directly.

**When to use:** When cortex (or tests) need to inject graph-scoped resources (prompt implementations, timing hooks, etc.) without modifying node code or dep functions.

**Why:** The resolver already checks `dep_cache[fn]` before calling `fn`. Pre-seeding the cache is the natural extension. This is concurrent-safe because each graph run gets its own dep_cache (local variable in `arun()`, line 308 of graph.py).

**Example:**
```python
# In graph.py, the change is minimal:
async def arun(self, *, lm=None, max_iters=10, dep_cache=None, **kwargs):
    # ... existing validation ...
    cache: dict = {LM_KEY: lm}
    if dep_cache:
        cache.update(dep_cache)
    # ... rest unchanged, uses 'cache' as before ...
```

### Pattern 3: Lifecycle State Machine

**What:** Each GraphRun has a state that transitions through a defined set: RUNNING -> DONE | FAILED | CANCELLED. Phase 26 does not include WAITING (that's Phase 28 input gates).

**When to use:** Tracking what each graph is doing at any point.

**Why:** The registry needs to distinguish active from completed runs for listing, cleanup, and TaskManager integration. The state machine matches TaskManager's TaskState but adds graph-specific granularity.

```python
class GraphState(enum.Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

Note: WAITING is deferred to Phase 28. The state enum should be designed to accept it later, but Phase 26 only needs the four above.

### Pattern 4: Per-Node Timing via arun() Hooks

**What:** The engine captures start/end timestamps for each node by wrapping the graph execution. Two approaches:

**Approach A -- Post-hoc from trace:** After `arun()` returns, the trace contains all visited nodes. The engine can't get per-node timing this way because `arun()` is a black box.

**Approach B -- Timing wrapper around arun() loop (recommended):** Instrument timing by wrapping the dep resolution and LM calls. The engine submits a coroutine that:
1. Calls `graph.arun()` with a custom dep_cache
2. Uses a timing-aware LM wrapper that records fill/choose_type durations
3. After completion, the trace + timing data are both available

The cleanest approach is a **timing LM wrapper**: a thin LM-protocol-conforming object that delegates to the real LM but records call durations.

```python
class TimingLM:
    """LM wrapper that records call durations for engine instrumentation."""

    def __init__(self, inner: LM, run: GraphRun):
        self._inner = inner
        self._run = run

    async def fill(self, target, resolved, instruction, source=None):
        start = time.perf_counter_ns()
        result = await self._inner.fill(target, resolved, instruction, source)
        elapsed = time.perf_counter_ns() - start
        self._run.node_timings.append(
            NodeTiming(node_type=target.__name__, start_ns=start, end_ns=start + elapsed)
        )
        return result

    async def choose_type(self, types, context):
        return await self._inner.choose_type(types, context)

    async def make(self, node, target):
        return await self._inner.make(node, target)

    async def decide(self, node):
        return await self._inner.decide(node)
```

This captures timing for every LM call (which is the dominant cost per node) without modifying `Graph.arun()` or the node code.

### Anti-Patterns to Avoid

- **Modifying Graph.arun() loop for timing:** The framework layer should not know about cortex timing. Use wrappers, not modifications.
- **Global mutable state for registry:** Each engine instance owns its registry. Don't use module-level singletons.
- **Coupling GraphRun to TaskManager internals:** GraphRun tracks its own state. TaskManager tracks its own TaskState. The mapping between them is in the engine layer, not in either data structure.
- **Adding WAITING state in Phase 26:** WAITING is for input gates (Phase 28). Adding it now adds untested state transitions. Keep the state machine minimal.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Task lifecycle (submit, cancel, list) | Custom task tracker | TaskManager.submit() | Already handles asyncio.Task wrapping, cancellation, active listing, Ctrl-C menu. Graph runs are just tasks with mode="graph". |
| Concurrent execution | Thread pool, multiprocessing | asyncio.create_task via TaskManager | Graphs are I/O-bound (LM calls). asyncio handles this naturally. Threading adds complexity for zero benefit. |
| Event loop yielding | Custom scheduler | `await asyncio.sleep(0)` | Stdlib one-liner. Yields to event loop between graph iterations. |
| Process cleanup on cancel | Manual subprocess tracking | `try/except CancelledError: process.kill()` in LM backend | The fix goes in `_run_cli_json`, not the engine. Engine just needs to propagate CancelledError. |

**Key insight:** Phase 26 is integration, not invention. Every primitive already exists in the codebase or stdlib. The work is wiring them together correctly.

## Common Pitfalls

### Pitfall 1: Event Loop Starvation from Graph Iteration Loop

**What goes wrong:** `Graph.arun()` runs a tight `while current is not None` loop. Between `await` points (LM calls), synchronous work (Pydantic construction, type hint inspection, dep cache lookups) can block the event loop for milliseconds. With multiple graphs, this compounds.

**Why it happens:** Dep cache hits are synchronous (no await). Routing strategy determination is synchronous. Node construction is synchronous. Only LM calls yield.

**How to avoid:** Add `await asyncio.sleep(0)` at the top of the `while` loop in `Graph.arun()`. This is the one modification to `arun()` beyond `dep_cache` -- it yields to the event loop on every iteration. Cost: negligible (one event loop tick per node).

**Warning signs:** Toolbar stops updating while a graph runs. REPL feels sluggish.

### Pitfall 2: Subprocess Orphans on Graph Cancellation

**What goes wrong:** `tm.revoke(task_id)` cancels the asyncio Task, but Claude CLI subprocesses spawned by `_run_cli_json` keep running. The CancelledError interrupts `process.communicate()` but doesn't kill the process.

**Why it happens:** `_run_cli_json` (lm.py:386-391) only catches `TimeoutError`, not `CancelledError`.

**How to avoid:** Fix `_run_cli_json` to handle both:
```python
except (asyncio.TimeoutError, asyncio.CancelledError):
    process.kill()
    await process.wait()
    raise
```

**Warning signs:** After cancelling a graph, `ps aux | grep claude` shows orphaned processes.

### Pitfall 3: dep_cache Parameter Breaking Existing Call Sites

**What goes wrong:** If `dep_cache` is added as a positional parameter or if existing callers pass unexpected kwargs, tests break.

**Why it happens:** Careless signature change.

**How to avoid:** `dep_cache` MUST be keyword-only (already is, since it follows `*`), with default `None`. Existing callers pass `lm=`, `max_iters=`, and `**kwargs` -- none conflict. The merge `cache.update(dep_cache)` must handle `None` gracefully (skip the update).

**Warning signs:** Any existing test failing after the change.

### Pitfall 4: Memory Leak from Retained GraphRun Objects

**What goes wrong:** Completed GraphRun objects hold references to the full trace (list of Node instances with resolved deps and LM data). Without cleanup, memory grows unboundedly across many graph runs.

**Why it happens:** Registry keeps all runs forever.

**How to avoid:** Use `collections.deque(maxlen=N)` for completed runs. When a run completes, move it from `_runs` to `_completed`. The deque evicts the oldest automatically.

**Warning signs:** RSS (toolbar mem widget) grows monotonically across multiple graph runs.

### Pitfall 5: TimingLM Not Conforming to LM Protocol

**What goes wrong:** If TimingLM doesn't exactly match the LM protocol signature, type checking or runtime dispatch breaks.

**Why it happens:** LM is a Protocol class. The wrapper must implement all four methods with matching signatures.

**How to avoid:** TimingLM delegates all four methods (`make`, `decide`, `choose_type`, `fill`) to the inner LM. Test that `isinstance(timing_lm, LM)` passes at runtime (LM is `@runtime_checkable`).

**Warning signs:** `TypeError` or `NotImplementedError` during graph execution with TimingLM.

## Code Examples

Verified patterns from the existing codebase:

### How TaskManager.submit() Works (Existing Pattern)

```python
# From shell.py line 431-432 -- NL mode submits to TaskManager
self.tm.submit(
    self._run_nl(prompt), name=f"ai:{self._active_session}:{prompt[:30]}", mode="nl"
)

# From tasks.py line 35-41 -- submit creates asyncio.Task
def submit(self, coro, *, name: str, mode: str) -> TrackedTask:
    task = asyncio.create_task(coro, name=name)
    tt = TrackedTask(task=task, name=name, mode=mode, task_id=self._next_id)
    self._tasks[self._next_id] = tt
    self._next_id += 1
    task.add_done_callback(self._on_done)
    return tt
```

Graph runs follow the identical pattern: `tm.submit(engine_coro, name="graph:g1:StartNode", mode="graph")`.

### How dep_cache Is Used (Existing Pattern)

```python
# From graph.py line 308 -- dep_cache is a local dict, seeded with LM
dep_cache: dict = {LM_KEY: lm}

# From resolver.py line 455 -- resolver checks cache before calling dep
to_resolve = [fn for fn in ready if fn not in dep_cache]
# ^^ If fn is already in dep_cache, it's skipped entirely

# From resolver.py line 459 -- results cached for reuse
for fn, result in zip(to_resolve, results):
    dep_cache[fn] = result
```

The engine pre-seeds dep_cache: `{LM_KEY: timing_lm, get_prompt: cortex_prompt}`. The resolver finds both already cached and never calls the original functions.

### How Ctrl-C Menu Shows Tasks (Existing Pattern)

```python
# From shell.py line 96-98 -- task menu shows active tasks
active = shell.tm.active()
for i, tt in enumerate(active, start=1):
    line = FormattedText([
        ("bold fg:ansiyellow", f"  {i}"),
        ("", f" {tt.name}"),
    ])
```

Graph tasks with `name="graph:g1:NewProject"` appear here automatically. No changes to the Ctrl-C menu code needed.

### arun() dep_cache Change (The One Framework Change)

```python
# graph.py -- the ONLY change to the framework layer
async def arun(
    self, *, lm: LM | None = None, max_iters: int = 10,
    dep_cache: dict | None = None, **kwargs
) -> GraphResult:
    # ... existing validation ...

    if lm is None:
        from bae.lm import ClaudeCLIBackend
        lm = ClaudeCLIBackend()

    trace: list[Node] = []
    cache: dict = {LM_KEY: lm}
    if dep_cache is not None:
        cache.update(dep_cache)
    current: Node | None = start_node
    iters = 0

    while current is not None:
        await asyncio.sleep(0)  # yield to event loop (Pitfall 1)
        # ... rest unchanged, uses 'cache' instead of 'dep_cache' ...
```

The local variable rename from `dep_cache` to `cache` avoids shadowing the parameter. All existing references to the local dict work unchanged.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `channel_arun()` in shell.py | Engine wrapper with registry | Phase 26 | channel_arun is a thin logger wrapper. Engine adds lifecycle, timing, registry. channel_arun stays for backward compat but engine supersedes it for managed runs. |
| No dep_cache param on arun() | dep_cache param on arun() | Phase 26 | Unlocks external resource injection. Backward compatible (default None). |
| Graph mode stub (`_run_graph` does nothing useful) | Engine submits graphs as managed tasks | Phase 26 | Foundation for Phase 27 command interface |

**Deprecated/outdated:**
- `channel_arun()` will be superseded by engine-managed runs for cortex use. It remains as a simple utility for non-cortex callers.

## Open Questions

1. **Should TimingLM wrap all four LM methods or just fill/choose_type?**
   - What we know: The v2 graph loop (ellipsis-body nodes) uses `choose_type` + `fill`. Custom `__call__` nodes use `make`/`decide` (v1 methods). Both paths need timing.
   - What's unclear: Whether wrapping `make`/`decide` adds noise (they're called from custom __call__, which the engine can't time without modifying the node).
   - Recommendation: Wrap all four. Timing data is always useful. Let Phase 29 decide what to display.

2. **Should GraphRegistry live on CortexShell or be standalone?**
   - What we know: It needs access to TaskManager for submit/revoke and LM for graph execution.
   - What's unclear: Whether Phase 27 GRAPH mode dispatch needs the registry on shell or can receive it as a parameter.
   - Recommendation: Standalone class instantiated in CortexShell.__init__(), stored as `self.engine` (or `self.graphs`). Same pattern as `self.tm`, `self.router`, `self.store`.

3. **Should the sleep(0) go in Graph.arun() or in the engine wrapper?**
   - What we know: sleep(0) in arun() benefits ALL callers (CLI, tests, cortex). In the wrapper, it only benefits cortex.
   - What's unclear: Whether non-cortex callers (CLI `bae run`) benefit from the yield, or whether it adds negligible overhead they don't need.
   - Recommendation: Put it in `Graph.arun()`. The overhead is negligible (one event loop tick per iteration). It's defensive programming -- any caller benefits from not starving the event loop.

4. **What should the internal dep_cache variable be renamed to?**
   - What we know: The current local variable in arun() is named `dep_cache` (line 308). The new parameter is also `dep_cache`. Shadowing is confusing.
   - Recommendation: Rename the internal variable. Options: `cache`, `run_cache`, `_cache`. `cache` is simplest, matches resolver naming conventions.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `bae/graph.py` (arun loop, dep_cache usage), `bae/resolver.py` (cache check pattern), `bae/repl/tasks.py` (TaskManager API), `bae/repl/shell.py` (task submission pattern, Ctrl-C menu), `bae/lm.py` (LM Protocol, _run_cli_json CancelledError gap)
- `bae/work/prompt.py` (Prompt protocol, dep injection via get_prompt, PromptDep)
- `.planning/research/SUMMARY.md`, `ARCHITECTURE.md`, `PITFALLS.md`, `STACK.md` -- v6.0 milestone research (2026-02-15)
- `.planning/REQUIREMENTS.md` -- ENG-01 through ENG-05, INT-01 requirement definitions
- `.planning/ROADMAP.md` -- Phase 26 success criteria and scope definition
- Python 3.14 stdlib docs: asyncio tasks, time.perf_counter_ns

### Secondary (MEDIUM confidence)
- LangGraph / Prefect / Temporal patterns from v6.0 research -- informed registry and lifecycle design

### Tertiary (LOW confidence)
- None -- all findings grounded in codebase analysis and stdlib docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, zero new deps, verified against existing codebase patterns
- Architecture: HIGH -- engine wrapper pattern directly mirrors existing TaskManager/channel_arun patterns in the codebase. dep_cache injection traced through resolver.py code path.
- Pitfalls: HIGH -- all five pitfalls identified from direct code analysis (specific line numbers in graph.py, lm.py, tasks.py). Mitigations verified against existing codebase patterns.

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (stable domain, stdlib only)
