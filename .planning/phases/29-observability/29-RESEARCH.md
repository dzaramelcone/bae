# Phase 29: Observability - Research

**Researched:** 2026-02-15
**Domain:** Graph execution observability via channel/view system, lifecycle events, timing metrics, memory profiling, concurrent execution validation
**Confidence:** HIGH

## Summary

Phase 29 surfaces the graph execution data that already exists (or can be cheaply collected) in the engine layer through the existing channel/view/store infrastructure. The foundation is solid: `GraphRegistry` already tracks lifecycle states (RUNNING/WAITING/DONE/FAILED/CANCELLED), `TimingLM` already records per-node fill durations, `ChannelRouter` already supports typed metadata on writes, `SessionStore` already persists entries with FTS5 search, and `ViewFormatter` protocol already supports view-specific rendering. The work is connecting these pieces and adding the missing metrics.

Three areas require new code: (1) emitting structured graph events into the `[graph]` channel during execution with typed metadata so views can render them appropriately, (2) collecting dep-level timing and memory metrics that `TimingLM` doesn't currently capture, and (3) a per-graph output policy controlling which events are emitted at what verbosity level. The `asyncio.capture_call_graph()` API is confirmed available in Python 3.14.3 and works for introspecting stuck tasks. The concurrent stress test (10+ graphs) validates existing `asyncio.sleep(0)` yielding in `arun()` and bounded `deque(maxlen=20)` archival.

No new dependencies required. All stdlib: `resource`, `tracemalloc`, `asyncio.graph`, `time`, `dataclasses`.

**Primary recommendation:** Instrument `GraphRegistry._execute` and `_wrap_coro` to emit structured events through a `ChannelRouter.write("graph", ...)` callback, extending the existing `notify` callback pattern. Add dep timing to the resolver, memory snapshots around graph runs, and a `GraphOutputPolicy` enum controlling verbosity. Wire events into `SessionStore` via the existing `Channel.store` integration. Add `asyncio.capture_call_graph()` as a GRAPH mode `debug <id>` command.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio.graph` | stdlib 3.14 | `capture_call_graph()` / `format_call_graph()` for stuck-task debugging | New in 3.14, confirmed working in 3.14.3 |
| `tracemalloc` | stdlib 3.14 | RSS delta per graph run via `take_snapshot()` + `compare_to()` | Standard Python memory profiling; per-allocation tracking |
| `resource` | stdlib 3.14 | `getrusage(RUSAGE_SELF).ru_maxrss` for high-water RSS | Already used in `toolbar.py:make_mem_widget()` |
| `time.perf_counter_ns` | stdlib 3.14 | Nanosecond-precision monotonic timing | Already used in `engine.py:TimingLM` and `GraphRun` |
| `dataclasses` | stdlib 3.14 | Event structs, metrics containers | Already used for `GraphRun`, `NodeTiming`, `InputGate` |
| `enum.Enum` | stdlib 3.14 | Output policy levels | Already used for `GraphState`, `ViewMode`, `Mode` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rich.table.Table` | existing dep | Formatted output for debug/inspect commands | Already used in `_cmd_list`, `_cmd_inspect` |
| `prompt_toolkit` | existing dep | Terminal rendering via `print_formatted_text` | Already used everywhere in views/channels |
| `pydantic` | existing dep | None -- no new Pydantic models needed for observability | N/A |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tracemalloc` snapshots | `resource.ru_maxrss` delta only | `ru_maxrss` is high-water mark on macOS (never decreases). `tracemalloc` gives accurate per-run allocation deltas. Use both: RSS for overall, tracemalloc for per-run. |
| Structured event dataclasses | Free-form dict metadata | Dataclasses give type safety and IDE completion, but the existing metadata pattern is `dict`. Use typed constants for event types, keep `dict` for metadata to match existing `Channel.write()` API. |
| OpenTelemetry spans | stdlib timing | OpenTelemetry adds a dependency and complexity. The requirements say "zero new dependencies." stdlib timing is sufficient for the scale. |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Recommended Changes

```
bae/repl/engine.py      # MODIFIED: event emission, dep timing, memory metrics, output policy
bae/repl/graph_commands.py  # MODIFIED: debug command, enhanced inspect, persist events
bae/repl/views.py       # MODIFIED: UserView/DebugView graph event rendering
bae/repl/shell.py       # MODIFIED: wire event callback, store integration
bae/repl/channels.py    # UNCHANGED (already supports typed metadata)
bae/repl/store.py       # UNCHANGED (already persists via Channel.store)
bae/graph.py            # UNCHANGED
bae/resolver.py          # UNCHANGED (or: minor timing hooks around dep resolution)
```

### Pattern 1: Event Emission via Notify Callback

**What:** Extend the existing `notify` callback (currently only used for gate creation) to emit all graph lifecycle events. The engine calls `notify(event_type, content, metadata)` at each lifecycle transition. The shell wires `notify` to `router.write("graph", ...)`.

**When to use:** For all lifecycle events: start, node-transition, gate-waiting, complete, fail, cancel.

**Why:** The `notify` callback pattern already exists in `GraphRegistry.submit()` and `_make_gate_hook()`. Extending it keeps the engine decoupled from the channel system. The engine emits events; the shell decides how to display them.

**Example:**
```python
# In engine.py -- extend _execute to emit structured events
async def _execute(self, run, *, lm=None, notify=None, **kwargs):
    _emit = notify or (lambda *a, **kw: None)
    _emit("lifecycle", f"{run.run_id} started", {
        "type": "lifecycle", "event": "start", "run_id": run.run_id,
        "graph": run.graph.start.__name__ if run.graph else "unknown",
    })
    try:
        # ... existing execution ...
        _emit("lifecycle", f"{run.run_id} done ({elapsed:.1f}s)", {
            "type": "lifecycle", "event": "complete", "run_id": run.run_id,
            "elapsed_ms": elapsed_ms,
        })
    except Exception as e:
        _emit("lifecycle", f"{run.run_id} failed: {run.error}", {
            "type": "lifecycle", "event": "fail", "run_id": run.run_id,
            "error": str(e),
        })
        raise

# In shell.py or graph_commands.py -- wire notify to channel
def _make_event_notify(shell, policy):
    def notify(event_type, content, metadata):
        if policy.should_emit(event_type):
            shell.router.write("graph", content, mode="GRAPH", metadata=metadata)
    return notify
```

### Pattern 2: Dep Timing via Resolver Instrumentation

**What:** Currently `TimingLM` only times `fill()` and `make()` (LM calls). Dep function durations are invisible. To capture dep timing, wrap `_resolve_one()` or instrument the gather loop in `resolve_fields()`.

**When to use:** OBS-03 requires "dep durations" in debug view.

**Why:** Dep functions can be I/O-bound (database queries, API calls, file reads). Knowing which dep is slow helps Dzara debug graph performance.

**Implementation approach:** Add timing around the `asyncio.gather()` in `resolve_fields()`. Two options:
- **Option A:** Modify `_resolve_one()` to return `(result, duration_ns)` -- requires changing `resolve_fields` to unpack tuples.
- **Option B:** Record timing in the dep_cache via a wrapper -- keep `_resolve_one` clean, wrap at the gather site.
- **Option C (recommended):** Add a timing callback to the dep_cache (like GATE_HOOK_KEY) that the engine provides. When present, `resolve_fields` calls it for each dep resolved.

```python
# Option C: timing hook in dep_cache
DEP_TIMING_KEY = object()  # sentinel in resolver.py

# In resolve_fields, after resolving a dep:
timing_hook = dep_cache.get(DEP_TIMING_KEY)
if timing_hook:
    timing_hook(fn_name, duration_ns)
```

### Pattern 3: Memory Metrics via tracemalloc Snapshots

**What:** Capture RSS delta per graph run using `tracemalloc.take_snapshot()` before and after execution. Store the delta in `GraphRun`.

**When to use:** OBS-04 requires "RSS delta per graph run."

**Why:** `resource.ru_maxrss` is a high-water mark (on macOS it never decreases). `tracemalloc` gives per-allocation tracking, so we can compute accurate deltas. However, `tracemalloc` has overhead (~10% CPU, significant memory for snapshot storage). For production use, capture only start/end RSS via `resource` and offer tracemalloc as opt-in debug mode.

**Example:**
```python
# In engine.py -- memory snapshot around execution
import resource, sys

def _get_rss_bytes():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024

# In _execute:
rss_before = _get_rss_bytes()
result = await run.graph.arun(...)
rss_after = _get_rss_bytes()
run.rss_delta_bytes = rss_after - rss_before
```

### Pattern 4: Per-Graph Output Policy

**What:** An enum controlling which events flow through the channel for a given graph run. Levels: `verbose` (all events including per-node transitions), `normal` (start/complete/fail/gate), `quiet` (fail/gate only), `silent` (nothing).

**When to use:** OBS-06 requires per-graph verbosity control.

**Why:** When running 10+ concurrent graphs, `verbose` would flood the channel. `normal` is the default for interactive use. `quiet`/`silent` for batch/automated scenarios.

**Example:**
```python
class OutputPolicy(enum.Enum):
    VERBOSE = "verbose"    # all: start, transition, dep-timing, complete, fail, gate
    NORMAL = "normal"      # lifecycle: start, complete, fail, gate
    QUIET = "quiet"        # errors only: fail, gate
    SILENT = "silent"      # nothing

    def should_emit(self, event: str) -> bool:
        if self == OutputPolicy.SILENT:
            return False
        if self == OutputPolicy.QUIET:
            return event in ("fail", "gate", "error")
        if self == OutputPolicy.NORMAL:
            return event in ("start", "complete", "fail", "gate", "error")
        return True  # VERBOSE
```

### Pattern 5: asyncio.capture_call_graph() as Debug Command

**What:** A `debug <id>` command in GRAPH mode that calls `asyncio.capture_call_graph()` on the asyncio.Task associated with a running graph and displays the formatted result.

**When to use:** OBS-05 -- when a graph appears stuck (RUNNING but not progressing).

**Why:** `capture_call_graph()` shows exactly where the coroutine is suspended (which `await` point). This tells Dzara whether the graph is stuck on an LM call, a dep function, a gate, or something unexpected.

**Example:**
```python
async def _cmd_debug(arg, shell):
    """Show async call graph for a running graph's task."""
    run = shell.engine.get(arg.strip())
    if run is None or run.state not in (GraphState.RUNNING, GraphState.WAITING):
        shell.router.write("graph", f"{arg}: not running", mode="GRAPH")
        return
    # Find the asyncio.Task
    for tt in shell.tm.active():
        if tt.name.startswith(f"graph:{run.run_id}:"):
            formatted = asyncio.format_call_graph(tt.task)
            shell.router.write("graph", formatted, mode="GRAPH",
                             metadata={"type": "debug", "run_id": run.run_id})
            return
    shell.router.write("graph", f"{arg}: task not found", mode="GRAPH")
```

### Pattern 6: Store Persistence for Graph Events

**What:** Graph events persist to SessionStore automatically because they flow through `Channel.write()`, which already calls `self.store.record()` when a store is attached. The `[graph]` channel is registered with `store=self.store` in `CortexShell.__init__()`.

**When to use:** INT-02 -- cross-session history of graph events.

**Why:** No new persistence code needed. The existing `Channel -> SessionStore` pipeline handles it. All graph events written via `router.write("graph", ...)` are automatically persisted with timestamp, mode, channel, direction, content, and metadata JSON.

**Verification:** After a graph completes, `store.search("lifecycle")` or `store.session_entries()` should return the graph events. The `metadata` column stores the typed event dict as JSON.

### Anti-Patterns to Avoid

- **Modifying Graph.arun() for observability hooks:** The framework layer must stay clean. All instrumentation goes through the engine wrapper (dep_cache injection, TimingLM wrapping, callback functions).
- **Emitting events synchronously from the event loop:** Event emission must not block. `router.write()` is synchronous but fast (string formatting + SQLite insert). For 10+ concurrent graphs, the SQLite WAL mode handles concurrent writes, but if serialization becomes a bottleneck, batch events.
- **Using tracemalloc always-on:** `tracemalloc` has ~10% CPU overhead and significant memory for snapshots. Use `resource.ru_maxrss` by default; offer tracemalloc as opt-in via a flag.
- **Unbounded event buffering:** The `Channel._buffer` grows without bound. For long-running or many-graph scenarios, consider whether this matters (the deque(maxlen=20) on completed runs already bounds the main leak).
- **Putting observability logic in views:** Views only render. The engine/commands layer decides what to emit. Views format it. Keep the separation clean.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async call graph inspection | Custom coroutine walker | `asyncio.capture_call_graph()` / `format_call_graph()` | Stdlib since 3.14, handles all edge cases (nested tasks, futures, TaskGroups) |
| Memory profiling | Manual RSS tracking | `resource.getrusage()` + `tracemalloc` | Both stdlib, well-tested, handle platform differences |
| Event persistence | Custom event store / separate DB table | Existing `Channel.store -> SessionStore.record()` pipeline | Already wired, already indexed, already FTS5 searchable |
| Concurrent task introspection | Custom task registry | `asyncio.Task` name matching + `TaskManager.active()` | Already the pattern in `_attach_done_callback` and `_cmd_cancel` |

**Key insight:** Phase 29 is mostly wiring -- connecting data that already exists (or can be cheaply collected) to display surfaces that already exist. The channel/view/store pipeline is the observability backbone; the engine just needs to emit into it.

## Common Pitfalls

### Pitfall 1: Channel Flooding from Verbose Concurrent Graphs

**What goes wrong:** 10 concurrent graphs each emitting per-node transition events produce a torrent of `[graph]` channel writes that overwhelm the terminal display and SQLite inserts.

**Why it happens:** No rate limiting or verbosity control on graph event emission.

**How to avoid:** Implement `OutputPolicy` (OBS-06) as a gate on event emission. Default to `NORMAL` (lifecycle events only). Per-node transitions only in `VERBOSE` mode. The policy check happens before `router.write()`, so quiet/silent graphs produce zero channel I/O.

**Warning signs:** Terminal feels laggy with multiple graphs. SQLite WAL grows large. `store.session_entries()` returns thousands of entries.

### Pitfall 2: tracemalloc Overhead in Production

**What goes wrong:** Enabling `tracemalloc` for RSS delta measurement adds ~10% CPU overhead and stores per-allocation metadata that itself consumes significant memory.

**Why it happens:** `tracemalloc.start()` instruments every Python allocation.

**How to avoid:** Use `resource.getrusage().ru_maxrss` by default (zero overhead, measures high-water mark). Offer `tracemalloc` as an opt-in debug command (e.g., `profile <id>`) that starts tracing only for a specific graph run. Note: `ru_maxrss` on macOS is high-water and never decreases, so deltas may be zero or inaccurate for small allocations. For the OBS-04 requirement, `ru_maxrss` before/after is sufficient for detecting large leaks.

**Warning signs:** Unexpectedly high RSS from tracemalloc bookkeeping itself.

### Pitfall 3: Event Loop Starvation from SQLite Writes

**What goes wrong:** `SessionStore.record()` is synchronous (SQLite commit per write). With 10+ graphs emitting events, the synchronous commits could block the event loop.

**Why it happens:** `self._conn.execute()` and `self._conn.commit()` in `SessionStore.record()` are blocking I/O.

**How to avoid:** SQLite WAL mode is already enabled (`PRAGMA journal_mode=WAL`), which allows concurrent reads and reduces write contention. For 10+ graphs producing lifecycle events (a few writes per graph per second), this is fine. If performance becomes an issue, batch writes or move to `aiosqlite`. But for Phase 29 scale, existing sync SQLite is sufficient.

**Warning signs:** `asyncio` event loop slow warnings. Task scheduling latency increases.

### Pitfall 4: Missing Task Reference for capture_call_graph

**What goes wrong:** `_cmd_debug` needs the `asyncio.Task` object to call `capture_call_graph(task)`. The engine's `GraphRun` doesn't store a reference to the task -- it's created in `TaskManager.submit()` and returned as `TrackedTask`.

**Why it happens:** The current wiring: `registry.submit() -> tm.submit() -> asyncio.create_task()`. The Task is stored in `TrackedTask.task`, but the engine never stores a reference to the `TrackedTask`.

**How to avoid:** Use the existing pattern from `_attach_done_callback` and `_cmd_cancel`: iterate `shell.tm.active()` and match by `tt.name.startswith(f"graph:{run.run_id}:")`. The task name contains the run_id, so lookup is straightforward. No need to store the task reference on GraphRun.

**Warning signs:** `_cmd_debug` can't find the task for a running graph.

### Pitfall 5: DebugView Not Handling New Graph Event Types

**What goes wrong:** New metadata types (e.g., `"event": "transition"`, `"event": "complete"`) render as raw key=value in DebugView but are not specially formatted. UserView may not handle them at all.

**Why it happens:** Views are metadata-type-driven. New types need handling in each view's `render()` method.

**How to avoid:** Design the metadata schema for graph events upfront. DebugView already handles arbitrary metadata (renders key=value pairs), so it works by default. UserView needs explicit handling for graph event types if they should render differently from the default prefix display. At minimum: lifecycle events should render with a distinguishing prefix (e.g., `[graph:g1]` with run_id in the label).

**Warning signs:** Graph events render identically to plain writes in UserView.

### Pitfall 6: Dep Timing Hook Changing Resolver Behavior

**What goes wrong:** Adding timing instrumentation to `resolve_fields()` introduces a performance regression or changes the resolution order.

**Why it happens:** Wrapping `_resolve_one()` calls or adding timing around `asyncio.gather()` could inadvertently serialize parallel deps or add overhead.

**How to avoid:** Keep the timing hook non-invasive. Measure elapsed time around the existing `gather()` call for the batch, then attribute durations per-dep post-hoc. Or record wall-clock start/end per dep in the cache alongside the result. Do NOT change the parallel resolution structure.

**Warning signs:** Dep resolution takes longer with timing enabled. Parallel deps run sequentially.

## Code Examples

### Existing Event Emission Pattern (Already Works)

```python
# From graph_commands.py:82-85 -- lifecycle event on submit
shell.router.write(
    "graph", f"submitted {run.run_id}", mode="GRAPH",
    metadata={"type": "lifecycle", "run_id": run.run_id},
)

# From graph_commands.py:93-108 -- done callback pattern
def _on_done(task, _run=run):
    if task.cancelled():
        shell.router.write(
            "graph", f"{_run.run_id} cancelled", mode="GRAPH",
            metadata={"type": "lifecycle", "run_id": _run.run_id},
        )
    elif task.exception() is not None:
        shell.router.write(
            "graph", f"{_run.run_id} failed: {_run.error}", mode="GRAPH",
            metadata={"type": "error", "run_id": _run.run_id},
        )
    else:
        shell.router.write(
            "graph", f"{_run.run_id} done", mode="GRAPH",
            metadata={"type": "lifecycle", "run_id": _run.run_id},
        )
```

### Existing Store Integration (Already Wired)

```python
# From shell.py:229-235 -- channels registered with store
self.store = SessionStore(Path.cwd() / ".bae" / "store.db")
self.router = ChannelRouter()
for name, cfg in CHANNEL_DEFAULTS.items():
    self.router.register(
        name, cfg["color"], store=self.store, markdown=cfg.get("markdown", False)
    )

# From channels.py:90-93 -- write auto-persists via store
if self.store:
    self.store.record(
        mode or self.name.upper(), self.name, direction, content, metadata,
    )
```

Graph events written via `router.write("graph", ...)` are ALREADY persisted. INT-02 is partially satisfied by existing wiring. What's needed: ensure events have rich enough metadata to be useful when reviewing past sessions.

### asyncio.capture_call_graph() Usage (Verified in 3.14.3)

```python
import asyncio

async def debug_stuck_task(task):
    graph = asyncio.capture_call_graph(task)
    if graph is None:
        return "No call graph available"

    # Structured access
    for entry in graph.call_stack:
        frame = entry.frame
        print(f"  {frame.f_code.co_name} at {frame.f_code.co_filename}:{frame.f_lineno}")

    # Or use the formatted string version
    return asyncio.format_call_graph(task)
```

### Memory Measurement (Verified)

```python
import resource, sys

def get_rss_bytes():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024

# Before graph run
rss_before = get_rss_bytes()
# ... run graph ...
rss_after = get_rss_bytes()
delta_mb = (rss_after - rss_before) / (1024 * 1024)
```

### Existing DebugView Renders Arbitrary Metadata

```python
# From views.py:181-196 -- DebugView already handles any metadata dict
def render(self, channel_name, color, content, *, metadata=None):
    meta = metadata or {}
    meta_str = " ".join(f"{k}={v}" for k, v in sorted(meta.items()))
    header = f"[{channel_name}] {meta_str}" if meta_str else f"[{channel_name}]"
    print_formatted_text(FormattedText([(f"{color} bold", header)]))
    for line in content.splitlines():
        print_formatted_text(FormattedText([
            ("fg:#808080", "  "),
            ("", line),
        ]))
```

Any new metadata keys we add to graph events will automatically render in DebugView. UserView needs explicit handling for enhanced display.

### Existing Graph Metadata Types

The `[graph]` channel currently uses these metadata types:

| type | Where | Contains |
|------|-------|----------|
| `lifecycle` | graph_commands.py | `run_id`, submit/done/cancelled events |
| `error` | graph_commands.py | `run_id`, failure messages |
| `gate` | graph_commands.py | gate schema notification |
| `ansi` | graph_commands.py | Rich-rendered tables (list, inspect) |
| `log` | shell.py (channel_arun) | bae.graph logger output |
| `result` | shell.py (channel_arun) | terminal node repr |

Phase 29 extends this with:

| type | New | Contains |
|------|-----|----------|
| `lifecycle` | extended | `event` field: start/complete/fail/transition/cancel |
| `transition` | new | `run_id`, `from_node`, `to_node`, `fill_ms` |
| `timing` | new | `run_id`, `node_type`, `fill_ms`, `dep_ms` |
| `memory` | new | `run_id`, `rss_delta_bytes` |
| `debug` | new | `run_id`, formatted call graph |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `channel_arun()` wraps graph with logger | Engine emits lifecycle via done_callback | Phase 26-28 | Engine is the observability point, not a wrapper function |
| No per-node timing | `TimingLM` wraps fill/make calls | Phase 26 | Node-level timing exists but only for LM calls |
| No dep timing | (not yet captured) | Phase 29 | Dep resolution timing is invisible |
| No memory metrics | `make_mem_widget()` shows total RSS | Phase 19 | Per-graph memory delta not tracked |
| No stuck-graph debugging | (not available before 3.14) | Phase 29 | `asyncio.capture_call_graph()` enables this |
| No output verbosity control | All events emitted always | Phase 29 | `OutputPolicy` gates emission |

**Deprecated/outdated:**
- `channel_arun()` in shell.py: superseded by engine-managed runs. Still exists as a utility but not the primary path.

## Open Questions

1. **Should dep timing modify resolver.py or stay entirely in the engine?**
   - What we know: `resolve_fields()` is framework code. Adding timing hooks changes its interface. But dep timing is most accurately captured at the resolve site.
   - What's unclear: Whether a timing callback sentinel (like `GATE_HOOK_KEY`) is acceptable coupling, or whether timing should be derived from wall-clock measurements around `arun()` + LM timing subtraction.
   - Recommendation: Use a timing callback sentinel (`DEP_TIMING_KEY`) in the dep_cache, matching the established `GATE_HOOK_KEY` pattern. This is minimal coupling (one `if` check) and gives accurate per-dep timing.

2. **Should per-node transition events go through notify or through a separate event stream?**
   - What we know: The existing `notify` callback is a simple `(msg: str) -> None` callable. Extending it to `(event_type, content, metadata)` changes its signature.
   - What's unclear: Whether callers of `submit()` who use `notify` for gate-only notifications would break.
   - Recommendation: Evolve `notify` to accept `(content: str, metadata: dict | None = None)`. This is backward-compatible if existing callers only receive string args. Or keep `notify` for gates and add a separate `on_event` callback for structured events.

3. **How should UserView render graph lifecycle events?**
   - What we know: UserView currently has no graph-specific rendering. Graph events fall through to `_render_prefixed()` which shows `[graph] content`.
   - What's unclear: Whether lifecycle events should render as Rich panels, simple prefixed lines, or something else.
   - Recommendation: Keep it simple. Lifecycle events render as `[graph:g1] started`, `[graph:g1] done (2.3s)`, `[graph:g1] failed: RuntimeError: ...`. The `run_id` goes in the label metadata so the channel renders `[graph:g1]` prefix. This already works via the existing `metadata.label` support in `Channel._display()`.

4. **Should OutputPolicy be per-graph or per-session?**
   - What we know: The requirement says "per-graph output policy." This means different graphs in the same session can have different verbosity.
   - What's unclear: Where the policy is stored and how it's set (submit-time kwarg? per-run attribute? GRAPH mode command?).
   - Recommendation: Set at submit time (`run <expr> --verbose` or `engine.submit(..., policy=OutputPolicy.VERBOSE)`). Store on `GraphRun`. Default `NORMAL`. The `_make_event_notify` closure captures the policy and checks it before emitting.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `bae/repl/engine.py` (GraphRegistry, TimingLM, GraphRun, InputGate, lifecycle tracking), `bae/repl/channels.py` (Channel, ChannelRouter, ViewFormatter protocol, store integration), `bae/repl/views.py` (UserView, DebugView, AISelfView, ViewMode), `bae/repl/store.py` (SessionStore, SQLite schema, record/search/session_entries), `bae/repl/graph_commands.py` (dispatch_graph, existing commands, metadata types), `bae/repl/shell.py` (CortexShell wiring, channel_arun, done_callback pattern), `bae/repl/toolbar.py` (make_mem_widget pattern), `bae/graph.py` (arun loop, dep_cache), `bae/resolver.py` (resolve_fields, dep DAG, GATE_HOOK_KEY pattern)
- [Python 3.14 asyncio call graph introspection docs](https://docs.python.org/3.14/library/asyncio-graph.html) -- `capture_call_graph()`, `format_call_graph()`, `FutureCallGraph` dataclass
- Verified Python 3.14.3 runtime: `asyncio.capture_call_graph()` confirmed working, `resource.getrusage()` confirmed, `tracemalloc` confirmed
- Phase 26 research: engine wrapper pattern, TimingLM design, dep_cache injection
- Phase 28 verification: gate hook pattern, WAITING state, notify callback

### Secondary (MEDIUM confidence)
- None -- all findings from direct code analysis and stdlib docs

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, zero new deps, every API verified in runtime
- Architecture: HIGH -- all patterns extend existing codebase patterns (notify callback, dep_cache sentinel, Channel.write metadata, SessionStore auto-persist)
- Pitfalls: HIGH -- all identified from direct code analysis and concurrency reasoning. SQLite WAL, tracemalloc overhead, and channel flooding are well-documented behaviors.

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (stable domain, stdlib only)
