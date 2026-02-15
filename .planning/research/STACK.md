# Technology Stack

**Project:** Concurrent Graph Execution in Cortex REPL
**Researched:** 2026-02-15

## Recommendation: Zero New Dependencies

The entire milestone -- concurrent graph execution, human-in-the-loop gates, observability, lifecycle management for 10+ concurrent instances -- can be built with Python 3.14 stdlib + existing dependencies (Rich 14.3.2, prompt-toolkit 3.0.52, Pydantic 2.12.5). No new packages needed.

Python 3.14 ships two new asyncio introspection APIs (`capture_call_graph`, `print_call_graph`) that are purpose-built for the observability requirements. Everything else uses established stdlib primitives.

---

## Recommended Stack

### Concurrent Graph Execution Engine

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `asyncio.TaskGroup` | stdlib 3.14 | Structured concurrency for parallel graph runs | Cancels siblings on failure -- when a node errors, the entire graph run aborts cleanly. Performance parity with `gather()` since 3.14. ExceptionGroup error handling surfaces all failures, not just the first. |
| `asyncio.Task` | stdlib 3.14 | Individual graph run tracking | TaskManager already wraps `asyncio.create_task()`. Graph runs become named tasks (`graph:run_id:GraphName`) tracked in existing TaskManager infrastructure. |
| `asyncio.timeout` | stdlib 3.14 | Per-graph-run timeout | Context manager that converts CancelledError to TimeoutError. Nestable. Reschedule-able via `.reschedule()` for dynamic deadline adjustment. Prevents runaway LLM calls from blocking the REPL indefinitely. |

**Integration point:** TaskManager.submit() already creates tasks with name/mode. Extend it to accept a `graph_run_id` and associate graph lifecycle metadata. Do NOT replace TaskManager -- augment it.

**Why TaskGroup over gather:** `gather()` does not cancel other tasks if one fails. When a node in a graph run raises DepError or FillError, the graph should stop immediately, not let remaining LLM calls run to completion. TaskGroup's structured concurrency enforces this.

**Why NOT separate TaskGroups per graph:** Each graph run is sequential (node A -> node B -> node C). TaskGroup is for managing multiple concurrent graph runs at the REPL level, not for parallelizing nodes within a single run. The current `arun()` loop stays sequential per-graph. Concurrency is between graphs, not within them.

### Human-in-the-Loop Input Gates

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `asyncio.Event` | stdlib 3.14 | Suspend graph execution until human responds | Textbook primitive for "wait until signaled." A gate node creates an Event, the graph runner awaits it. When the human responds, the REPL sets the Event. Zero overhead when not waiting. Thread-safe. |
| `asyncio.Queue(maxsize=1)` | stdlib 3.14 | Carry human input back to the waiting gate | Event says "go", but the gate needs the answer too. Queue(maxsize=1) carries the response value. Graph awaits `queue.get()`, REPL does `queue.put_nowait(answer)`. Single-item queue prevents stale responses. |
| `prompt_toolkit.patch_stdout` | 3.0.52 | Print gate notifications above the prompt | Already used in CortexShell.run(). Notifications from background graph tasks use `print_formatted_text()` inside the patch_stdout context -- output appears above the prompt without corrupting it. |

**Integration point:** Gate notifications go through the existing Channel/ChannelRouter system. Graph channel writes with metadata `{"type": "gate_waiting", "run_id": "...", "prompt": "..."}` surface "Graph X is waiting for input" to the user. The REPL dispatches responses via a gate registry keyed by `(run_id, gate_id)`.

**Why Event+Queue, not Condition:** `asyncio.Condition` is for notify-one/notify-all patterns with shared mutable state. Gate semantics are simpler: binary signal + single value. Event+Queue is two clear primitives composing into one clear pattern, vs Condition which bundles lock + notification into one opaque object.

**Anti-pattern -- modal dialogs:** Do NOT use `prompt_toolkit.shortcuts.input_dialog`. Modal dialogs steal focus from the REPL prompt, blocking all other work. Instead, the human types a response at the normal prompt. A command syntax (e.g. `:gate run_3 yes` or routing via GRAPH mode) delivers the answer to the waiting graph. The REPL stays interactive while graphs wait.

### Graph Observability / Metrics

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `time.perf_counter_ns()` | stdlib 3.14 | Nanosecond timing for node/dep/LM execution | Integer nanoseconds avoids floating-point drift in aggregations. Monotonic. Wrap each node step, dep call, and LM invocation with start/end timestamps. Convert to ms for display. |
| `dataclasses.dataclass` | stdlib 3.14 | Metrics collection structs (NodeMetrics, RunMetrics, DepMetrics) | Lightweight, no validation overhead. Metrics are internal bookkeeping, not user-facing models. Frozen dataclasses for immutable snapshots after a run completes. |
| `asyncio.capture_call_graph()` | stdlib 3.14 | Debug async task relationships at runtime | **NEW in 3.14.** Returns structured `FutureCallGraph` showing which tasks await which. Use for debugging stuck graphs: "Task graph:run_3 is awaiting gate:confirm_deploy". Zero instrumentation needed -- reads the runtime's own tracking. |
| `asyncio.print_call_graph()` | stdlib 3.14 | Human-readable async call graph dump | **NEW in 3.14.** Prints the full async task tree. Route output to the `debug` channel via `format_call_graph()` (returns string instead of printing). |
| Rich `Table` | 14.3.2 | Render metrics as formatted terminal tables | Already a dependency. Render NodeMetrics/RunMetrics as Rich Tables, convert to ANSI via `Console(file=StringIO())`, display through existing ViewFormatter protocol. Same pattern as UserView panels. |
| Rich `Text` | 14.3.2 | Styled inline metrics in graph channel output | Already used in views.py. Color-code timing (green < 1s, yellow < 5s, red > 5s) for per-node durations in graph output. |
| `resource.getrusage()` | stdlib | Process-level memory before/after graph runs | Already used in toolbar's `make_mem_widget()`. Snapshot RSS before and after graph runs for delta tracking. Not per-graph-run isolation (impossible without tracemalloc overhead), but sufficient for "did this run leak?" |

**Integration point:** A `RunContext` dataclass accumulates per-node timing, dep call counts, LM call counts, and error counts as the graph executes. It wraps the existing `Graph.arun()` loop -- the graph itself stays unchanged. ViewFormatter protocol renders it: UserView shows summary line, DebugView shows full per-node breakdown.

**Why capture_call_graph over manual tracking:** `capture_call_graph()` is free (3.14 builtin), returns structured data about the real async stack, and sees relationships the application code does not instrument. Manual tracking would duplicate what the runtime already knows, and would miss relationships between TaskManager tasks, gate Events, and LLM subprocess waits.

**Anti-pattern -- external tracing:** Do NOT use OpenTelemetry, Prometheus, Jaeger, or external observability. This is a local REPL for a single developer, not a distributed production system. Dataclass metrics + Rich tables are the right weight.

### Graph Lifecycle Management (10+ Concurrent Instances)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `dict[str, GraphRun]` | stdlib | Registry of active graph runs | Simple dict keyed by run_id (auto-incrementing int). GraphRun dataclass holds: Graph ref, asyncio.Task ref, RunContext (metrics), state enum, gate registry. Mirrors TaskManager's `_tasks` dict pattern. |
| `enum.Enum` | stdlib | Graph run state machine | States: `PENDING -> RUNNING -> WAITING_GATE -> RUNNING -> COMPLETED / FAILED / CANCELLED`. Extends TaskManager's TaskState concept with graph-specific `WAITING_GATE`. |
| `asyncio.Semaphore` | stdlib 3.14 | Throttle concurrent LLM calls across all graph runs | 10+ concurrent graphs each making LLM calls would overwhelm any backend. A global semaphore (e.g. `max_concurrent_lm_calls=3`) throttles LLM access without blocking the event loop. Graphs queue for LLM access, not for execution. |
| `weakref.WeakValueDictionary` | stdlib | Prevent completed graph run memory leaks | Completed GraphRun objects should be garbage-collectable after inspection. Weak references in the run registry let finished runs evict naturally. Keep last N results in a bounded `collections.deque` for post-mortem inspection. |
| `collections.deque(maxlen=N)` | stdlib | Bounded history of completed runs | Completed runs move from the active registry to a fixed-size deque. Oldest results evict when the deque is full. Prevents unbounded memory growth from many short-lived graph runs. |

**Integration point:** The graph run registry lives on CortexShell (like `_ai_sessions`). The toolbar gets a `make_graphs_widget()` showing active graph count + waiting gates. GRAPH mode input routes to the run registry for commands (`status`, `cancel run_3`, `inspect run_2`, `metrics run_1`).

**Why Semaphore for LLM, not for graphs:** Graph execution is cheap (Python dict lookups, Pydantic construction). The bottleneck is LLM calls (subprocess + API latency). Throttling graph count would artificially limit concurrency. Throttling LLM calls prevents API saturation while letting non-LLM graph work proceed freely.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Concurrency | `asyncio.TaskGroup` | `anyio.create_task_group` | Extra dependency. AnyIO adds Trio compatibility bae will never use. TaskGroup is stdlib. |
| Concurrency | `asyncio.TaskGroup` | `asyncio.gather()` | gather() does not cancel siblings on failure. Unsafe for graph runs where one error should abort the whole run. |
| Input gates | `asyncio.Event` + `Queue` | `asyncio.Condition` | Condition bundles lock + notification. Event+Queue is two orthogonal primitives -- clearer, harder to misuse. |
| Input gates | Inline prompt routing | `prompt_toolkit.input_dialog` | Modal dialogs block the entire REPL. Inline routing lets the user work while graphs wait. |
| Observability | `time.perf_counter_ns()` | `tracemalloc` for memory | tracemalloc adds ~5-10% CPU overhead. RSS delta via `resource.getrusage()` is zero-overhead and sufficient for leak detection. |
| Observability | `dataclasses` | Pydantic models for metrics | Metrics are internal. Pydantic validation is pointless for trusted internal data. Dataclasses construct faster. |
| Observability | `asyncio.capture_call_graph()` | Manual task relationship tracking | capture_call_graph is 3.14 builtin, returns structured data, sees the real async stack. Manual tracking duplicates runtime knowledge. |
| Lifecycle | `dict` registry | Redis / SQLite task queue | This is in-process. No persistence needed for running state. SessionStore handles I/O history. A task queue for 10 in-memory graphs is over-engineering. |
| Lifecycle | `asyncio.Semaphore` | Token bucket / rate limiter library | Semaphore is stdlib. We need concurrency limiting (max simultaneous), not rate limiting (requests/sec). |
| Metrics rendering | Rich Table via StringIO | Textual TUI | Textual is a full TUI framework. Cortex is a prompt_toolkit REPL. Mixing two TUI frameworks causes stdout conflicts. Rich via StringIO -> ANSI -> print_formatted_text is the proven pattern in views.py. |

---

## What NOT to Add

| Temptation | Why Resist |
|------------|-----------|
| `anyio` / `trio` | Bae is asyncio-native. AnyIO abstracts over runtimes that will never be used here. Adds complexity for zero benefit. |
| `celery` / `dramatiq` / `arq` | Distributed task queues. Bae runs in a single-process REPL. |
| `networkx` | Graph analysis library. Bae's Graph discovers topology via type hints and already has `to_mermaid()`. NetworkX would duplicate the adjacency list. |
| `opentelemetry` / `prometheus-client` | Distributed tracing for microservices. This is a local dev tool. Dataclass metrics + Rich tables cover the use case completely. |
| `textual` | Full TUI framework. Conflicts with prompt_toolkit which owns the terminal. Rich-via-StringIO is the correct rendering path. |
| `graphviz` / `matplotlib` | Heavy visualization deps. `Graph.to_mermaid()` exists. Terminal rendering via Rich is sufficient. |
| `psutil` | Process monitoring library. `resource.getrusage()` is stdlib and already used in toolbar. psutil adds a compiled C extension for information we do not need. |

---

## Existing Dependencies (Unchanged)

No version changes needed. Current installed versions are sufficient.

| Package | Installed | Required | Status |
|---------|-----------|----------|--------|
| `pydantic` | 2.12.5 | >=2.0 | OK. Node models, graph validation. |
| `prompt-toolkit` | 3.0.52 | >=3.0.50 | OK. REPL, patch_stdout, key bindings, print_formatted_text. |
| `rich` | 14.3.2 | >=14.3 | OK. Table, Panel, Syntax, Text, Console(file=StringIO()). |
| `pygments` | 2.19.2 | >=2.19 | OK. Python lexer for PY mode. |
| `typer` | (installed) | >=0.12 | OK. CLI entry point. |

**pyproject.toml: No changes.**

---

## New Stdlib Usage Summary

Everything below is Python 3.14 stdlib. Zero `pip install` commands.

```
# Concurrent execution
asyncio.TaskGroup           -- structured concurrency for multiple graph runs
asyncio.timeout             -- per-run deadline enforcement

# Human-in-the-loop gates
asyncio.Event               -- gate suspension primitive
asyncio.Queue(maxsize=1)    -- gate response delivery

# Observability
asyncio.capture_call_graph  -- task relationship introspection (NEW in 3.14)
asyncio.format_call_graph   -- string rendering of task tree (NEW in 3.14)
time.perf_counter_ns        -- nanosecond execution timing
resource.getrusage          -- RSS memory snapshots (already used)

# Lifecycle management
asyncio.Semaphore           -- LLM call concurrency throttle
weakref.WeakValueDictionary -- auto-cleanup of completed runs
collections.deque           -- bounded completed-run history
enum.Enum                   -- run state machine
dataclasses.dataclass       -- metrics structs
```

---

## Key Integration Points with Existing Architecture

### TaskManager (bae/repl/tasks.py)
- Graph runs are TaskManager tasks via `submit()`. Returns TrackedTask with graph metadata in name.
- `revoke()` cancels a graph run and its LLM subprocesses. `revoke_all()` cancels all.
- Ctrl-C task menu shows graph runs alongside AI/PY/BASH tasks -- no UI changes needed.
- TrackedTask.mode = "graph" distinguishes graph tasks from other modes.

### ChannelRouter (bae/repl/channels.py)
- All graph observability writes to the `"graph"` channel with typed metadata.
- Gate notifications: `{"type": "gate_waiting", "run_id": "...", "prompt": "..."}`.
- Node completion: `{"type": "node_complete", "run_id": "...", "node": "ClassName", "duration_ms": N}`.
- Run completion: `{"type": "run_complete", "run_id": "...", "node_count": N, "total_ms": N}`.
- All writes persist to SessionStore automatically (existing behavior).

### ViewFormatter Protocol (bae/repl/views.py)
- UserView: render graph run summaries as Rich Panels (code reuse from ai_exec panels).
- DebugView: render per-node metrics, dep timings, LM call details as raw key=value pairs.
- AISelfView: render graph events with semantic tags (graph-start, node-fill, gate-wait, etc.).
- Extend via new metadata types on existing views. No new ViewFormatter subclass needed initially.

### SessionStore (bae/repl/store.py)
- Graph run summaries persist via `store.record()` on the graph channel.
- Searchable via FTS5: `store("graph run_3")` finds all entries for that run.
- No schema changes needed -- entries table already has mode/channel/direction/content/metadata.

### ToolbarConfig (bae/repl/toolbar.py)
- `make_graphs_widget()`: shows active graph count + gates waiting. Same pattern as `make_tasks_widget()`.
- Integrates via existing `toolbar.add("graphs", make_graphs_widget(shell))`.

### Graph.arun() (bae/graph.py)
- The execution loop stays unchanged. A new `arun_observed()` wrapper (or hooks) adds timing around each step.
- RunContext passed alongside trace, not embedded in it. Graph core remains clean.
- Dep cache (`dep_cache: dict`) is per-run, already isolated. No concurrency conflict between runs.

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| asyncio.TaskGroup for concurrent runs | HIGH | Stdlib since 3.11, improved in 3.13/3.14. Verified against official 3.14.3 docs. |
| asyncio.Event + Queue for gates | HIGH | Standard concurrency primitives since Python 3.4. Well-documented, well-tested. |
| asyncio.capture_call_graph | HIGH | Verified new in 3.14 via official docs. Full API confirmed: `capture_call_graph()`, `format_call_graph()`, `print_call_graph()`. |
| prompt_toolkit patch_stdout compatibility | HIGH | Already in production in CortexShell.run(). Background task output works correctly. |
| Rich via StringIO for metrics rendering | HIGH | Proven pattern in views.py and channels.py. No architecture changes needed. |
| asyncio.Semaphore for LLM throttling | MEDIUM | Correct primitive. Optimal `max_concurrent_lm_calls` value needs empirical tuning with Claude CLI backend latency characteristics. |
| time.perf_counter_ns for metrics | HIGH | Stdlib since 3.7. Monotonic, integer nanoseconds, zero overhead. |
| Zero new dependencies | HIGH | All four feature areas map to stdlib + existing deps. Verified against pyproject.toml and installed packages. |

---

## Sources

### Official Documentation (HIGH confidence)
- [Python 3.14 What's New](https://docs.python.org/3/whatsnew/3.14.html) -- asyncio TaskGroup changes, introspection APIs
- [asyncio Call Graph Introspection](https://docs.python.org/3/library/asyncio-graph.html) -- capture_call_graph, format_call_graph, print_call_graph API
- [asyncio Coroutines and Tasks](https://docs.python.org/3/library/asyncio-task.html) -- TaskGroup, timeout, create_task signatures
- [prompt_toolkit 3.0.52 docs](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/reference.html) -- patch_stdout, print_formatted_text, create_background_task
- [prompt_toolkit asyncio integration](https://python-prompt-toolkit.readthedocs.io/en/master/pages/advanced_topics/asyncio.html)
- [Rich Live Display docs](https://rich.readthedocs.io/en/stable/live.html) -- confirmed NOT suitable (conflicts with prompt_toolkit stdout)
- [Rich Tables docs](https://rich.readthedocs.io/en/stable/tables.html) -- Table API for metrics rendering
- [Python time module](https://docs.python.org/3/library/time.html#time.perf_counter_ns) -- perf_counter_ns specification

### Verified Against Installed Packages
- Rich 14.3.2, prompt-toolkit 3.0.52, Pydantic 2.12.5, Pygments 2.19.2 -- all verified via `uv pip list`
- Python 3.14 -- confirmed via pyproject.toml `requires-python = ">=3.14"`
