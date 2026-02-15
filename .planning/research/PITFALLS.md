# Domain Pitfalls

**Domain:** Concurrent async graph execution engine added to existing prompt_toolkit REPL (cortex)
**Researched:** 2026-02-15
**Confidence:** HIGH -- based on direct codebase analysis, verified prompt_toolkit/asyncio behavior, documented CPython issues

---

## Critical Pitfalls

Mistakes that cause deadlocks, data loss, or require architectural rewrites.

---

### Pitfall 1: Input Gate Deadlock -- Graph Awaits User Who Is Awaiting Prompt

**What goes wrong:** A graph running as a background task hits an input gate (e.g., `PromptDep.ask()`) and awaits user input. But the user is interacting with cortex's `prompt_async()` loop, which is also awaiting input on the same event loop. Both are blocked waiting for input from the same terminal. Neither can proceed. The graph hangs forever.

**Why it happens:** The current `TerminalPrompt` (prompt.py:43-62) calls `loop.run_in_executor(None, input, ...)` which blocks a thread pool thread waiting for stdin. Meanwhile, prompt_toolkit's `prompt_async()` (shell.py:448) is also reading from stdin via its own input mechanism. These compete for the same file descriptor. Even if `run_in_executor` technically uses a separate thread, the underlying `input()` call and prompt_toolkit's input reader both consume from fd 0. The result is unpredictable: either the graph's `input()` steals characters meant for the prompt, or the prompt steals the graph's input, or both hang.

With 10+ concurrent graphs, this becomes combinatorial: any of them could hit an input gate simultaneously, each waiting on stdin. Only one can "win." The rest deadlock or receive garbled input.

**Consequences:** Complete REPL freeze. The user sees a prompt but cannot type. Ctrl-C may not work because the event loop is not blocked (it's awaiting), but the terminal's stdin is contended. Force-kill is the only recovery.

**Prevention:**
1. Input gates MUST NOT use `input()` or any direct stdin reader. They must go through cortex's own input system.
2. Design an input gate protocol: graph sets an `asyncio.Event` and registers a notification. The REPL shows a notification (via channel/toolbar). The user explicitly responds. The graph's Event is set with the response.
3. One input at a time: use an `asyncio.Queue` or `asyncio.Lock` to serialize input gate requests across all graphs. When graph A needs input, it enqueues its request. The REPL processes the queue FIFO. Other graphs continue executing non-input nodes.
4. The `PromptDep` must have a cortex-aware implementation that routes through the notification system, not through `TerminalPrompt`. `TerminalPrompt` should only be used for standalone (non-REPL) graph execution.
5. Add a timeout on every input gate wait: `asyncio.wait_for(gate_event.wait(), timeout=300)`. If the user never responds, the graph should cancel gracefully, not hang forever.

**Detection:** Any graph that calls `await prompt.ask(...)` inside cortex freezes the REPL. Test by running a `new_project` graph in graph mode and checking whether the REPL remains responsive at the first input gate.

**Phase relevance:** This is the FIRST thing to solve. Input gates touch the event loop, the REPL, and graph execution simultaneously. Everything else depends on this working.

---

### Pitfall 2: Graph Task Leaks on Cancellation -- Subprocess Orphans from LM Calls

**What goes wrong:** Cancelling a graph task via `tm.revoke()` cancels the Python `asyncio.Task`, but the Claude CLI subprocess spawned by `ClaudeCLIBackend._run_cli_json()` keeps running. The `asyncio.create_subprocess_exec` process is not killed when its parent task is cancelled. The subprocess continues consuming resources, holding open file descriptors, and potentially completing an LM call whose result is never consumed.

**Why it happens:** The current TaskManager (tasks.py:50-57) calls `tt.task.cancel()` and kills the registered process. But graph tasks do not register their LM subprocesses with the TaskManager. The registration mechanism (`tm.register_process()`, tasks.py:44-48) requires `asyncio.current_task()` to match -- but graph execution happens inside `graph.arun()` which spawns LM calls internally. The LM backend creates subprocesses (lm.py:380-384) that are local to `_run_cli_json` and have no reference outside that scope.

When `task.cancel()` fires, it raises `CancelledError` at the next `await` point. If the task is currently inside `process.communicate()` (lm.py:386-388), the `CancelledError` interrupts the await, but the process is not killed. The `try/except asyncio.TimeoutError` block (lm.py:389-391) only handles timeout, not cancellation.

With 10+ concurrent graphs, each making multiple LM calls, a bulk `revoke_all()` can leave dozens of orphaned `claude` processes running.

**Consequences:** Orphaned `claude` CLI processes consume memory and API quota. On macOS, `ulimit` exhaustion from accumulated zombie processes. The user's API bill increases for work whose results are thrown away.

**Prevention:**
1. `_run_cli_json` must handle `CancelledError` and kill the process:
```python
try:
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        process.communicate(), timeout=self.timeout
    )
except (asyncio.TimeoutError, asyncio.CancelledError):
    process.kill()
    await process.wait()
    raise
```
2. Graph execution (`graph.arun`) should wrap the main loop in a `try/finally` that tracks and cleans up any in-flight subprocesses.
3. The graph registry (new system) should track which processes belong to which graph, so `revoke_graph(graph_id)` can kill all associated processes.
4. Consider adding `process.kill()` to the `__del__` or an `atexit` handler as a safety net, though structured cleanup is the primary mechanism.

**Detection:** After cancelling a graph, run `ps aux | grep claude` and check for orphaned processes. In tests, mock `create_subprocess_exec` and verify that `process.kill()` is called on `CancelledError`.

**Phase relevance:** Must be solved when implementing graph lifecycle management. Every graph that makes LM calls is affected.

---

### Pitfall 3: Event Loop Starvation from Synchronous Graph Operations

**What goes wrong:** The graph execution loop in `graph.arun()` (graph.py:312-427) runs a `while current is not None` loop that performs dep resolution, LM calls, and effect execution sequentially. While each individual operation is `async`, the overall structure is a tight loop that yields to the event loop only at `await` points. If dep resolution involves many synchronous Pydantic validations, type hint inspections, or cached dep lookups (resolver.py:449-465), the loop can run for extended periods without yielding. This starves prompt_toolkit's UI refresh, making the REPL unresponsive.

**Why it happens:** Pydantic's `model_construct()`, `model_validate()`, `get_type_hints()`, and `classify_fields()` are all synchronous CPU-bound operations. They complete in microseconds individually, but a graph with many nodes, each with many fields, can accumulate milliseconds of unbroken synchronous work between `await` points. Prompt_toolkit refreshes the UI (toolbar, prompt redraw) on event loop ticks. If the loop is occupied by synchronous graph work, the UI freezes.

The dep cache (resolver.py:449-465) makes this worse after warmup: cached deps return immediately (no await), so the resolved fields are built synchronously, the node is constructed synchronously, routing strategy is determined synchronously, and only the LM call finally yields. For nodes with no LM call (custom `__call__` returning a pre-constructed node), the entire iteration is synchronous.

**Consequences:** The toolbar stops updating (task count stale, memory stale). The prompt becomes unresponsive. The user perceives the REPL as frozen even though work is happening. With 10+ graphs, the starvation compounds -- each graph's synchronous segments compete for the same event loop.

**Prevention:**
1. Insert `await asyncio.sleep(0)` at the top of each graph iteration (after `while current is not None`). This yields to the event loop, allowing prompt_toolkit to process UI events. Cost: negligible (one event loop tick per graph iteration).
2. For the graph registry, consider running each graph's `arun()` as a separate `asyncio.Task` (already planned via TaskManager.submit). This ensures the event loop schedules between graphs. But the `sleep(0)` is still needed WITHIN each graph to yield between iterations.
3. Do NOT use `run_in_executor` to offload graph execution to a thread pool. This breaks the asyncio concurrency model: dep resolution uses `asyncio.gather()` for parallel deps, which requires being on the event loop. Threading adds complexity for no benefit since the bottleneck is LM calls (I/O bound), not CPU.

**Detection:** While a graph is running, check if the toolbar's memory widget updates (it reads `resource.getrusage()` on each render, toolbar.py:101-108). If it freezes, the event loop is starved. More precisely: add a heartbeat task that logs timestamps every 100ms. If gaps exceed 500ms during graph execution, there's starvation.

**Phase relevance:** Must be addressed when integrating `graph.arun()` with the TaskManager. Simple fix but critical for UX.

---

### Pitfall 4: Channel Flooding from Concurrent Graph Output

**What goes wrong:** With 10+ concurrent graphs, each emitting output through `ChannelRouter.write()`, the terminal fills with interleaved output from different graphs. Channel writes are synchronous and immediate (channels.py:81-96) -- each `write()` calls `_display()` which calls `print_formatted_text()`. Ten graphs producing output simultaneously means ten interlaced streams of `[graph]` prefixed text, making the output unreadable.

**Why it happens:** The channel system was designed for one active context at a time (one AI conversation, one bash command, one graph). The `[channel_name]` prefix differentiates streams, but with `[graph] result from graph 1` interleaved with `[graph] debug from graph 3` and `[graph] error from graph 7`, the user cannot follow any single graph's output.

Worse: each `print_formatted_text()` call redraws the prompt line (this is how patch_stdout works -- it erases the prompt, prints above it, redraws the prompt). With high-frequency output from many graphs, this causes visible flickering and performance degradation as the terminal processes dozens of redraws per second.

**Consequences:** Output is unreadable. Terminal flickers. Performance degrades. The user cannot determine which graph produced which output. The debug view (DebugView, views.py:170-187) compounds the problem by adding metadata headers to every line.

**Prevention:**
1. Each graph MUST write to a labeled sub-channel: `router.write("graph", content, metadata={"label": graph_id})`. The existing `metadata["label"]` support (channels.py:83-84, views.py:153-154) already renders `[graph:proj-1]` style prefixes. This is already built.
2. Add a configurable output policy per graph: `"visible"` (default), `"quiet"` (only errors), `"silent"` (nothing until complete). Let users choose which graphs produce live output.
3. Buffer graph output and flush on completion. Instead of immediate `print_formatted_text()`, accumulate output in a list and render a summary when the graph reaches a terminal node. This eliminates interleaving entirely.
4. Rate-limit channel writes: if more than N writes per second hit the same channel, batch them into a single `print_formatted_text()` call with newline-joined content. This reduces prompt redraws.
5. The `[graph]` channel registration should happen per-graph, not as a single shared channel. `router.register(f"graph:{graph_id}", color)` gives each graph its own visibility toggle via the existing Ctrl+O channel toggle (channels.py:203-217).

**Detection:** Run 5+ graphs simultaneously (even mock ones that just emit output). If the terminal becomes unreadable or noticeably flickers, flooding is occurring.

**Phase relevance:** Must be solved in the graph I/O integration phase. Channel infrastructure already supports labels; this is about using them correctly and adding rate limiting.

---

## Moderate Pitfalls

---

### Pitfall 5: asyncio.Event Race in Input Gate Notification

**What goes wrong:** The input gate uses `asyncio.Event` for graph-to-REPL communication. Graph sets up an Event, registers a notification, and calls `event.wait()`. The REPL eventually calls `event.set()` with the user's response. But if the REPL calls `event.set()` before the graph reaches `event.wait()`, the event is already set when wait is called, so it returns immediately. This is correct. The race condition is the opposite: if TWO graphs need input simultaneously and the REPL uses `event.set()` followed by `event.clear()` to reset for the next request, there is a window where a third graph calling `event.wait()` sees the event as set from the previous graph's response.

**Why it happens:** `asyncio.Event.clear()` after `event.set()` has a documented race condition with multiple waiters ([Trio issue #637](https://github.com/python-trio/trio/issues/637)). The sequence `set(); clear()` can wake some waiters but not others, or wake waiters who should not have been woken. In single-threaded asyncio this is less severe than in multi-threaded code, but with many concurrent graphs all potentially waiting on input, the timing becomes fragile.

**Prevention:**
1. Do NOT use a shared Event for multiple graphs. Each input gate request gets its own `asyncio.Event` instance.
2. Use a request/response pattern: graph creates an `InputRequest(event, question, graph_id)` and puts it in an `asyncio.Queue`. The REPL pops from the queue, presents the question, and sets the specific request's event. No clearing, no sharing.
3. The response value should be attached to the request object, not passed through a separate channel. `request.response = user_text; request.event.set()` -- the graph reads `request.response` after `await request.event.wait()`.
4. Do NOT use `Event.clear()` at all. Create fresh Events for each interaction. Events are cheap.

**Detection:** Unit test: two graphs both requesting input simultaneously. Assert that each receives its own response, not the other's. Hard to reproduce in manual testing because the timing window is narrow.

---

### Pitfall 6: Memory Leak from Completed Graph State Retention

**What goes wrong:** The graph registry tracks running graphs. When a graph completes, its `GraphResult` (result.py) contains the full execution trace -- a list of every `Node` instance visited. Each node holds resolved dep values, Recall references to other nodes, and any data the LM produced. For a long-running graph with many iterations, this trace can be substantial. If the registry keeps completed graphs (for inspection, re-running, etc.) without explicit cleanup, memory grows unboundedly.

**Why it happens:** The `dep_cache` (graph.py:308) accumulates resolved dependencies across the entire run. The `trace` list (graph.py:307) grows by one node per iteration. Nodes hold references to other nodes via Recall (resolver.py:67-111), creating a reference web that prevents garbage collection of individual nodes even if they are no longer needed for execution.

In the current single-graph model this is fine -- the graph runs, returns a `GraphResult`, and the caller decides what to keep. But in a registry managing 10+ graphs over a long session, completed graphs pile up. Each `GraphResult.trace` is a list of node instances holding LM-generated content (potentially large strings) and dep function results.

The `SessionStore` (store.py) compounds this: every channel write from every graph is persisted to SQLite. The `MAX_CONTENT` limit (10,000 chars, store.py:13) prevents individual entries from being huge, but the sheer volume from many graphs can grow the database significantly.

**Prevention:**
1. The graph registry should distinguish `running`, `completed`, and `archived` states. `completed` graphs keep the `GraphResult`. `archived` graphs drop the trace and keep only the terminal node + metadata.
2. Implement a `max_completed` limit on the registry. When exceeded, the oldest completed graph is archived (trace dropped). Default: 10.
3. The `dep_cache` should be scoped to the graph run and not referenced after completion. When `arun()` returns, the dep_cache should be eligible for GC. This already works in the current code (dep_cache is a local variable in `arun()`), but the registry must not accidentally capture it in a closure or store it.
4. For the SessionStore, add a `max_session_entries` setting that auto-prunes old entries. WAL mode already handles concurrent reads during pruning.
5. Consider making `GraphResult.trace` a weakref-based structure for nodes that aren't the terminal, so intermediate nodes can be GC'd if memory pressure increases.

**Detection:** Monitor RSS (already visible via toolbar mem widget, toolbar.py:101-108) during a session with many graph completions. If RSS only grows and never shrinks, completed graphs are leaking.

---

### Pitfall 7: SessionStore Contention from Concurrent Graph Writes

**What goes wrong:** The `SessionStore` uses synchronous `sqlite3.connect()` (store.py:59) with commits on every `record()` call (store.py:89). With 10+ concurrent graphs all routing output through channels, and each channel write calling `store.record()`, the synchronous SQLite commits serialize all graph output. Each `commit()` flushes to disk (even with WAL mode). Under high concurrency, this becomes a bottleneck: the event loop blocks on each `commit()`, and graphs effectively serialize at the database layer.

**Why it happens:** SQLite's WAL mode allows concurrent readers but only one writer at a time. The `sqlite3` module's default `check_same_thread=True` prevents multi-threaded access, but that is not the issue here -- all access is from the same thread (the event loop thread). The issue is that `conn.execute()` + `conn.commit()` are synchronous I/O operations that block the event loop. With WAL, `commit()` is fast (append to WAL file), but still involves a filesystem `fsync` that can take milliseconds. At 100 writes/second from 10 concurrent graphs, that is 100ms of event loop blocking per second.

**Consequences:** The event loop blocks for cumulative milliseconds on each graph iteration's channel writes. Prompt_toolkit UI refresh is delayed. Other graphs' LM calls are delayed from starting because the event loop cannot schedule them while blocked on `commit()`.

**Prevention:**
1. Batch commits: instead of committing on every `record()`, accumulate writes and commit periodically (every 100ms or every N writes). This reduces the number of `fsync` calls.
2. Use `conn.execute("PRAGMA synchronous=NORMAL")` instead of the default `FULL`. With WAL mode, `NORMAL` is safe against data loss from process crash (only loses data on OS crash, which is acceptable for REPL session logs).
3. Move store writes to a background thread via `run_in_executor`. This unblocks the event loop but requires `check_same_thread=False` on the connection and careful serialization of access.
4. Alternatively, use `aiosqlite` which wraps sqlite3 in a dedicated thread, providing an async API. However, this is a significant change to an existing working system -- batch commits are simpler.
5. The simplest fix: remove the per-write `commit()` and rely on periodic auto-commit or explicit flush. SQLite in WAL mode will not lose data on normal Python exit because `conn.close()` (store.py:160) flushes.

**Detection:** Add timing instrumentation around `store.record()`. If individual calls exceed 1ms or cumulative time per second exceeds 50ms, contention is significant.

---

### Pitfall 8: Graph Cancellation During Dep Resolution Leaves Inconsistent State

**What goes wrong:** If a graph task is cancelled while `resolve_fields()` (resolver.py:402-478) is running `asyncio.gather()` for parallel deps, some deps complete and are cached while others are cancelled. The `dep_cache` is now partially populated. If the graph is restarted or retried, the cached deps from the previous attempt are stale or inconsistent with the new run's context.

**Why it happens:** `asyncio.gather()` (resolver.py:458) fires all deps at the same level concurrently. When `CancelledError` propagates, `gather()` cancels remaining tasks, but completed tasks have already written to `dep_cache`. The cache is a mutable dict shared across the entire graph run (graph.py:308).

For deps that have side effects (e.g., `PromptDep` which prompts the user, or deps that make API calls), partial completion means some side effects fired and others did not. The system is in an inconsistent state.

**Consequences:** Retrying a graph after cancellation may produce incorrect results because the dep cache contains values from the previous attempt. Side-effecting deps may fire twice (once in the cancelled run, once in the retry). User-facing prompts may re-ask questions the user already answered.

**Prevention:**
1. Each graph run MUST use a fresh `dep_cache`. The current code already does this (dep_cache is initialized as a local in `arun()`, graph.py:308). The graph registry must ensure retries create a new cache, not reuse the old one.
2. For side-effecting deps, wrap them in an idempotency guard: check if the side effect already happened (e.g., "was this question already answered in this run?") before executing.
3. For the PromptDep specifically: if the graph is cancelled while awaiting user input, the input gate should be dismissed (notification cleared, Event cancelled). The user should not see stale input requests from cancelled graphs.
4. Document that `dep_cache` is per-run, not per-graph. A graph instance can be run multiple times; each run gets its own cache.

**Detection:** Cancel a graph mid-execution, then re-run it. If behavior differs from a fresh run (e.g., skips prompts, uses stale data), the cache or side effects were not properly isolated.

---

### Pitfall 9: print_formatted_text() Interleaving from Concurrent Channel Writes

**What goes wrong:** Multiple graphs writing to channels simultaneously call `print_formatted_text()` concurrently. Each call involves: erase current prompt line, print the new content above, redraw the prompt line. If two calls interleave at the terminal level, the output is garbled: one call erases the prompt, the other prints its content where the prompt was, then the first redraws the prompt on top of the second's content.

**Why it happens:** `print_formatted_text()` within `patch_stdout()` is [documented as not thread-safe](https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html). In asyncio's single-threaded model, true interleaving of two synchronous calls cannot happen (the GIL and event loop guarantee sequential execution within a single thread). However, if any code uses `run_in_executor` to offload work to a thread and that thread calls `print_formatted_text()`, interleaving DOES happen.

The more insidious issue: multi-line output. A channel write with 50 lines calls `print_formatted_text()` 50 times (channels.py:119-125, one per line). Between any two of those calls, the event loop could schedule another task (if there is a yield point). In practice, synchronous for-loops do not yield, so this is safe. But if the loop is ever changed to `async for` or if an `await` is inserted between lines, interleaving becomes possible.

**Consequences:** Garbled terminal output. Lines from different graphs appear mid-line of other graphs' output. The prompt line appears in wrong positions. Terminal state becomes corrupted requiring `clear`.

**Prevention:**
1. Consolidate multi-line output into a single `print_formatted_text()` call. Instead of iterating lines and calling print per line, join them into a single `FormattedText` list and call once. This is a small change to `Channel._display()`.
2. Never call `print_formatted_text()` from a thread (via `run_in_executor`). If threaded work needs to produce output, it should put the content in an `asyncio.Queue` and let the event loop thread do the actual printing.
3. The view formatter contract should require returning a complete renderable, not making multiple print calls. The formatter produces a single ANSI string or FormattedText, and the channel makes one print call.
4. If interleaving is observed despite single-threaded execution, add a reentrant lock around the print path. But this should not be needed if rule #2 is followed.

**Detection:** Run two graphs that produce multi-line output simultaneously. If lines from one graph appear inside another graph's output block, interleaving is occurring.

---

### Pitfall 10: Toolbar Polling Cost Scales with Graph Count

**What goes wrong:** The toolbar refreshes every 1 second (shell.py:258, `refresh_interval=1.0`). The tasks widget (toolbar.py:76-85) calls `shell.tm.active()` which iterates all tracked tasks and filters by `TaskState.RUNNING`. With 10+ graphs, each potentially spawning sub-tasks (LM calls, dep resolutions), the task list grows. The `active()` method (tasks.py:63-67) creates a new sorted list on every call. With hundreds of tracked tasks (10 graphs x multiple LM calls each), this list creation and sort happens every second.

More importantly, the task dict (`_tasks`, tasks.py:32) never shrinks. Completed tasks remain in the dict forever (tasks.py:75-84 updates state but never removes). After a long session with many graph runs, `_tasks` contains thousands of entries, and `active()` must filter all of them to find the running ones.

**Consequences:** Gradual performance degradation over long sessions. The toolbar render (every 1 second) takes longer and longer as the completed task list grows. This is a slow leak, not a sudden failure -- noticeable after hours of use.

**Prevention:**
1. Prune completed tasks from `_tasks` after a retention period. Add a `_prune()` method that removes tasks in `SUCCESS`, `FAILURE`, or `REVOKED` state that are older than N minutes.
2. Call `_prune()` inside `active()` or on a periodic schedule (e.g., every 60 seconds).
3. Alternatively, maintain a separate `_active` set that is updated in `submit()` and `_on_done()`. This makes `active()` O(1) instead of O(n) over all tasks.
4. For the graph registry specifically: track graph-level task IDs, not individual sub-task IDs. The toolbar shows "3 graphs running", not "47 tasks running." Sub-task tracking is internal to each graph.

**Detection:** After running 50+ graphs over a session, check if toolbar rendering latency increases. Profile `tm.active()` call duration over time.

---

## Minor Pitfalls

---

### Pitfall 11: dep_cache Sharing Between Concurrent Graphs on Same Type

**What goes wrong:** If two graphs of the same type run concurrently and share a dep function (e.g., both use `get_prompt()` which returns the global `_prompt` singleton), the dep_cache isolates them (each has its own dict). But the underlying dep function returns the SAME object. If that object has mutable state (e.g., a conversation history or accumulated context), concurrent graphs mutate the same state.

**Prevention:** Dep functions that return mutable state must be graph-scoped, not global. The dep_cache isolation only prevents redundant calls within a single graph run -- it does not clone the returned value. If `get_prompt()` returns a stateful `Prompt` implementation, each graph needs its own instance. Either make dep functions return new instances, or add a graph-scoped context to the dep resolution system.

### Pitfall 12: Graph Trace Holds Strong References to All Nodes

**What goes wrong:** The trace list in `graph.arun()` (graph.py:307) holds strong references to every visited node. Nodes hold strong references to resolved deps (including potentially large data from LM responses). For a graph that loops many times (e.g., iterative refinement), the trace grows without bound until `max_iters` is hit. A graph with `max_iters=100` and nodes containing 10KB of LM output each accumulates 1MB of trace data.

**Prevention:** Consider a sliding window on the trace for Recall resolution. Instead of keeping ALL visited nodes, keep the last N nodes (where N is the maximum Recall depth observed in the graph's topology). This requires static analysis at graph construction time to determine the maximum Recall chain length. Simpler alternative: keep all nodes but clear their resolved dep values after they are no longer needed for Recall.

### Pitfall 13: Graph Mode Dispatch Lacks Graph Selection

**What goes wrong:** The current graph mode dispatch (shell.py:333-350) assumes a single `namespace["graph"]` object. With a graph registry managing multiple graphs, typing in GRAPH mode needs a way to select WHICH graph receives the input. Without this, all GRAPH mode input goes to the last registered graph, and users cannot interact with specific running graphs.

**Prevention:** GRAPH mode should prefix input with a graph selector (e.g., `@project-1 approve`) or use the graph that most recently requested input. The input gate notification system (Pitfall 1's solution) naturally provides this: the REPL responds to the input request that is currently displayed, which belongs to a specific graph.

### Pitfall 14: SQLite Connection Not Thread-Safe for run_in_executor Offloading

**What goes wrong:** If `store.record()` is moved to `run_in_executor` to avoid blocking the event loop (Pitfall 7's mitigation), the `sqlite3.Connection` is accessed from both the main thread and the executor thread. SQLite's default mode (`check_same_thread=True`) will raise `ProgrammingError`. Even with `check_same_thread=False`, concurrent access without a lock can corrupt the database.

**Prevention:** If using `run_in_executor` for store writes, either: (a) create a dedicated connection per thread, or (b) use `aiosqlite` which manages a single-threaded connection internally, or (c) queue writes and process them from a single dedicated writer thread.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Input gate system | #1 (stdin deadlock), #5 (Event race), #8 (cancellation during deps) | Route through cortex notification system not stdin, per-request Events not shared, fresh dep_cache per run |
| Graph registry / lifecycle | #2 (subprocess orphans), #6 (memory leak), #10 (toolbar scaling) | Kill subprocesses on CancelledError, archive completed graphs, prune TaskManager |
| Graph I/O through channels | #4 (channel flooding), #9 (print interleaving), #7 (store contention) | Per-graph labels + output policy, single print calls, batch store commits |
| Event loop integration | #3 (starvation), #1 (deadlock) | sleep(0) per iteration, no blocking stdin reads |
| Debug views / observability | #4 (flooding), #10 (toolbar scaling), #6 (memory from trace retention) | Rate-limit debug output, lazy trace inspection, archive old graphs |

---

## Evidence Base

| Finding | Source | Confidence |
|---------|--------|------------|
| `TerminalPrompt` uses `run_in_executor(None, input)` -- competes with prompt_toolkit for stdin | Direct code: prompt.py:54, shell.py:448 | HIGH |
| TaskManager does not track LM subprocess processes inside graph execution | Direct code: tasks.py:44-48 vs graph.py:380-384 -- no register_process call path from arun | HIGH |
| `_run_cli_json` does not handle CancelledError for subprocess cleanup | Direct code: lm.py:386-391 -- only catches TimeoutError | HIGH |
| asyncio event loop only keeps weak references to tasks | [CPython #91887](https://github.com/python/cpython/issues/91887), [Python docs](https://docs.python.org/3/library/asyncio-task.html) | HIGH |
| TaskManager._tasks never prunes completed entries | Direct code: tasks.py:75-84 updates state, never deletes | HIGH |
| `store.record()` commits synchronously on every call | Direct code: store.py:89 | HIGH |
| SQLite WAL allows concurrent reads but serializes writes | [SQLite WAL docs](https://sqlite.org/wal.html), [iifx.dev article](https://iifx.dev/en/articles/17373144) | HIGH |
| `print_formatted_text()` with patch_stdout is not thread-safe | [prompt-toolkit #1866](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1866), [reference docs](https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html) | HIGH |
| `asyncio.Event.clear()` has race conditions with multiple waiters | [Trio #637](https://github.com/python-trio/trio/issues/637), asyncio docs recommend fresh events | MEDIUM |
| prompt_toolkit `create_background_task` manages references; raw `create_task` may lose them | [prompt-toolkit #1847](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1847), [Python docs](https://docs.python.org/3/library/asyncio-task.html) | HIGH |
| Subprocess orphans on task cancellation are a known CPython issue | [CPython #88050](https://github.com/python/cpython/issues/88050) | HIGH |
| Channel metadata label already supports per-graph prefixes | Direct code: channels.py:83-84, views.py:153-154 | HIGH |
| dep_cache is local to arun(), already properly scoped per run | Direct code: graph.py:308 | HIGH |

---

*Pitfalls researched: 2026-02-15 for graph runtime in REPL milestone*
*Previous version: v5.0 Stream Views pitfalls (2026-02-14) -- that file covered Rich rendering, prompt hardening, and tool interception. This file covers concurrent graph execution, input gates, and observability.*
