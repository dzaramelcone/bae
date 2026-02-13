# Domain Pitfalls: Cortex -- Augmented Async Python REPL

**Domain:** Adding an async REPL shell with channel-based I/O, reflective namespace, AI integration, and OTel instrumentation to an existing async Python agent graph framework
**Researched:** 2026-02-13
**Confidence:** HIGH for prompt_toolkit/asyncio integration (official docs + known issues verified), HIGH for asyncio channel pitfalls (verified against multiple sources + codebase analysis), MEDIUM for OTel async context propagation (official docs + community reports), MEDIUM for reflective namespace issues (inferred from Python internals + REPL precedents)

---

## Critical Pitfalls

Mistakes that cause rewrites, deadlocks, or architectural dead ends.

---

### Pitfall 1: Event Loop Ownership Conflict Between prompt_toolkit and Graph Execution

**What goes wrong:**
prompt_toolkit 3.0 uses asyncio natively. It calls `asyncio.run()` internally when you use `PromptSession.prompt()` (the sync API). Bae's `Graph.run()` also calls `asyncio.run()` internally (line 217 of graph.py). If cortex's REPL loop calls `Graph.run()` from within the prompt_toolkit event loop, you get `RuntimeError: asyncio.run() cannot be called from a running event loop`. The two systems fight over who owns the event loop.

**Why it happens in bae specifically:**
Bae has a sync/async split: `Graph.run()` wraps `Graph.arun()` via `asyncio.run()`. The same pattern exists in `CompiledGraph.run()`. This sync wrapper is designed for script-level callers who have no event loop. But cortex IS an event loop -- it is an async REPL running inside `asyncio.run()`. If cortex calls `graph.run()` instead of `await graph.arun()`, the nested `asyncio.run()` explodes.

This is not hypothetical. The exact same issue plagues IPython's async REPL: "IPykernel has a persistent asyncio loop running, while Terminal IPython starts and stops a loop for each code block." Projects like `nest_asyncio` exist solely to work around this. ptpython's `--asyncio` flag exists because the problem is that common.

**Consequences:**
- `RuntimeError` crash on every graph execution from the REPL
- If worked around with `nest_asyncio`, subtle reentrancy bugs emerge (gather() within gather(), shared dep_cache mutation under concurrent resolution)
- Users cannot `await graph.arun(...)` from the REPL without cortex properly embedding async execution in its event loop

**Warning signs:**
- Any call to `asyncio.run()` from within the REPL crashes
- Import of `nest_asyncio` appears in the codebase
- Users must remember `await graph.arun()` instead of `graph.run()` and there is no error message telling them why

**Prevention:**
1. **Cortex must own the event loop.** The REPL runs inside `asyncio.run(main())`. All graph execution goes through `await graph.arun()`, never `graph.run()`. The sync wrappers are for external scripts, not for the REPL.
2. **Make `graph.run()` detect a running loop and raise a clear error.** Instead of the cryptic `asyncio.run() cannot be called from a running event loop`, detect and say: `"graph.run() cannot be used inside cortex. Use 'await graph.arun(...)' instead."`
3. **Auto-await in the REPL namespace.** If the user types `graph.run(...)`, cortex should detect this returns a coroutine from `arun` and auto-await it, similar to IPython's autoawait feature. Or better: make the REPL's default code execution async so all top-level awaits work.
4. **Never use `nest_asyncio`.** It papers over the problem but introduces reentrancy hazards with bae's `asyncio.gather()` calls in the resolver. If two graph executions share a dep_cache and both resolve concurrently via nested event loops, the cache mutations race.

**Detection:** Unit test that calls `graph.run()` from within a running event loop and asserts the error message is clear, not a raw RuntimeError.

**Phase to address:** Phase 1 (REPL foundation). Event loop ownership is the first design decision. Everything else depends on getting this right.

---

### Pitfall 2: prompt_toolkit Output Corruption From Concurrent Graph Streams

**What goes wrong:**
When a graph executes in the background (or multiple graphs execute concurrently), their output -- LLM streaming tokens, dep resolution logs, trace updates -- writes to stdout. Without `patch_stdout()`, these writes corrupt the prompt_toolkit input line, producing garbled terminal output where the user's partially-typed input intermixes with graph output.

Even with `patch_stdout()`, there are documented issues: prints near application exit get swallowed (prompt-toolkit/python-prompt-toolkit#1079), thread-based printing causes exceptions in interactive mode (prompt-toolkit/python-prompt-toolkit#1040), and if a print is not inside the `patch_stdout()` context, it ruins the terminal for other widgets.

**Why it happens in bae specifically:**
Bae's `ClaudeCLIBackend` shells out to `claude` CLI via `asyncio.create_subprocess_exec()` and reads stdout. During LLM fill operations, stdout from the subprocess flows through asyncio pipes. If cortex wants to stream LLM responses (showing tokens as they arrive), those writes must go through prompt_toolkit's patched stdout. But the subprocess stdout is a pipe, not sys.stdout -- `patch_stdout()` does not intercept it.

Additionally, bae's resolver uses `asyncio.gather()` to resolve deps concurrently. Multiple dep functions might print or log simultaneously. In a REPL context, these concurrent writes are visible to the user and must be properly interleaved.

**Consequences:**
- Terminal becomes garbled when graph output intermixes with the prompt line
- User loses their partially-typed input when background output scrolls the terminal
- LLM streaming tokens appear in random positions relative to the input prompt
- After terminal corruption, the user must restart cortex

**Warning signs:**
- Output appears on the same line as the input prompt
- Terminal state (cursor position, color) is wrong after a graph completes
- Background task output disappears (swallowed by `patch_stdout` on exit)
- Tests pass but the REPL visually breaks in practice

**Prevention:**
1. **All output must go through a cortex channel, never raw stdout.** Graph execution output, LLM streaming, dep resolution logs -- everything routes through an output channel that cortex's display layer renders above the prompt line via `patch_stdout()`.
2. **Use prompt_toolkit's `print_formatted_text()` instead of `print()`.** This function respects the patched stdout context and properly renders above the prompt.
3. **Wrap `patch_stdout()` around the entire REPL session, not individual prompts.** The official example shows `with patch_stdout(): background_task = ...; await interactive_shell()`. This is the correct scope.
4. **Never allow raw print() from within graph execution.** Enforce this by routing all output through a `Channel` that cortex controls. The channel buffers output and flushes through `patch_stdout()`.
5. **Test terminal rendering manually.** Automated tests cannot catch visual corruption. The REPL needs manual QA with concurrent graph execution.

**Phase to address:** Phase 1 (REPL foundation) for `patch_stdout` setup. Phase 2 (channel I/O) for the output channel architecture.

---

### Pitfall 3: Channel Deadlock From Bounded Queue + Synchronous Consumer

**What goes wrong:**
Channel-based I/O between the REPL and graph execution uses `asyncio.Queue` for message passing. If the queue is bounded (has a `maxsize`) and the consumer is blocked (e.g., waiting for user input in `prompt_async()`), producers block on `queue.put()` waiting for space. The consumer is waiting for the user, the producer is waiting for the consumer -- deadlock.

This is the classic bounded-buffer deadlock, but in asyncio it manifests differently: since everything runs on one thread, a deadlock means the event loop itself is blocked. No coroutines advance. The REPL appears frozen.

**Why it happens in bae specifically:**
Cortex will have at least two concurrent activities: (1) the prompt session waiting for user input, and (2) background graph execution producing results. If graph results flow through a bounded queue and the REPL loop is:

```python
while True:
    user_input = await session.prompt_async()  # Blocks here
    # ... queue.get() happens only after user presses enter
```

Then the graph cannot put results into a full queue because nobody is calling `queue.get()` -- the REPL is waiting for the user. The graph blocks, the user sees nothing, and assumes the REPL crashed.

This is compounded by bae's use of `asyncio.gather()` in the resolver. If a dep function tries to write to the output channel during resolution, and the channel is full, the entire gather stalls -- including other deps that have nothing to do with the channel.

**Consequences:**
- REPL freezes when graph execution fills the output queue
- User sees no output and thinks the system is hung
- Dep resolution stalls because one dep's output write blocks the entire gather
- Ctrl+C may not work cleanly because the event loop is blocked

**Warning signs:**
- REPL freezes intermittently during long-running graph executions
- Adding more concurrent graph executions makes freezes more common
- Removing the queue maxsize "fixes" the freeze (but introduces memory issues)
- Ctrl+C takes unusually long to respond

**Prevention:**
1. **Output channels must be unbounded or use a drain pattern.** For display output (things the user sees), use `asyncio.Queue()` without maxsize. The user's terminal is the natural backpressure -- if they can't read fast enough, the queue buffers. Memory growth is bounded in practice because graph output is finite per execution.
2. **Separate the prompt wait from the output consumer.** Use `asyncio.wait()` with `FIRST_COMPLETED` to multiplex between user input and output messages:
   ```python
   input_task = asyncio.create_task(session.prompt_async())
   output_task = asyncio.create_task(output_queue.get())
   done, pending = await asyncio.wait(
       {input_task, output_task}, return_when=asyncio.FIRST_COMPLETED
   )
   ```
   This way the REPL processes output messages even while waiting for user input.
3. **Never put a bounded queue between graph execution and output.** If you need backpressure for graph execution scheduling (e.g., limit concurrent graph runs), use a semaphore at the admission point, not a bounded output queue.
4. **Use `queue.put_nowait()` for fire-and-forget output.** If the queue is unbounded, `put_nowait()` never blocks. If it must be bounded, catch `QueueFull` and drop the oldest message (display backpressure -- losing old output is acceptable for streaming display).

**Detection:** Test with a graph that produces output faster than the consumer reads. Verify no deadlock after 100 messages.

**Phase to address:** Phase 2 (channel I/O architecture). The multiplexing pattern is the core of the REPL's event handling.

---

### Pitfall 4: asyncio.gather() Exception Handling Destroys Sibling Tasks

**What goes wrong:**
Bae's resolver uses `asyncio.gather()` (without `return_exceptions=True`) to resolve deps concurrently. If one dep raises an exception, `asyncio.gather()` propagates that exception immediately to the caller -- but **the other tasks in the gather continue running on the event loop**. They are not cancelled. They are orphaned.

In a REPL context, this means a failed dep resolution leaks running tasks. If the user retries, new tasks spawn alongside the old orphaned ones. Over time, orphaned tasks accumulate, consuming memory and potentially making stale LLM calls.

Worse: if the user hits Ctrl+C during a graph execution, `CancelledError` propagates into the gather. If a sibling coroutine is mid-LLM-call (e.g., `ClaudeCLIBackend._run_cli_json` with a subprocess running), the cancellation may not clean up the subprocess. The subprocess continues running after the REPL reports cancellation.

**Why it happens in bae specifically:**
The resolver's gather calls (lines 383 and 451 of resolver.py) use bare `asyncio.gather()` without `return_exceptions=True`:

```python
results = await asyncio.gather(
    *[_resolve_one(fn, dep_cache, trace) for fn in to_resolve]
)
```

This is correct for batch execution (fail fast on error) but dangerous in an interactive REPL where:
- The user expects to recover from errors and retry
- Background subprocesses (Claude CLI) must be killed on cancellation
- Task leaks accumulate across REPL interactions

**Consequences:**
- Failed dep resolution leaks running tasks (LLM calls continue in background)
- Ctrl+C does not cleanly stop graph execution (subprocesses orphaned)
- Memory grows over time from accumulated orphaned tasks
- Stale LLM responses arrive after the user has moved on, potentially corrupting shared state

**Warning signs:**
- After cancelling a graph run, CPU/network activity continues
- `asyncio.all_tasks()` shows growing task count across REPL interactions
- Subprocess PIDs survive after cancellation (visible in `ps`)
- Stale output appears after an error or cancellation

**Prevention:**
1. **Use `asyncio.TaskGroup` (Python 3.11+) instead of bare `gather()` for REPL-context resolution.** TaskGroup automatically cancels sibling tasks when one fails, and propagates CancelledError cleanly. Since bae requires Python 3.14, this is available. However, this is a change to existing resolver code and must not break batch execution.
2. **Alternatively, wrap graph execution in a TaskGroup at the cortex level.** Cortex creates a TaskGroup for each graph run. All tasks spawned during that run (dep resolution, LLM calls, subprocess management) live in the group. Cancellation of the group cancels everything.
3. **Register subprocess cleanup.** When `ClaudeCLIBackend` creates a subprocess, register it for cleanup. On CancelledError, `process.kill()` is called in a finally block (the timeout path already does this, but the cancellation path does not).
4. **Monitor task leaks in development.** Add a debug mode that logs `len(asyncio.all_tasks())` after each REPL interaction. Alert if task count grows monotonically.

**Phase to address:** Phase 1 (REPL execution model). The task lifecycle model must be defined before graph execution is wired into the REPL.

---

### Pitfall 5: OTel Context Propagation Breaks Across asyncio.gather() Boundaries

**What goes wrong:**
OpenTelemetry Python uses `contextvars` for span context propagation. In normal async code, `await` preserves context -- a child coroutine inherits the parent's span context. But `asyncio.create_task()` copies context at creation time, and `asyncio.gather()` creates tasks internally. When bae's resolver resolves multiple deps in parallel via `gather()`, each dep task gets a copy of the parent context at the moment the task is created. If one dep modifies the context (e.g., starts a child span), the other deps don't see it.

This is correct behavior for independent deps. But it means the trace structure is flat: all concurrent deps appear as siblings under the parent span, not as a sequential chain. More problematically, if an OTel span is started before the gather and ended after the gather, the span correctly parents all dep spans. But if a dep itself creates a sub-span and that sub-span is not ended (due to an exception), the span leaks -- it persists in the contextvar as an unclosed span, and subsequent operations in that context see a stale parent.

**Why it happens in bae specifically:**
Bae's dep resolution topology is a DAG resolved level-by-level via `asyncio.gather()`. Each level's deps run concurrently. An OTel trace of a graph execution should show:

```
graph.arun
  resolve_fields (node 1)
    dep_a  \
    dep_b  / concurrent (siblings in trace)
  lm.fill (node 1)
  resolve_fields (node 2)
    dep_c
  lm.fill (node 2)
```

If deps are not properly instrumented, the trace shows all deps and fills as flat siblings under `graph.arun` -- losing the per-node grouping. Worse, if a dep starts a span and fails without ending it, subsequent spans in the same context have a wrong parent.

The `run_in_executor` path is also relevant: if any dep function uses blocking I/O via `run_in_executor`, the context does NOT propagate to the executor thread automatically. Only `asyncio.to_thread()` (Python 3.9+) propagates contextvars. Raw `run_in_executor` loses the OTel context entirely, producing orphan spans.

**Consequences:**
- Trace hierarchy is flat instead of reflecting the per-node, per-level DAG structure
- Span leaks from failed deps corrupt subsequent trace context
- `run_in_executor` calls produce orphan spans (no parent)
- Performance overhead from creating many short-lived spans in hot paths (dep resolution runs on every node)

**Warning signs:**
- OTel traces show all operations as flat siblings instead of nested tree
- Some spans have no parent (orphans) despite being part of a graph execution
- Span count grows without bound across REPL interactions
- Switching from sequential to concurrent dep resolution changes trace shape unexpectedly

**Prevention:**
1. **Create spans at the right granularity.** Span per graph execution (top-level), span per node step, span per LM call. Do NOT span individual dep resolutions unless they involve I/O (LLM calls). Pure-compute deps should be attributes on the node span, not separate spans.
2. **Always use `with tracer.start_as_current_span()` context manager, never manual `span.start()`/`span.end()`.** The context manager guarantees cleanup even on exception. Manual start/end is the primary source of span leaks.
3. **Use `asyncio.to_thread()` instead of `run_in_executor()` when calling blocking code.** `to_thread` propagates contextvars automatically. If `run_in_executor` is unavoidable, manually copy context: `ctx = contextvars.copy_context(); loop.run_in_executor(None, ctx.run, fn)`.
4. **Test trace structure.** Export spans to an in-memory exporter in tests. Assert parent-child relationships match expected DAG structure. Assert no orphan spans. Assert span count is bounded.
5. **Use head-based sampling in the REPL.** In a REPL, the user runs many short interactions. Without sampling, every keystroke and tab-completion generates spans. Use `TraceIdRatioBased` sampling or only create spans for graph executions, not REPL input handling.

**Phase to address:** Phase 4 (OTel instrumentation). Should be addressed after the REPL and channel architecture are stable, because instrumentation wraps those layers.

---

## Moderate Pitfalls

Mistakes that cause bugs, confusing behavior, or technical debt.

---

### Pitfall 6: Reflective Namespace Holds References That Prevent GC

**What goes wrong:**
A reflective REPL namespace exposes graph nodes, traces, results, and LM backends as live objects the user can inspect and manipulate. These objects hold references to other objects (traces hold all intermediate nodes, nodes hold Pydantic models with nested structures, LM backends hold agent caches). If the namespace retains references to old graph results, those entire object trees are pinned in memory.

In a long REPL session, the user runs many graphs. Each result stays in the namespace (e.g., `result`, `_`, `_1`, `_2`, ...). Each result's trace holds every node instance from that execution. The memory footprint grows linearly with the number of executions, never shrinking because the namespace holds the references.

**Why it happens in bae specifically:**
Bae's `GraphResult.trace` is a `list[Node]`, and each `Node` is a Pydantic `BaseModel` that may hold complex nested data (the OOTD example has nodes with weather data, outfit recommendations, URLs, etc.). The dep_cache (keyed by callable identity) holds resolved dep values for the lifetime of a graph run. If the namespace retains the dep_cache or the GraphResult, all dep values are pinned.

Additionally, `PydanticAIBackend._agents` is a dict cache that grows without bound -- each unique `(output_types, allow_none)` tuple creates a new Agent. In a REPL where the user experiments with many different node types, this cache grows indefinitely.

**Consequences:**
- Memory grows linearly with REPL usage, never shrinking
- Long REPL sessions eventually OOM
- User cannot free memory without restarting cortex
- Pydantic model instances pin their validators, which pin their classes

**Warning signs:**
- Process memory grows steadily during a REPL session
- `gc.get_referrers(old_result)` shows the namespace dict as the retainer
- `PydanticAIBackend._agents` dict grows without bound
- `del result` doesn't actually free the memory (other references from `_`, `__`, etc.)

**Prevention:**
1. **Limit history depth.** Keep only the last N results in the namespace (e.g., `_1` through `_10`). Older results are explicitly `del`-ed from the namespace and the references are dropped.
2. **Weak references for optional history.** If extended history is desired, store `weakref.ref()` to old results. When memory pressure triggers GC, old results can be collected.
3. **Clear dep_cache after each graph run.** The dep_cache is per-run already (created at line 257 of graph.py), but if cortex's namespace holds a reference to a function's closure that captured the cache, it persists. Ensure dep_cache is not exposed in the namespace.
4. **Bound the Agent cache.** Add a `maxsize` or LRU policy to `PydanticAIBackend._agents`. In a REPL, the user might experiment with many type combinations. The cache should evict old entries.
5. **Provide `%clear` / `%gc` magic.** Give the user explicit control to purge old results and force garbage collection.

**Phase to address:** Phase 2 (reflective namespace). Design the namespace retention policy before exposing objects.

---

### Pitfall 7: AI Context Explosion From Accumulating REPL History

**What goes wrong:**
When cortex integrates AI assistance (e.g., "explain this trace", "optimize this node"), the AI call must include context: the current namespace state, recent execution history, graph definitions, error messages. In a long REPL session, this context grows without bound. Eventually, the context exceeds the model's window, and the AI either truncates silently (producing wrong answers from partial context) or errors out.

Multi-agent systems amplify this: "if a root agent passes its full history to a sub-agent, and that sub-agent does the same, you trigger a context explosion where the token count skyrockets."

**Why it happens in bae specifically:**
Bae's graph execution traces contain rich, multi-field nodes. A single OOTD trace has 3+ nodes, each with 5-6 fields. Ten graph executions produce 30+ nodes in the history. If the AI context includes the full REPL history ("here's everything the user has done"), token count explodes:

- Namespace state (all live objects serialized): 500-2000 tokens
- Per-execution trace: 200-500 tokens
- 10 executions of history: 2000-5000 tokens
- Graph definition (node classes, field types): 500-1000 tokens
- Current error/question: 100-300 tokens
- System prompt: 500-1000 tokens
- **Total: 3800-9800 tokens before the AI even responds**

At 20+ executions, context hits 15K+ tokens. The AI starts "confidently producing incorrect results" because it works with partial context after truncation.

**Consequences:**
- AI answers degrade as REPL session length increases
- Token costs grow linearly with session length
- Silent truncation produces confident but wrong AI responses
- User loses trust in AI assistance after it gives bad advice from stale context

**Warning signs:**
- AI responses become less accurate later in a session
- AI "forgets" things it correctly referenced earlier
- Token usage metrics show linear growth per interaction
- AI responses reference objects that no longer exist in the namespace

**Prevention:**
1. **Scope AI context to the current task, not the full history.** When the user asks "explain this trace", send only: the current trace, the graph definition, and the question. Do not send all previous traces.
2. **Summarize, don't serialize.** Instead of sending `result.trace` as full JSON, send a summary: "3-node trace: IsTheUserGettingDressed -> AnticipateUsersDay -> RecommendOOTD. Final output: top='sweater', bottom='joggers'." Summaries compress 500 tokens to 50.
3. **Use a sliding window.** Keep only the last 3-5 REPL interactions in the AI context. Older interactions are dropped unless the user explicitly references them.
4. **Make context budget explicit.** Track token count of AI context. If approaching 80% of window, warn: "AI context is large (12K tokens). Consider starting a new session for better responses."
5. **Never include the full namespace.** Only include objects the user explicitly references in their query. "Explain _1" sends `_1`, not `_1` through `_10`.

**Phase to address:** Phase 3 (AI integration). Design the context scoping strategy before implementing AI commands.

---

### Pitfall 8: Streaming LLM Output Conflicts With REPL Input

**What goes wrong:**
When an AI-assisted command or a graph execution streams LLM tokens (showing output as it's generated), those tokens write to the terminal. If the user starts typing before streaming completes, the streaming output and user input intermix. The user sees garbled text: "Here is the analy[user types 'he']sis of your tra[user types 'lp']ce..."

This is distinct from Pitfall 2 (background output corruption) because streaming is foreground -- the user is watching and waiting for the stream, but decides to type before it finishes.

**Why it happens in bae specifically:**
Bae's `ClaudeCLIBackend` uses subprocess stdout pipes for LLM output. The output arrives as a complete blob (the CLI blocks until done). But if cortex adds native API streaming (via PydanticAI's streaming support), tokens arrive incrementally. The REPL must decide: is the user allowed to type while streaming? If yes, how do you prevent visual corruption?

**Consequences:**
- Streaming output and user input visually intermix
- User must wait for streaming to complete before typing (poor DX)
- Ctrl+C during streaming may not cancel cleanly (stream continues in background)
- Terminal state corruption if streaming uses ANSI codes that aren't properly reset

**Warning signs:**
- User input appears inside streaming output text
- Streaming continues after user presses Ctrl+C
- Terminal colors or cursor position are wrong after streaming
- Tests pass but visual rendering is broken

**Prevention:**
1. **Streaming output goes to a dedicated region.** Use prompt_toolkit's output abstraction to write streaming tokens above the prompt line (same as `patch_stdout` behavior). The user can type at any time; streaming appears above their input.
2. **Gate input during foreground AI operations.** When the user runs an AI command (e.g., `/explain`), disable the prompt until streaming completes. Show a spinner or progress indicator instead of the prompt. This is simpler and avoids the multiplexing complexity.
3. **Cancellation must kill the stream.** If the user presses Ctrl+C during streaming, the LLM call must be cancelled immediately. For subprocess-based backends (ClaudeCLI), this means `process.kill()`. For API-based backends (PydanticAI), this means aborting the HTTP stream.
4. **Reset terminal state after streaming.** Any ANSI codes (colors, bold) used during streaming must be reset before the prompt reappears. Use prompt_toolkit's style system rather than raw ANSI codes.

**Phase to address:** Phase 3 (AI integration). Streaming display is an AI integration concern.

---

### Pitfall 9: Reflective Namespace Leaks Internal State

**What goes wrong:**
A reflective namespace exposes bae's internals (nodes, graphs, LM backends, traces) for user inspection. If the namespace exposes mutable internal state, the user (or AI) can accidentally mutate it, corrupting subsequent graph executions. For example, if the namespace exposes the LM backend instance and the user modifies `lm._agents`, subsequent graph executions use the mutated cache.

More subtly: Pydantic models with `model_config = ConfigDict(arbitrary_types_allowed=True)` can hold unpicklable values. If cortex provides a "save session" feature that pickles the namespace, it crashes on these objects. And if cortex provides tab-completion over the namespace, inspecting complex objects (e.g., calling `repr()` on a large trace) can block the event loop if `repr` triggers expensive computation.

**Why it happens in bae specifically:**
Bae's `Node` is a Pydantic BaseModel with `arbitrary_types_allowed=True`. Dep-annotated fields can hold any Python object (the result of the dep function). If a dep function returns, say, an HTTP client or a database connection, that object is in the trace, and the trace is in the namespace. Pickling the namespace for session save hits these non-serializable objects.

The `dep_cache` in graph.py stores an `LM_KEY = object()` sentinel. If exposed in the namespace, this sentinel is confusing and the cache is mutable.

**Consequences:**
- User accidentally mutates internal LM state, breaking graph execution
- Session save fails on unpicklable objects in the namespace
- Tab-completion hangs on expensive `__repr__` methods
- Internal implementation details leak into the user-facing API

**Warning signs:**
- User can modify `lm._agents` and break subsequent runs
- `pickle.dumps(namespace)` raises `PicklingError`
- Tab-completion pauses for seconds when expanding a complex object
- User sees internal objects (`dep_cache`, `LM_KEY`) in the namespace

**Prevention:**
1. **Namespace exposes views, not internals.** Wrap exposed objects in read-only proxies or provide accessor functions. `cortex.graph` returns a read-only view of the graph. `cortex.trace` returns a copy of the trace, not the live list.
2. **No pickle for session state.** Use JSON serialization for saveable state. Non-serializable objects (LM backends, live connections) are recreated on session load, not saved.
3. **Lazy repr with depth limits.** Override `__repr__` for namespace objects to be shallow. For traces, show `[3 nodes: IsTheUserGettingDressed -> ... -> RecommendOOTD]` not the full Pydantic dump. Set a repr depth limit for tab-completion.
4. **Separate user namespace from runtime namespace.** User's variables live in one dict, bae's runtime state lives in another. The user can inspect bae state through accessor functions but cannot accidentally assign to it.

**Phase to address:** Phase 2 (reflective namespace design). The namespace boundary is a design decision, not an implementation detail.

---

### Pitfall 10: asyncio.Queue.shutdown() Semantics and Graceful REPL Exit

**What goes wrong:**
When the user exits cortex (Ctrl+D, `exit()`, or `/quit`), all background tasks must be cleanly shut down: in-progress graph executions cancelled, LLM subprocesses killed, OTel spans flushed, output channels drained. `asyncio.Queue` in Python 3.13+ supports `.shutdown()` to signal producers and consumers that the queue is closing. But if cortex supports Python 3.14 (as bae requires), the shutdown semantics interact poorly with tasks blocked on `queue.get()` or `queue.put()`.

Specifically: after `shutdown()`, calls to `get()` raise `QueueShutDown` on an empty queue, but calls on a non-empty queue succeed (draining remaining items). If a consumer is blocked on `get()` when shutdown is called, it wakes up with `QueueShutDown`. But if the consumer has a `try/except` that catches generic exceptions and retries, it spins in a tight loop catching `QueueShutDown` and retrying.

**Why it happens in bae specifically:**
Cortex will have multiple async tasks: the prompt loop, the output display loop, background graph executions. On exit, all must stop. If shutdown order is wrong:
- Shutting down the output queue before cancelling graph tasks means graph tasks try to write to a shut-down queue and get `QueueShutDown`
- Cancelling graph tasks before shutting down the output queue means remaining output is lost (user never sees final results)
- If the OTel exporter has a flush timeout and the event loop exits before flush completes, traces are lost

**Consequences:**
- REPL exit hangs (tasks don't terminate)
- REPL exit crashes (unhandled QueueShutDown exceptions)
- Final output lost (queue shut down before drain)
- OTel traces from the last interaction lost (exporter not flushed)

**Warning signs:**
- `asyncio.run()` prints "Task was destroyed but it is pending!" warnings on exit
- REPL takes several seconds to exit (timeout waiting for tasks)
- User's last graph result is missing from output
- OTel backend shows missing final traces

**Prevention:**
1. **Define a shutdown sequence.** (1) Signal graph tasks to cancel. (2) Wait for graph tasks to complete/cancel with a timeout. (3) Drain output queue. (4) Shut down output queue. (5) Flush OTel exporter. (6) Exit.
2. **Use `asyncio.timeout()` around shutdown steps.** If any step takes more than 2 seconds, force-kill and move to the next step. Do not hang forever.
3. **Register signal handlers for SIGINT/SIGTERM.** Cortex should handle Ctrl+C gracefully by triggering the shutdown sequence, not by letting the default handler raise KeyboardInterrupt (which leaves tasks orphaned).
4. **Test exit behavior.** Automated test that starts cortex, runs a graph, and exits. Assert no "Task was destroyed" warnings, no zombie subprocesses, and OTel export completes.

**Phase to address:** Phase 1 (REPL lifecycle). Graceful startup and shutdown are part of the core REPL architecture.

---

### Pitfall 11: OTel Instrumentation Performance Overhead in Hot Paths

**What goes wrong:**
OTel span creation has non-zero overhead: context copying, attribute serialization, span ID generation. In bae's dep resolution, which runs `asyncio.gather()` over potentially many deps per node, creating a span per dep per node per graph execution can add measurable latency. For a graph with 5 nodes, each with 3 deps, that's 15 dep spans per execution. In a REPL where the user runs graphs rapidly, the overhead accumulates.

Span attribute filtering can cut trace volumes by 70%, but the span creation overhead itself (before filtering) is unavoidable once instrumentation is added.

**Why it happens in bae specifically:**
Bae's dep resolution is the hottest path: it runs on every node transition, potentially making LLM calls (for Node-as-Dep) and running user functions. If every dep resolution creates a span, every dep function call creates a child span, and every LM call creates a span, the trace tree for a single graph execution can have 50+ spans.

In a REPL context, the user expects instant responsiveness. Even 5ms of OTel overhead per span, times 50 spans, is 250ms of added latency per graph execution. This is noticeable.

**Consequences:**
- Graph execution measurably slower with instrumentation enabled
- REPL feels sluggish compared to running graphs without cortex
- Users disable instrumentation to get performance, losing observability
- Span volume overwhelms the OTel backend (if exporting to a service)

**Warning signs:**
- `time graph.arun(...)` shows different timing with and without OTel
- OTel backend shows thousands of spans per minute during active REPL use
- REPL input-to-output latency increases after enabling instrumentation
- Span export queue backs up (exporter can't keep up)

**Prevention:**
1. **Span at the right granularity.** One span per graph execution, one span per node step, one span per LM call. Pure-compute deps do NOT get their own spans -- they get attributes on the node span. Only I/O deps (LM calls, HTTP, DB) get spans.
2. **Use span events, not child spans, for lightweight annotations.** `span.add_event("dep_resolved", {"name": "weather", "duration_ms": 12})` is much cheaper than creating a child span.
3. **Default to sampled instrumentation.** In the REPL, sample 1-in-10 graph executions by default. `cortex.trace_all()` enables 100% sampling when the user is debugging.
4. **Lazy instrumentation.** Don't create spans unless an OTel exporter is configured. Check `tracer.is_recording()` before creating spans. If no exporter, the overhead is near zero.
5. **Benchmark.** Before shipping, measure graph execution time with and without instrumentation. Set a budget: OTel overhead must be <5% of total execution time.

**Phase to address:** Phase 4 (OTel instrumentation). Design the span strategy based on measured overhead, not speculation.

---

## Minor Pitfalls

Mistakes that cause annoyance or require cleanup.

---

### Pitfall 12: User Code Exceptions Crash the REPL

**What goes wrong:**
In a standard Python REPL, if user code raises an exception, the REPL prints the traceback and returns to the prompt. It never crashes. Cortex must provide the same guarantee: no user-typed code should be able to crash the REPL process. This includes bae-specific exceptions (`BaeError`, `DepError`, `FillError`, `RecallError`) that might propagate from graph execution.

Bae's convention is to "let errors propagate" (from CONVENTIONS.md: "Never use try-except unless reraising"). This is correct for library code but dangerous for REPL code. The REPL is the outermost exception boundary -- it must catch everything.

**Prevention:**
1. **Catch all exceptions at the REPL eval boundary.** After executing user code, catch `Exception` (not `BaseException` -- let `KeyboardInterrupt` and `SystemExit` through) and print the traceback.
2. **Attach trace context to bae exceptions.** `BaeError`, `DepError`, etc. already have `.trace` attributes. In the REPL, display these alongside the traceback: "Error at node AnticipateUsersDay (step 2 of 3)."
3. **Never catch `CancelledError` at the REPL boundary.** CancelledError (a BaseException in Python 3.9+) must propagate to cancel tasks properly.

**Phase to address:** Phase 1 (REPL error handling). The exception boundary is part of the core REPL loop.

---

### Pitfall 13: Tab-Completion Triggers Expensive Operations

**What goes wrong:**
prompt_toolkit supports custom completers for tab-completion. If cortex provides completion for namespace objects (e.g., typing `result.` shows `trace`, `node`, `result`), the completer must inspect the object. For Pydantic models, this means calling `dir()` or accessing `model_fields`. For large objects, `dir()` can trigger `__getattr__` methods that perform computation, and `repr()` for completion tooltips can be expensive.

If the completer runs synchronously (blocking the event loop), the REPL freezes on every tab press.

**Prevention:**
1. **Completers must be async or cached.** Use prompt_toolkit's `ThreadedCompleter` to run completion in a thread pool, keeping the event loop responsive.
2. **Cache completion results.** Recompute completions only when the namespace changes (new assignment), not on every tab press.
3. **Limit completion depth.** Complete `result.` but not `result.trace[0].` unless explicitly requested. One level of attribute completion is sufficient.
4. **Timeout completion.** If completion takes more than 100ms, return empty results rather than blocking.

**Phase to address:** Phase 2 (reflective namespace). Completion is a namespace concern.

---

### Pitfall 14: Dep Functions With Side Effects Behave Differently in REPL vs Script

**What goes wrong:**
In a script, `graph.run()` executes once and exits. In the REPL, the user runs the graph many times. Dep functions that have side effects (writing to a file, incrementing a counter, making an API call) execute on every run. If a dep function assumes it runs once (e.g., initializes a database schema), running it 10 times from the REPL causes 10 schema initializations.

Bae's `dep_cache` is per-run (created at line 257 of graph.py: `dep_cache: dict = {LM_KEY: lm}`). It does NOT persist across REPL interactions. So a dep that was cached in run 1 is re-executed in run 2. This is correct but surprising: the user might expect caching to persist across runs.

**Prevention:**
1. **Document dep lifecycle clearly.** "Dep functions are called once per graph run. They are not cached across runs. Side effects will execute on every run."
2. **Provide an optional persistent dep cache.** `cortex.dep_cache` that persists across runs for deps the user marks as cacheable. Not default behavior -- opt-in.
3. **Warn about side-effect deps in REPL mode.** If a dep function writes to a file or makes HTTP calls, show a note: "Dep `fetch_weather` made an HTTP call. This will re-execute on every graph run."

**Phase to address:** Phase 2 (reflective namespace / execution model). The dep lifecycle in REPL context needs documentation.

---

### Pitfall 15: Python 3.14 asyncio Changes Affect Event Loop Behavior

**What goes wrong:**
Bae requires Python 3.14+. Python 3.14 includes changes to asyncio that may affect cortex:
- The new REPL (PEP 756) exposed internal imports to the top-level environment (cpython#118908), causing namespace pollution
- asyncio's event loop management continues to evolve, with deprecation of `get_event_loop()` in favor of `get_running_loop()`
- `asyncio.Runner` (added in 3.11) is the recommended way to manage event loop lifecycle

Since cortex will create its own async REPL, it must be aware of these changes to avoid relying on deprecated patterns.

**Prevention:**
1. **Use `asyncio.Runner` for event loop management.** Instead of `asyncio.run()`, use `Runner` for more control over the event loop lifecycle (shutdown behavior, exception handling).
2. **Use `asyncio.get_running_loop()`, never `get_event_loop()`.** The latter is deprecated for contexts where a loop may not be running.
3. **Test on Python 3.14 specifically.** Don't assume 3.12/3.13 behavior carries over. Run the REPL test suite on 3.14 nightlies.
4. **Isolate cortex's namespace from Python's REPL internals.** If Python 3.14's new REPL leaks `os` and `sys` into the top-level scope, cortex's namespace must be independent (use a custom namespace dict, not the module's globals).

**Phase to address:** Phase 1 (REPL foundation). Python version behavior is a foundation concern.

---

## Phase-Specific Warning Summary

| Phase | Pitfall | Risk | Mitigation Priority |
|-------|---------|------|---------------------|
| Phase 1 (REPL Foundation) | #1: Event loop ownership conflict | CRITICAL | cortex owns the loop, graph uses arun() only |
| Phase 1 (REPL Foundation) | #2: Output corruption from concurrent streams | CRITICAL | patch_stdout + output channel |
| Phase 1 (REPL Foundation) | #4: gather() exception handling leaks tasks | HIGH | TaskGroup or cortex-level task management |
| Phase 1 (REPL Foundation) | #10: Graceful shutdown sequence | HIGH | Defined shutdown order with timeouts |
| Phase 1 (REPL Foundation) | #12: User code crashes REPL | MEDIUM | Exception boundary at eval layer |
| Phase 1 (REPL Foundation) | #15: Python 3.14 asyncio changes | MEDIUM | Use Runner, get_running_loop(), test on 3.14 |
| Phase 2 (Channel I/O + Namespace) | #3: Channel deadlock from bounded queue | CRITICAL | Unbounded output queue + multiplexed wait |
| Phase 2 (Channel I/O + Namespace) | #6: Namespace holds GC-preventing references | HIGH | History depth limit, weak refs, cache bounds |
| Phase 2 (Channel I/O + Namespace) | #9: Namespace leaks internal state | HIGH | Read-only views, JSON serialization |
| Phase 2 (Channel I/O + Namespace) | #13: Tab-completion triggers expensive ops | MEDIUM | ThreadedCompleter, caching, depth limits |
| Phase 2 (Channel I/O + Namespace) | #14: Side-effect deps re-execute in REPL | LOW | Documentation, optional persistent cache |
| Phase 3 (AI Integration) | #7: AI context explosion from history | HIGH | Scoped context, summaries, sliding window |
| Phase 3 (AI Integration) | #8: Streaming conflicts with REPL input | MEDIUM | Dedicated output region or gated input |
| Phase 4 (OTel Instrumentation) | #5: OTel context breaks across gather | HIGH | Correct span granularity, context manager spans |
| Phase 4 (OTel Instrumentation) | #11: OTel performance overhead | MEDIUM | Right granularity, events not spans, sampling |

## Key Design Decisions Forced by Pitfalls

These pitfalls force design decisions that must be made before coding starts:

1. **Who owns the event loop?** (Pitfall #1)
   Cortex must own the single event loop. All graph execution goes through `arun()`. The sync `run()` wrappers must detect a running loop and error clearly. This is a non-negotiable architectural constraint.

2. **How do concurrent outputs reach the terminal?** (Pitfalls #2, #3, #8)
   All output flows through cortex-controlled channels. The REPL multiplexes between user input and output consumption. Output channels are unbounded (display output is finite per execution). Streaming uses prompt_toolkit's output abstraction, not raw stdout.

3. **What is the task lifecycle model?** (Pitfalls #4, #10)
   Each graph execution lives in a TaskGroup. Cancellation of the group cancels all subtasks. REPL exit triggers an ordered shutdown sequence with timeouts. No orphaned tasks, no leaked subprocesses.

4. **What does the namespace expose?** (Pitfalls #6, #9)
   The namespace exposes read-only views of bae state, not mutable internals. History is bounded. Non-serializable objects are not exposed. The user namespace and the runtime namespace are separate.

5. **Where do OTel spans go?** (Pitfalls #5, #11)
   Spans at graph/node/LM-call granularity only. Dep resolution uses events, not spans. Context manager spans only (no manual start/end). Sampling by default. Zero overhead when no exporter configured.

## The Central Risk: Event Loop Sovereignty

Pitfalls #1, #2, #3, #4, #8, #10, and #15 all stem from the same root: **cortex is adding an interactive event loop owner to a framework designed for batch execution.** Bae's existing code assumes it controls when the event loop starts and stops (`asyncio.run()` in `graph.run()` and `CompiledGraph.run()`). Cortex reverses this assumption: the REPL owns the event loop, and graph execution is a guest.

Every pitfall in Phase 1 is about establishing this sovereignty cleanly:
- The REPL owns the loop (#1)
- Output goes through the REPL's display system (#2)
- Channel communication respects the loop's single-threaded nature (#3)
- Task lifecycle is managed by the REPL, not by individual graph runs (#4)
- Shutdown is orchestrated by the REPL (#10)

If this sovereignty is established correctly in Phase 1, Phases 2-4 build on a solid foundation. If it's compromised (e.g., by using `nest_asyncio` to paper over the loop conflict), every subsequent phase inherits the instability.

## Sources

**HIGH confidence (official documentation, verified behavior):**
- [prompt_toolkit 3.0 asyncio integration](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/asyncio.html) -- `prompt_async()`, `patch_stdout()`, `run_async()` patterns
- [prompt_toolkit asyncio-prompt.py example](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/asyncio-prompt.py) -- Canonical pattern for async REPL with background tasks
- [Python asyncio documentation](https://docs.python.org/3/library/asyncio-task.html) -- `gather()` semantics, `TaskGroup`, cancellation behavior
- [Python asyncio.Queue documentation](https://docs.python.org/3/library/asyncio-queue.html) -- `shutdown()` semantics (Python 3.13+)
- [OpenTelemetry Python async context example](https://github.com/open-telemetry/opentelemetry-python/blob/main/docs/examples/basic_context/async_context.py) -- contextvars propagation
- [OpenTelemetry asyncio instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asyncio/asyncio.html) -- Async task instrumentation
- [CPython issue #118908](https://github.com/python/cpython/issues/118908) -- New REPL namespace leakage
- Bae codebase analysis (graph.py:217 asyncio.run, resolver.py:383,451 asyncio.gather, lm.py:404 create_subprocess_exec)

**MEDIUM confidence (WebSearch verified against multiple sources):**
- [Armin Ronacher: "I'm not feeling the async pressure"](https://lucumr.pocoo.org/2020/1/1/async-pressure/) -- Backpressure patterns in asyncio, unbounded queue dangers
- [Debug Context Propagation in Async Applications](https://oneuptime.com/blog/post/2026-02-06-debug-context-propagation-async-applications/view) -- OTel context loss across thread boundaries, orphan span identification
- [asyncio.gather() swallows cancellation](https://bugs.python.org/issue32684) -- gather with return_exceptions=True hides CancelledError
- [OpenTelemetry Performance Impact](https://oneuptime.com/blog/post/2026-01-07-opentelemetry-performance-impact/view) -- Span creation overhead, sampling strategies
- [IPython autoawait documentation](https://ipython.readthedocs.io/en/stable/interactive/autoawait.html) -- Nested event loop problem and solutions
- [prompt_toolkit patch_stdout issues](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1079) -- Missing prints on exit
- [prompt_toolkit thread printing exceptions](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1040) -- Thread safety limitations
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) -- Context scoping, history management
- [CPython asyncio REPL issue](https://github.com/python/cpython/issues/142784) -- Event loop lifecycle management
- [asyncio.to_thread contextvars propagation](https://bugs.python.org/issue34014) -- run_in_executor vs to_thread context behavior

**LOW confidence (inferred from patterns, needs validation):**
- OTel span overhead quantification (5ms per span) -- extrapolated from benchmarks, not measured in bae
- PydanticAIBackend._agents cache growth -- inferred from code inspection, not profiled
- Python 3.14 specific asyncio changes -- based on Python 3.13+ patterns, not 3.14 release notes

---
*Pitfalls research for: Bae v4.0 Cortex -- Augmented Async Python REPL*
*Researched: 2026-02-13*
