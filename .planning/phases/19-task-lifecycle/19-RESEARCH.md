# Phase 19: Task Lifecycle - Research

**Researched:** 2026-02-13
**Domain:** asyncio task management, Ctrl-C interrupt handling in prompt_toolkit, configurable REPL toolbar
**Confidence:** HIGH

## Summary

Phase 19 adds three capabilities to cortex: (1) Ctrl-C opens a menu to kill individual running tasks, (2) double Ctrl-C kills all tasks and returns to bare prompt, and (3) the user can configure what the bottom toolbar displays. These map to REPL-10, REPL-11, and REPL-06.

The core technical challenge is interrupt routing. prompt_toolkit intercepts SIGINT at the event loop level and dispatches it as a `Keys.SIGINT` key press into its key processor. The default binding (in `PromptSession._create_prompt_bindings`) calls `event.app.exit(exception=KeyboardInterrupt())`. To implement the task kill menu, we override both the `c-c` and `<sigint>` key bindings with a handler that checks `self.tasks`: if tasks are running, show the kill menu; if no tasks, exit (preserving REPL-12 behavior). Double Ctrl-C is implemented with a timestamp guard -- if two `<sigint>` events arrive within a threshold (e.g., 0.4s), kill all tasks instead of showing the menu.

The `self.tasks: set[asyncio.Task]` field already exists on `CortexShell` (created in Phase 14, never populated). Phase 19 populates it: when the shell dispatches a mode handler (graph execution, AI call, bash subprocess), the awaitable is wrapped in `asyncio.create_task()`, added to `self.tasks`, and cleaned up on completion via a `done_callback`. Task names use `task.set_name()` for display in the kill menu.

For the configurable toolbar (REPL-06), the existing `_toolbar()` method returns a static mode+cwd display. Phase 19 makes it extensible: the user registers callable "widgets" that return formatted text segments. Built-in widgets include task count, mode name, and cwd. Users add custom widgets (CPU load, cost accumulator, etc.) by registering callables on a `ToolbarConfig` object exposed in the namespace.

**Primary recommendation:** Override `c-c`/`<sigint>` key bindings in `_build_key_bindings` to implement the task kill menu and double-Ctrl-C. Use `asyncio.create_task()` + `self.tasks` set for background task tracking. Expose a `ToolbarConfig` in the namespace for user-customizable toolbar segments. No new dependencies -- stdlib `asyncio` and `time` plus existing prompt_toolkit APIs.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio` (stdlib) | 3.14 | `create_task()`, `Task.cancel()`, `Task.set_name()`, `Task.get_name()`, `all_tasks()` | Python's native async task management. All needed APIs verified on 3.14.3. |
| `prompt_toolkit` | 3.0.52 (installed) | Key bindings (`c-c`, `<sigint>`), `checkboxlist_dialog` for task kill menu, `bottom_toolbar` callable, `refresh_interval`, `invalidate()` | Already the REPL framework. Dialog API used for channel toggle (Phase 16). |
| `time` (stdlib) | 3.14 | `time.monotonic()` for double-press detection threshold | Monotonic clock is the correct choice for elapsed-time guards. |
| `os` (stdlib) | 3.14 | `os.getloadavg()` for built-in CPU load toolbar widget | Available on macOS/Linux. No external dep needed for basic load info. |
| `resource` (stdlib) | 3.14 | `resource.getrusage()` for memory/CPU time toolbar widgets | Available on Unix. Reports user/system CPU time and max RSS. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `bae.repl.channels` | internal | `ChannelRouter.write("debug", ...)` for task lifecycle logging | When tasks are created, cancelled, or complete -- debug channel output. |
| `bae.repl.store` | internal | `SessionStore.record()` for task lifecycle events | Persist task start/cancel/complete events for session history. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `checkboxlist_dialog` for kill menu | Custom prompt_toolkit `Application` layout | checkboxlist_dialog is already proven in the codebase (channel toggle). Custom layout is overkill for a selection list. |
| `time.monotonic()` for double-press | `asyncio.get_event_loop().time()` | Both are monotonic clocks. `time.monotonic()` is simpler, doesn't require a running loop reference. |
| stdlib `resource`/`os` for system metrics | `psutil` library | psutil gives richer metrics (per-process CPU%, disk I/O, network) but is not installed. `os.getloadavg()` and `resource.getrusage()` cover the basic use cases without a new dependency. psutil can be added later if users need it. |
| Overriding `c-c`/`<sigint>` bindings | Custom SIGINT signal handler via `signal.signal()` | prompt_toolkit already installs a SIGINT handler that routes to its key processor. Fighting with signal handlers is fragile. Overriding at the key binding level is the sanctioned approach. |

**Installation:**
```bash
# No new dependencies. All existing: prompt_toolkit, asyncio stdlib.
```

## Architecture Patterns

### Recommended Project Structure

```
bae/repl/
    shell.py        # MODIFIED: Ctrl-C handler, task tracking, toolbar config
    toolbar.py      # NEW: ToolbarConfig, built-in widgets, widget protocol
    modes.py        # Unchanged
    exec.py         # Unchanged
    bash.py         # Unchanged
    channels.py     # Unchanged
    store.py        # Unchanged
    namespace.py    # Unchanged
    ai.py           # Unchanged
    complete.py     # Unchanged
```

### Pattern 1: Task Tracking via create_task + done_callback

**What:** Wrap mode dispatches in `asyncio.create_task()`, track in `self.tasks`, clean up via done callback.

**When to use:** Every awaitable mode dispatch (graph execution, AI call). Not needed for synchronous operations.

```python
# In CortexShell:

def _track_task(self, coro, *, name: str) -> asyncio.Task:
    """Create a tracked task from a coroutine."""
    task = asyncio.create_task(coro, name=name)
    self.tasks.add(task)
    task.add_done_callback(self.tasks.discard)
    return task

# Usage in run():
elif self.mode == Mode.GRAPH:
    task = self._track_task(
        self._run_graph(text),
        name=f"graph:{text[:30]}",
    )
    await task  # Wait for completion, but task is tracked for kill menu
```

**Key insight:** The task is both tracked (in `self.tasks`) AND awaited. The REPL loop waits for the task, but if Ctrl-C fires during the wait, the interrupt handler sees the task in `self.tasks` and can cancel it. The `done_callback` ensures cleanup even if the task completes normally before being killed.

**Confidence:** HIGH -- `asyncio.create_task()`, `Task.set_name()`, `add_done_callback()` all verified on Python 3.14.3. The `discard` callback is a common pattern for task set management.

### Pattern 2: Ctrl-C Interrupt Handler with Double-Press Detection

**What:** Override the default `c-c`/`<sigint>` key bindings. Single press with tasks running shows kill menu. Double press within threshold kills all. No tasks running: exit (preserves REPL-12).

**When to use:** Bound at shell construction.

```python
import time

def _build_key_bindings(shell: CortexShell) -> KeyBindings:
    kb = KeyBindings()
    _last_sigint = [0.0]  # mutable container for closure
    DOUBLE_PRESS_THRESHOLD = 0.4  # seconds

    @kb.add("c-c", eager=True)
    @kb.add("<sigint>")
    def handle_interrupt(event):
        """Ctrl-C: task menu, double-Ctrl-C: kill all, no tasks: exit."""
        now = time.monotonic()
        elapsed = now - _last_sigint[0]
        _last_sigint[0] = now

        if not shell.tasks:
            # REPL-12: no tasks running, exit
            event.app.exit(exception=KeyboardInterrupt())
            return

        if elapsed < DOUBLE_PRESS_THRESHOLD:
            # REPL-11: double Ctrl-C, kill all
            for task in list(shell.tasks):
                task.cancel()
            shell.tasks.clear()
            # Return to bare prompt
            event.current_buffer.reset()
            event.app.invalidate()
            return

        # REPL-10: single Ctrl-C, show task kill menu
        event.app.create_background_task(_show_kill_menu(shell, event))

    # ... other bindings ...
    return kb
```

**Critical detail:** The `eager=True` flag on `c-c` ensures our binding takes priority over any prefix bindings. The `<sigint>` binding handles the OS signal path. Together they cover both the terminal key press and the signal-based interrupt.

**Confidence:** HIGH -- prompt_toolkit's default SIGINT handling verified in source (application.py line 813-814, prompt.py line 835-839). Key binding override is the documented mechanism.

### Pattern 3: Task Kill Menu via checkboxlist_dialog

**What:** When Ctrl-C is pressed with tasks running, show a checkbox dialog listing active tasks. User selects which to kill.

**When to use:** On single Ctrl-C when `shell.tasks` is non-empty.

```python
from prompt_toolkit.shortcuts import checkboxlist_dialog

async def _show_kill_menu(shell: CortexShell, event) -> None:
    """Show task kill selection dialog."""
    tasks = list(shell.tasks)
    if not tasks:
        return

    values = [
        (task, f"{task.get_name()}")
        for task in tasks
    ]

    result = await checkboxlist_dialog(
        title="Running Tasks",
        text="Select tasks to kill (Enter to confirm, Esc to cancel):",
        values=values,
    ).run_async()

    if result:
        for task in result:
            task.cancel()
        shell.router.write(
            "debug",
            f"killed {len(result)} task(s)",
            mode="DEBUG",
        )
    event.app.invalidate()
```

**Confidence:** HIGH -- `checkboxlist_dialog` already used in channel toggle (Phase 16). API verified: `values` is a list of `(value, label)` tuples, returns the selected values or None on cancel.

### Pattern 4: Configurable Toolbar via Widget Protocol

**What:** A `ToolbarConfig` object that holds an ordered list of callable widgets. Each widget returns a list of `(style, text)` tuples. The toolbar renders all widgets in sequence. Users register custom widgets from PY mode.

**When to use:** Every toolbar render (called by prompt_toolkit each redraw).

```python
from typing import Callable

# Type alias: a widget returns prompt_toolkit style tuples
ToolbarWidget = Callable[[], list[tuple[str, str]]]


class ToolbarConfig:
    """Configurable toolbar with user-registerable widgets.

    toolbar.add("load", lambda: [("", f" load:{os.getloadavg()[0]:.1f} ")])
    toolbar.remove("load")
    toolbar.widgets  -- list current widget names
    """

    def __init__(self) -> None:
        self._widgets: dict[str, ToolbarWidget] = {}
        self._order: list[str] = []

    def add(self, name: str, widget: ToolbarWidget) -> None:
        """Register a named toolbar widget."""
        if name not in self._widgets:
            self._order.append(name)
        self._widgets[name] = widget

    def remove(self, name: str) -> None:
        """Remove a toolbar widget by name."""
        self._widgets.pop(name, None)
        if name in self._order:
            self._order.remove(name)

    @property
    def widgets(self) -> list[str]:
        """List registered widget names in display order."""
        return list(self._order)

    def render(self) -> list[tuple[str, str]]:
        """Render all widgets into a flat style tuple list."""
        parts: list[tuple[str, str]] = []
        for name in self._order:
            widget = self._widgets.get(name)
            if widget:
                try:
                    parts.extend(widget())
                except Exception:
                    parts.append(("fg:red", f" [{name}:err] "))
        return parts

    def __repr__(self) -> str:
        names = ", ".join(self._order)
        return f"toolbar -- .add(name, fn), .remove(name). widgets: [{names}]"
```

**Shell integration:**
```python
# In CortexShell.__init__():
self.toolbar = ToolbarConfig()
# Register built-in widgets
self.toolbar.add("mode", lambda: [("class:toolbar.mode", f" {MODE_NAMES[self.mode]} ")])
self.toolbar.add("tasks", lambda: [("class:toolbar.tasks", f" {len(self.tasks)} tasks ")] if self.tasks else [])
self.toolbar.add("cwd", self._cwd_widget)
self.namespace["toolbar"] = self.toolbar

# Replace static _toolbar with:
def _toolbar(self):
    return self.toolbar.render()
```

**User customization examples (from PY mode):**
```python
# Show CPU load average
toolbar.add("load", lambda: [("", f" load:{os.getloadavg()[0]:.1f} ")])

# Show running task count in color
toolbar.add("tasks", lambda: [("fg:red bold", f" {len(asyncio.all_tasks())} tasks ")])

# Cost accumulator (user-defined variable)
cost = 0.0  # user tracks this
toolbar.add("cost", lambda: [("fg:yellow", f" ${cost:.2f} ")])

# Remove a widget
toolbar.remove("load")
```

**Confidence:** HIGH -- prompt_toolkit's `bottom_toolbar` accepts any callable that returns `FormattedText` (list of style tuples). The callable is re-evaluated each render. This pattern gives users full control with no framework changes.

### Pattern 5: Awaiting Tasks During Mode Dispatch

**What:** The REPL loop awaits the tracked task, but the task is cancellable via the interrupt handler. The interrupt handler fires inside prompt_toolkit's key processor (which runs in the same event loop), so it can cancel tasks while the REPL loop is awaiting them.

**When to use:** All mode dispatches that create tasks.

```python
# In CortexShell.run():
elif self.mode == Mode.NL:
    task = self._track_task(self._run_nl(text), name=f"ai:{text[:30]}")
    try:
        await task
    except asyncio.CancelledError:
        self.router.write("debug", f"killed: {task.get_name()}", mode="DEBUG")
    except Exception:
        tb = traceback.format_exc()
        self.router.write("ai", tb.rstrip("\n"), mode="NL", metadata={"type": "error"})
```

**Critical insight:** This does NOT work as-is. When the REPL loop is `await`ing a task, it is NOT inside `prompt_async()`. SIGINT arrives as an OS signal, and prompt_toolkit's SIGINT handler calls `key_processor.send_sigint()`. But the key processor only processes keys when the Application is running (during `prompt_async()`). Between prompts (during task execution), SIGINT is handled by asyncio's default behavior: it raises `KeyboardInterrupt` on the running task.

**The actual flow:**
1. User types input, presses Enter
2. `prompt_async()` returns the text
3. REPL loop dispatches to mode handler (not inside prompt_toolkit anymore)
4. During mode handler execution, SIGINT raises `KeyboardInterrupt` in Python
5. REPL loop catches it

**This means:** The Ctrl-C behavior during task execution is NOT handled by prompt_toolkit key bindings. It's handled by the REPL loop's `except KeyboardInterrupt` clause. The key binding override only applies when the user is at the prompt (inside `prompt_async()`).

**Revised approach:** The interrupt handler has two paths:
- **At prompt** (inside `prompt_async()`): key binding handles `c-c`/`<sigint>`. If tasks running, show menu. If no tasks, exit.
- **During execution** (outside `prompt_async()`): `KeyboardInterrupt` propagates. Catch it in the REPL loop, cancel the current task, return to prompt.

```python
async def run(self) -> None:
    with patch_stdout():
        while True:
            try:
                text = await self.session.prompt_async()
            except KeyboardInterrupt:
                # At prompt: already handled by key binding for task cases
                # If we get here, no tasks were running -- exit
                self.store.close()
                return
            except EOFError:
                await self._shutdown()
                return

            if not text.strip():
                continue

            # Dispatch to mode handler with task tracking
            try:
                await self._dispatch(text)
            except KeyboardInterrupt:
                # During execution: cancel tracked tasks
                self._cancel_current()
            except asyncio.CancelledError:
                self._cancel_current()
```

**Confidence:** HIGH -- this matches the behavior analysis from Phase 14 research (Pitfall #6). The two-path interrupt model is inherent to how prompt_toolkit works.

### Anti-Patterns to Avoid

- **Using `signal.signal(SIGINT, ...)` directly:** prompt_toolkit installs its own SIGINT handler via `loop.add_signal_handler()`. Installing a competing handler will break prompt_toolkit's input processing. Override at the key binding level, not the signal level.
- **Cancelling tasks from within a key binding handler without `create_background_task`:** Key binding handlers are synchronous. Calling `task.cancel()` is synchronous and safe. But showing a dialog (which is async) must be dispatched via `event.app.create_background_task()`.
- **Using `asyncio.all_tasks()` to find REPL tasks:** `all_tasks()` includes prompt_toolkit internal tasks, asyncio internals, etc. Only `self.tasks` contains tasks the REPL created. Filter by the set, not by `all_tasks()`.
- **Making the toolbar callback expensive:** The toolbar renders on every keypress and redraw. Widgets must return quickly. CPU-intensive widgets should cache their result and refresh on a timer, not recompute every render.
- **Storing `asyncio.Task` objects in the session store:** Tasks are not serializable. Store task names and lifecycle events (created, cancelled, completed) as strings, not task objects.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Task selection dialog | Custom prompt_toolkit layout with selectable list | `checkboxlist_dialog(values=...)` | Already proven in channel toggle. Handles keyboard navigation, Enter/Esc, scrolling. |
| Double-press detection | Custom signal handler with threading.Timer | `time.monotonic()` comparison in key binding handler | Simple timestamp comparison is sufficient. No threads, no timers, no signal complexity. |
| System metrics (CPU, memory) | Custom `/proc` parser or ctypes bindings | `os.getloadavg()` + `resource.getrusage()` | Stdlib, cross-platform (Unix), sufficient for toolbar display. psutil can be added if needed. |
| Task lifecycle tracking | Custom task registry with states | `set[asyncio.Task]` + `add_done_callback(set.discard)` | asyncio.Task already tracks state (pending, cancelled, done). The set is the registry. |
| Configurable toolbar | Toolbar format string parser | Callable widgets returning style tuples | prompt_toolkit's toolbar protocol IS style tuples. Callables compose naturally. No parsing needed. |

**Key insight:** Phase 19 is primarily a wiring phase. asyncio already provides task management (`create_task`, `cancel`, `get_name`, `done_callback`). prompt_toolkit already provides interrupt handling (key bindings) and dialog UI (checkboxlist_dialog). The novel code is the glue: tracking tasks in a set, routing interrupts to the right action, and the toolbar widget protocol.

## Common Pitfalls

### Pitfall 1: SIGINT During Task Execution vs. At Prompt

**What goes wrong:** Developer assumes prompt_toolkit key bindings handle Ctrl-C everywhere. They don't -- key bindings only fire inside `prompt_async()`. During task execution (between prompts), SIGINT raises `KeyboardInterrupt` via Python's default handler.

**Why it happens:** prompt_toolkit installs a SIGINT handler that routes to `key_processor.send_sigint()`. But the key processor only processes keys when the Application is running. After `prompt_async()` returns, the Application is no longer running. The SIGINT handler is technically still installed but `send_sigint` has no effect because there's no active key processing loop.

**How to avoid:** Handle interrupts in TWO places:
1. In the key binding (`c-c`/`<sigint>`): for interrupts at the prompt
2. In the REPL loop's `except KeyboardInterrupt`: for interrupts during task execution

The key binding handler checks `self.tasks` and shows the menu. The REPL loop catch cancels the current task and returns to prompt.

**Warning signs:** Kill menu never appears when tasks are running, because the interrupt bypasses key bindings.

### Pitfall 2: Race Between Task Completion and Kill Menu

**What goes wrong:** User presses Ctrl-C, kill menu shows 3 tasks. While menu is displayed, task completes normally. User selects the completed task. `task.cancel()` is called on a finished task (no-op, but confusing).

**Why it happens:** The kill menu is async (dialog). Tasks continue executing while the dialog is open.

**How to avoid:** Cancelling a finished task is a no-op in asyncio -- it doesn't raise an error. This is safe. The `done_callback` will have already removed it from `self.tasks`. The dialog's selected value is the task object; if it's no longer in `self.tasks`, that's fine -- `cancel()` on a done task does nothing. No special handling needed.

**Warning signs:** User confusion when a task listed in the menu has already completed by the time they confirm.

### Pitfall 3: Toolbar Widgets That Raise Exceptions

**What goes wrong:** A user-registered toolbar widget raises an exception. The toolbar render fails, and prompt_toolkit may display an error or crash.

**Why it happens:** User code is unpredictable. A widget that reads `os.getloadavg()` works on macOS but raises `OSError` on Windows. A widget referencing a namespace variable that was deleted fails with `NameError`.

**How to avoid:** Wrap each widget call in try/except in `ToolbarConfig.render()`. On error, display `[name:err]` in red instead of crashing. This is shown in the Pattern 4 code example.

**Warning signs:** Toolbar goes blank or prompt_toolkit error traceback after registering a custom widget.

### Pitfall 4: Task Set Mutation During Iteration

**What goes wrong:** Iterating `self.tasks` to cancel all tasks while a `done_callback` removes a task from the set, causing `RuntimeError: Set changed size during iteration`.

**Why it happens:** `task.cancel()` schedules cancellation. If the task's `done_callback` fires synchronously (it shouldn't in asyncio, but edge cases exist), it modifies the set.

**How to avoid:** Always iterate a copy: `for task in list(self.tasks)`. The "kill all" handler already shows this pattern.

**Warning signs:** `RuntimeError: Set changed size during iteration` during Ctrl-C handling.

### Pitfall 5: Orphaned Subprocesses After Task Cancellation

**What goes wrong:** Cancelling a task that wraps `dispatch_bash()` or `AI.__call__()` (which runs a Claude CLI subprocess) cancels the Python task but does NOT kill the child process. The subprocess continues running in the background.

**Why it happens:** `asyncio.Task.cancel()` raises `CancelledError` at the next await point in the coroutine. If the coroutine is awaiting `process.communicate()`, the `CancelledError` interrupts the wait but does not signal the subprocess. The subprocess continues running with no parent waiting for it.

**How to avoid:** Wrap subprocess-based operations in try/finally that kills the process:

```python
async def _run_with_process_cleanup(coro_fn, *args):
    """Wrapper ensuring subprocess cleanup on cancellation."""
    try:
        return await coro_fn(*args)
    except asyncio.CancelledError:
        # Kill any subprocesses that were started
        # (Implementation depends on whether the coroutine exposes its process)
        raise
```

For `AI.__call__`, the subprocess is created inside the method. The existing timeout path already calls `process.kill()`. Add the same in a `finally` or `except CancelledError` block. For `dispatch_bash`, same pattern with `proc.kill()`.

**Warning signs:** After killing an AI task, `ps aux | grep claude` still shows the subprocess running.

### Pitfall 6: Refresh Interval for Toolbar Dynamic Updates

**What goes wrong:** Toolbar shows stale task count or CPU load because it only refreshes on user input (keypress).

**Why it happens:** prompt_toolkit's `bottom_toolbar` callable is only re-evaluated on redraw, which happens on keypress or explicit `invalidate()`. Between keypresses, the toolbar is static.

**How to avoid:** Use `refresh_interval` parameter on the PromptSession. Setting `refresh_interval=1.0` causes prompt_toolkit to redraw every second, updating the toolbar. This is the documented mechanism for live-updating toolbars. Already a parameter on the existing PromptSession.

```python
self.session = PromptSession(
    ...,
    refresh_interval=1.0,  # Refresh toolbar every second
)
```

**Warning signs:** Task count in toolbar doesn't update until user presses a key.

## Code Examples

### Complete Interrupt Handler

```python
import time

def _build_key_bindings(shell: CortexShell) -> KeyBindings:
    kb = KeyBindings()
    _last_sigint = [0.0]
    DOUBLE_PRESS_THRESHOLD = 0.4

    @kb.add("c-c", eager=True)
    @kb.add("<sigint>")
    def handle_interrupt(event):
        """Route Ctrl-C based on task state and press timing."""
        now = time.monotonic()
        elapsed = now - _last_sigint[0]
        _last_sigint[0] = now

        if not shell.tasks:
            # REPL-12: no tasks, exit
            event.app.exit(exception=KeyboardInterrupt())
            return

        if elapsed < DOUBLE_PRESS_THRESHOLD:
            # REPL-11: double press, kill all
            for task in list(shell.tasks):
                task.cancel()
            shell.router.write("debug", f"killed all {len(shell.tasks)} tasks", mode="DEBUG")
            return

        # REPL-10: single press, show menu
        event.app.create_background_task(_show_kill_menu(shell))

    # ... other existing bindings (s-tab, enter, escape+enter, c-o) ...
    return kb


async def _show_kill_menu(shell: CortexShell) -> None:
    """Checkbox dialog for selective task killing."""
    tasks = list(shell.tasks)
    if not tasks:
        return
    values = [(t, t.get_name()) for t in tasks]
    result = await checkboxlist_dialog(
        title="Running Tasks",
        text="Select tasks to kill:",
        values=values,
    ).run_async()
    if result:
        for task in result:
            task.cancel()
        shell.router.write("debug", f"killed {len(result)} task(s)", mode="DEBUG")
```

### Task Tracking in REPL Loop

```python
async def run(self) -> None:
    with patch_stdout():
        while True:
            try:
                text = await self.session.prompt_async()
            except KeyboardInterrupt:
                # At prompt with no tasks -- exit (REPL-12)
                # (If tasks exist, key binding handled it already)
                self.store.close()
                return
            except EOFError:
                await self._shutdown()
                return

            if not text.strip():
                continue
            self.store.record(self.mode.value, "repl", "input", text)

            try:
                await self._dispatch(text)
            except KeyboardInterrupt:
                # During execution: cancel current tasks, return to prompt
                for task in list(self.tasks):
                    task.cancel()
                self.router.write("debug", "interrupted", mode="DEBUG")
            except asyncio.CancelledError:
                self.router.write("debug", "cancelled", mode="DEBUG")


def _track_task(self, coro, *, name: str) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    self.tasks.add(task)
    task.add_done_callback(self.tasks.discard)
    return task


async def _dispatch(self, text: str) -> None:
    """Dispatch input to the current mode handler."""
    if self.mode == Mode.PY:
        # PY mode: execute directly (not tracked -- synchronous-ish)
        result, captured = await async_exec(text, self.namespace)
        if captured:
            self.router.write("py", captured.rstrip("\n"), mode="PY", metadata={"type": "stdout"})
        if result is not None:
            self.router.write("py", repr(result), mode="PY", metadata={"type": "expr_result"})

    elif self.mode == Mode.NL:
        task = self._track_task(self.ai(text), name=f"ai:{text[:30]}")
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            tb = traceback.format_exc()
            self.router.write("ai", tb.rstrip("\n"), mode="NL", metadata={"type": "error"})

    elif self.mode == Mode.GRAPH:
        graph = self.namespace.get("graph")
        if graph:
            task = self._track_task(
                channel_arun(graph, text, self.router),
                name=f"graph:{text[:30]}",
            )
            try:
                result = await task
                if result and result.trace:
                    self.namespace["_trace"] = result.trace
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                trace = getattr(exc, "trace", None)
                if trace:
                    self.namespace["_trace"] = trace
                tb = traceback.format_exc()
                self.router.write("graph", tb.rstrip("\n"), mode="GRAPH", metadata={"type": "error"})
        else:
            self.router.write("graph", "(no graph loaded)", mode="GRAPH")

    elif self.mode == Mode.BASH:
        task = self._track_task(dispatch_bash(text), name=f"bash:{text[:30]}")
        try:
            stdout, stderr = await task
            if stdout:
                self.router.write("bash", stdout.rstrip("\n"), mode="BASH")
            if stderr:
                self.router.write("bash", stderr.rstrip("\n"), mode="BASH", metadata={"type": "stderr"})
        except asyncio.CancelledError:
            pass
```

### ToolbarConfig with Built-in Widgets

```python
# bae/repl/toolbar.py

from __future__ import annotations

import os
from typing import Callable

ToolbarWidget = Callable[[], list[tuple[str, str]]]


class ToolbarConfig:
    """User-configurable toolbar with named widgets.

    toolbar.add("name", fn)   -- register widget
    toolbar.remove("name")    -- unregister widget
    toolbar.widgets            -- list widget names
    """

    def __init__(self) -> None:
        self._widgets: dict[str, ToolbarWidget] = {}
        self._order: list[str] = []

    def add(self, name: str, widget: ToolbarWidget) -> None:
        if name not in self._widgets:
            self._order.append(name)
        self._widgets[name] = widget

    def remove(self, name: str) -> None:
        self._widgets.pop(name, None)
        if name in self._order:
            self._order.remove(name)

    @property
    def widgets(self) -> list[str]:
        return list(self._order)

    def render(self) -> list[tuple[str, str]]:
        parts: list[tuple[str, str]] = []
        for name in self._order:
            fn = self._widgets.get(name)
            if fn:
                try:
                    parts.extend(fn())
                except Exception:
                    parts.append(("fg:red", f" [{name}:err] "))
        return parts

    def __repr__(self) -> str:
        names = ", ".join(self._order)
        return f"toolbar -- .add(name, fn), .remove(name). widgets: [{names}]"


def make_mode_widget(shell) -> ToolbarWidget:
    """Built-in widget: current mode name."""
    from bae.repl.modes import MODE_NAMES
    return lambda: [("class:toolbar.mode", f" {MODE_NAMES[shell.mode]} ")]


def make_tasks_widget(shell) -> ToolbarWidget:
    """Built-in widget: running task count (hidden when zero)."""
    def widget():
        n = len(shell.tasks)
        if n == 0:
            return []
        return [("class:toolbar.tasks", f" {n} task{'s' if n != 1 else ''} ")]
    return widget


def make_cwd_widget() -> ToolbarWidget:
    """Built-in widget: current working directory."""
    def widget():
        cwd = os.getcwd()
        home = os.path.expanduser("~")
        if cwd.startswith(home):
            cwd = "~" + cwd[len(home):]
        return [("class:toolbar.cwd", f" {cwd} ")]
    return widget
```

### Subprocess Cleanup on Cancellation

```python
# In bae/repl/ai.py, modify AI.__call__:

async def __call__(self, prompt: str) -> str:
    """NL conversation with namespace context via Claude CLI."""
    context = _build_context(self._namespace)
    full_prompt = f"{context}\n\n{prompt}" if context else prompt

    cmd = [...]  # existing command construction

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=self._timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(f"AI timed out after {self._timeout}s")
    except asyncio.CancelledError:
        process.kill()
        await process.wait()
        raise

    # ... rest of existing code
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bare `asyncio.gather()` for concurrent tasks | `asyncio.TaskGroup` (Python 3.11+) for structured concurrency | Python 3.11 (2022) | TaskGroup auto-cancels siblings on failure. Available on 3.14. |
| `signal.signal(SIGINT, handler)` for interrupt handling | prompt_toolkit key bindings for `<sigint>` / `c-c` | prompt_toolkit 3.0 | Integrated with terminal state, raw mode, key processor. |
| Static bottom toolbar | Dynamic toolbar with `refresh_interval` and callable | prompt_toolkit 3.0 | Re-evaluates callable each redraw cycle. |
| `asyncio.get_event_loop()` | `asyncio.get_running_loop()` | Python 3.10 (deprecated old) | Correct API for accessing loop inside async code. |
| Manual task tracking | `Task.set_name()` / `Task.get_name()` (Python 3.7+) | Python 3.7 (2018) | Named tasks for debugging and display. |

**Deprecated/outdated:**
- `asyncio.ensure_future()` -- use `asyncio.create_task()` since Python 3.7
- `asyncio.get_event_loop()` -- use `get_running_loop()` inside async code
- `loop.create_task()` -- use module-level `asyncio.create_task()` for simplicity

## Open Questions

1. **Should PY mode execution be tracked as a task?**
   - What we know: PY mode uses `async_exec()` which compiles and executes user code. It's awaited directly in the REPL loop. Wrapping it in `create_task()` would make it cancellable via the kill menu.
   - What's unclear: Whether users want to cancel in-progress Python execution. Python doesn't support cooperative cancellation of synchronous code -- only await points can be cancelled. A tight loop like `while True: pass` can't be cancelled via `task.cancel()`.
   - Recommendation: Track PY mode tasks for visibility in the toolbar. Cancellation will only work for async code (which hits await points). Document this limitation. Alternatively, don't track PY mode and only track NL/Graph/Bash tasks which are inherently async.

2. **Should the kill menu appear as a dialog or inline?**
   - What we know: `checkboxlist_dialog` opens a full-screen dialog that takes over the terminal. This is the same approach used for channel toggle (Ctrl-O).
   - What's unclear: Whether a lighter-weight inline display (numbered list with "type number to kill") would be better UX.
   - Recommendation: Use `checkboxlist_dialog` for consistency with channel toggle. Users already know this interaction pattern. A lighter-weight approach could be a future enhancement.

3. **What happens when the kill menu is open and another Ctrl-C arrives?**
   - What we know: The dialog has its own key bindings. Ctrl-C inside the dialog is handled by the dialog (typically dismisses it).
   - What's unclear: Whether the user expects Ctrl-C in the dialog to kill all tasks (double-press semantics) or dismiss the dialog.
   - Recommendation: Let the dialog handle its own Ctrl-C (dismiss). The double-press window only applies at the main prompt, not inside dialogs.

4. **Should toolbar refresh interval be configurable?**
   - What we know: `refresh_interval=1.0` is a reasonable default for toolbar updates.
   - What's unclear: Whether some users want faster updates (0.5s) or want to disable periodic refresh to save CPU.
   - Recommendation: Default to 1.0s. Allow users to change it: `toolbar.refresh_interval = 0.5`. This requires storing the interval on ToolbarConfig and rebuilding the session, which is complex. Simpler: hardcode 1.0s, optimize if needed. YAGNI.

## Sources

### Primary (HIGH confidence)

- Existing codebase: `bae/repl/shell.py` -- `self.tasks: set[asyncio.Task]` stub (line 76), `_shutdown()` with task cancellation (lines 130-140), KeyboardInterrupt handling in REPL loop (line 148), `_build_key_bindings()` function (lines 38-67)
- Existing codebase: `bae/repl/channels.py` -- `toggle_channels()` using `checkboxlist_dialog` (lines 143-157), proven dialog pattern
- Existing codebase: `bae/repl/ai.py` -- `AI.__call__` subprocess with timeout but no cancellation cleanup (lines 81-101)
- prompt_toolkit source: `application.py` -- SIGINT handler routes to `key_processor.send_sigint()` (line 814), `create_background_task()` API (lines 1132-1156)
- prompt_toolkit source: `prompt.py` -- Default `c-c`/`<sigint>` binding calls `event.app.exit(exception=KeyboardInterrupt())` (lines 835-839), `interrupt_exception` parameter (line 423), `refresh_interval` parameter
- prompt_toolkit source: `key_bindings.py` -- `eager` parameter for binding priority (line 255)
- Python 3.14 stdlib: `asyncio.Task.cancel()`, `.get_name()`, `.set_name()`, `.add_done_callback()`, `create_task()` -- all verified working on 3.14.3
- Python 3.14 stdlib: `time.monotonic()`, `os.getloadavg()`, `resource.getrusage()` -- verified on macOS 3.14.3
- Phase 14 research: Pitfall #6 (Ctrl-C behavior depends on context) -- documents the two-path interrupt model
- Phase 14 plan 02 summary: "Task set (`self.tasks`) is wired for shutdown but not yet populated -- Phase 19 will add background task management"

### Secondary (MEDIUM confidence)

- Research PITFALLS.md: Pitfall #4 (asyncio.gather() exception handling destroys sibling tasks) -- documents task leak prevention strategies relevant to cancellation cleanup
- Research ARCHITECTURE.md: Event loop sovereignty model -- cortex owns the loop, all execution cooperative

### Tertiary (LOW confidence)

- Dialog UX during task execution: It's unclear how well the checkboxlist_dialog behaves when tasks are actively producing output via channels. The dialog takes over the terminal, which may conflict with `patch_stdout()` output. Needs empirical testing.

## Metadata

**Confidence breakdown:**
- Task tracking: HIGH -- `asyncio.create_task()` + `set` + `done_callback` is the standard pattern. Verified on 3.14.3.
- Interrupt handling: HIGH -- Two-path model (key bindings at prompt, KeyboardInterrupt during execution) verified from prompt_toolkit source. Key binding override mechanism understood.
- Kill menu: HIGH -- `checkboxlist_dialog` already proven in the codebase (channel toggle).
- Configurable toolbar: HIGH -- prompt_toolkit's `bottom_toolbar` callable + `refresh_interval` is the documented mechanism. Widget protocol is a clean Python pattern.
- Subprocess cleanup: MEDIUM -- Adding `except CancelledError: process.kill()` is straightforward but requires modifying `ai.py` and potentially `bash.py`. Needs care to avoid breaking existing behavior.
- Dialog interaction during output: LOW -- Untested interaction between checkboxlist_dialog and background task output via patch_stdout.

**Research date:** 2026-02-13
**Valid until:** 2026-03-15 (prompt_toolkit 3.0 stable, asyncio stdlib stable)
