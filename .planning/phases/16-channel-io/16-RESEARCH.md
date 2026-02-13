# Phase 16: Channel I/O - Research

**Researched:** 2026-02-13
**Domain:** Output multiplexing with labeled channels, TUI toggle, debug logging, graph wrapper pattern
**Confidence:** HIGH

## Summary

Phase 16 introduces a channel system that wraps all REPL output in labeled, color-coded channels (e.g., `[py]`, `[graph]`, `[ai]`, `[bash]`). Users can toggle channel visibility via a TUI select menu, access channels as Python objects in the namespace, enable debug logging to file, and have graph execution output routed through channels via a wrapper around `graph.arun()` without modifying bae source.

The core technical challenge is building a `Channel` class that acts as both a write destination (for output routing) and a namespace-accessible object (for user inspection). Each channel wraps `print_formatted_text()` from prompt_toolkit to render color-coded prefixes, records to `SessionStore`, and conditionally suppresses output based on visibility state. The channel system is a thin orchestration layer -- it does not replace existing I/O, it interposes on it. The existing `store.record()` calls in `shell.py` are replaced by `channel.write()` calls that internally handle both display and storage.

For the graph wrapper (CHAN-05), the approach is a `channel_arun()` async function that wraps `graph.arun()` -- capturing its return value and any logging output, routing both through the `[graph]` channel. Since `graph.py` uses `logging.getLogger(__name__)` for debug output, the wrapper can temporarily attach a logging handler that routes to the channel. No modifications to `bae/graph.py` are needed.

**Primary recommendation:** Build `bae/repl/channels.py` with a `Channel` dataclass and a `ChannelRouter` that manages channel registry, visibility state, and output dispatch. Hook into `shell.py` by replacing direct `print()` / `store.record()` calls with `router.write(channel_name, content)`. Use `checkboxlist_dialog(...).run_async()` for the TUI toggle menu, triggered by a new keybinding.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `prompt_toolkit` | 3.0.52 (installed) | `print_formatted_text`, `FormattedText`, `checkboxlist_dialog`, `Style` | Already the REPL foundation. Native color output, dialog widgets, async support. |
| `logging` (stdlib) | 3.14 | `FileHandler` for debug log capture, `getLogger` for graph output interception | Standard Python logging. Graph module already uses `logging.getLogger(__name__)`. |
| `sqlite3` (stdlib) | 3.51.2 (bundled) | `SessionStore.record()` for persisting channel output | Already integrated from Phase 15. Channels record through the existing store. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` (stdlib) | 3.14 | `Channel` and `ChannelRouter` as lightweight data holders | Always. Channels are simple state + behavior, not Pydantic models. |
| `logging.handlers` (stdlib) | 3.14 | `FileHandler` for debug mode log capture | When user enables debug logging (CHAN-04). |
| `pathlib` (stdlib) | 3.14 | Debug log file path (`.bae/debug.log`) | When debug mode is enabled. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom `Channel` class | Python `logging.Logger` per channel | Logging framework has too much ceremony (formatters, handlers, propagation) for what is essentially "print with a prefix." Channels need visibility toggling and namespace access, which logging does not provide. |
| `checkboxlist_dialog` for TUI toggle | Custom keybinding-driven toggle (Shift+1/2/3/4) | Per-key toggles don't scale and lack discoverability. A checkbox dialog shows all channels with current state. The dialog approach matches prompt_toolkit's widget ecosystem. |
| `print_formatted_text` for colored output | ANSI escape codes via raw `print()` | Raw ANSI works but bypasses prompt_toolkit's output management. `print_formatted_text` integrates with `patch_stdout` and handles terminal compatibility. |
| `FileHandler` for debug log | `RotatingFileHandler` | Debug logs are session-scoped. Rotation is unnecessary -- a single file per session suffices. If size becomes a concern, add rotation later. |

**Installation:**
```bash
# No new dependencies. All stdlib + existing prompt_toolkit.
```

## Architecture Patterns

### Recommended Project Structure

```
bae/repl/
    channels.py     # Channel, ChannelRouter -- output multiplexing layer
    shell.py        # Modified: uses router.write() instead of print()/store.record()
    store.py        # Unchanged: channels call store.record() internally
    exec.py         # Unchanged: returns (result, captured_stdout) as before
    bash.py         # Unchanged: returns (stdout, stderr) as before
    modes.py        # Unchanged: Mode enum
    complete.py     # Unchanged: tab completion
```

### Pattern 1: Channel as Write Destination

**What:** A `Channel` is a named output destination with a color, visibility flag, and reference to the store and output function. Writing to a channel formats the output with a color-coded prefix, optionally displays it (if visible), and always records to the store.

**When to use:** Every output operation in the REPL.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText

if TYPE_CHECKING:
    from bae.repl.store import SessionStore


@dataclass
class Channel:
    """A labeled output stream with color-coded display and store integration."""

    name: str
    color: str
    visible: bool = True
    store: SessionStore | None = None
    _buffer: list[str] = field(default_factory=list, repr=False)

    @property
    def label(self) -> str:
        return f"[{self.name}]"

    def write(self, content: str, *, mode: str = "", direction: str = "output",
              metadata: dict | None = None) -> None:
        """Write content through this channel."""
        # Always record to store
        if self.store:
            self.store.record(mode or self.name.upper(), self.name, direction, content, metadata)
        # Always buffer
        self._buffer.append(content)
        # Display only if visible
        if self.visible:
            self._display(content)

    def _display(self, content: str) -> None:
        """Render content with color-coded channel prefix."""
        for line in content.splitlines():
            text = FormattedText([
                (f'{self.color} bold', self.label),
                ('', ' '),
                ('', line),
            ])
            print_formatted_text(text)

    def __repr__(self) -> str:
        n = len(self._buffer)
        vis = "visible" if self.visible else "hidden"
        return f"Channel({self.name!r}, {vis}, {n} entries)"
```

**Confidence:** HIGH -- `FormattedText` with hex color tuples verified on prompt_toolkit 3.0.52. `print_formatted_text` works within `patch_stdout` context.

### Pattern 2: ChannelRouter as Registry

**What:** The `ChannelRouter` holds all channels, provides `write(channel_name, content)` as the single output entry point, and exposes a namespace-friendly object where `channels.py` accesses the `py` channel.

**When to use:** Owned by `CortexShell`, replaces direct print/store calls.

```python
@dataclass
class ChannelRouter:
    """Registry of output channels with visibility control."""

    _channels: dict[str, Channel] = field(default_factory=dict, repr=False)
    debug_handler: logging.FileHandler | None = field(default=None, repr=False)

    def register(self, name: str, color: str, store: SessionStore | None = None) -> Channel:
        """Register a new channel."""
        ch = Channel(name=name, color=color, store=store)
        self._channels[name] = ch
        return ch

    def write(self, channel: str, content: str, **kwargs) -> None:
        """Write to a named channel."""
        ch = self._channels.get(channel)
        if ch:
            ch.write(content, **kwargs)
            # Debug logging
            if self.debug_handler:
                record = logging.LogRecord(
                    name=channel, level=logging.DEBUG, pathname="",
                    lineno=0, msg=content, args=(), exc_info=None,
                )
                self.debug_handler.emit(record)

    def __getattr__(self, name: str) -> Channel:
        """Allow channels.py, channels.graph, etc."""
        if name.startswith('_'):
            raise AttributeError(name)
        if name in self._channels:
            return self._channels[name]
        raise AttributeError(f"No channel {name!r}")

    @property
    def visible(self) -> list[str]:
        return [n for n, ch in self._channels.items() if ch.visible]

    @property
    def all(self) -> list[str]:
        return list(self._channels.keys())
```

**Confidence:** HIGH -- standard Python `__getattr__` pattern for namespace-friendly attribute access.

### Pattern 3: TUI Toggle via checkboxlist_dialog

**What:** A keybinding triggers `checkboxlist_dialog(...).run_async()` to let the user toggle channel visibility. The dialog shows all channels with their current visibility as pre-selected values. After the user confirms, channel visibility is updated.

**When to use:** User presses a dedicated key (e.g., Ctrl+O or a function key) to open the channel toggle menu.

```python
from prompt_toolkit.shortcuts import checkboxlist_dialog
from prompt_toolkit.application import run_in_terminal

async def toggle_channels(router: ChannelRouter) -> None:
    """Show a checkbox dialog for channel visibility toggles."""
    values = [(name, f"[{name}] channel") for name in router.all]
    default = router.visible

    # run_in_terminal suspends the current prompt, shows the dialog, then resumes
    result = await checkboxlist_dialog(
        title="Channel Visibility",
        text="Toggle which channels are displayed:",
        values=values,
        default_values=default,
    ).run_async()

    if result is not None:  # None means cancelled
        for name in router.all:
            router._channels[name].visible = name in result
```

**Confidence:** HIGH -- `checkboxlist_dialog` returns a `prompt_toolkit.Application` with `run_async()`. Verified: `checkboxlist_dialog(values=...).run_async()` returns an awaitable. The `default_values` parameter controls pre-selected items.

### Pattern 4: Graph Wrapper (No Source Modification)

**What:** An async wrapper function around `graph.arun()` that captures logging output and routes the result through the `[graph]` channel. Uses a temporary logging handler attached to the `bae.graph` logger.

**When to use:** GRAPH mode execution in `shell.py`.

```python
import logging
from io import StringIO


async def channel_arun(graph, start_node, router, *, lm=None, max_iters=10):
    """Wrap graph.arun() to route output through the [graph] channel."""
    # Capture bae.graph logger output
    graph_logger = logging.getLogger("bae.graph")
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    graph_logger.addHandler(handler)
    old_level = graph_logger.level
    graph_logger.setLevel(logging.DEBUG)

    try:
        result = await graph.arun(start_node, lm=lm, max_iters=max_iters)
    finally:
        graph_logger.removeHandler(handler)
        graph_logger.setLevel(old_level)

    # Route captured log output through [graph] channel
    captured = buf.getvalue()
    if captured:
        router.write("graph", captured.rstrip(), mode="GRAPH", direction="output",
                      metadata={"type": "log"})

    # Route result through [graph] channel
    if result and result.trace:
        terminal = result.trace[-1]
        router.write("graph", repr(terminal), mode="GRAPH", direction="output",
                      metadata={"type": "result"})

    return result
```

**Confidence:** HIGH -- `graph.py` uses `logging.getLogger("bae.graph")` (line 18). Attaching a temporary handler is standard Python logging. The wrapper is a pure function that calls `graph.arun()` and processes its outputs. Zero modifications to `bae/graph.py`.

### Pattern 5: Debug Mode File Logging

**What:** When debug mode is enabled, a `logging.FileHandler` is attached to the router. All channel writes are additionally logged to `.bae/debug.log` with timestamps and channel labels.

**When to use:** User calls `channels.debug(True)` or a CLI flag.

```python
import logging
from pathlib import Path


def enable_debug(router: ChannelRouter, log_dir: Path | None = None) -> None:
    """Enable debug logging to file."""
    log_path = (log_dir or Path.cwd() / ".bae") / "debug.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    router.debug_handler = handler


def disable_debug(router: ChannelRouter) -> None:
    """Disable debug logging."""
    if router.debug_handler:
        router.debug_handler.close()
        router.debug_handler = None
```

**Confidence:** HIGH -- stdlib `logging.FileHandler` is well-understood.

### Anti-Patterns to Avoid

- **Modifying `bae/graph.py`:** The requirement is explicit -- wrapper pattern only. Never add channel awareness to graph.py, resolver.py, or node.py.
- **Replacing `sys.stdout` globally for channels:** `async_exec` already does stdout capture via StringIO swap. Channels should receive the captured output after `async_exec` returns, not by competing for sys.stdout.
- **Making Channel a subclass of io.TextIOBase:** Channels are not file-like objects. They are write-and-display destinations. Implementing the full TextIOBase protocol (readable, seekable, etc.) is unnecessary complexity.
- **One logging.Logger per channel:** Channels need visibility toggling and namespace access. Python logging does not support "hide this logger's output from the console." Using loggers conflates two different systems.
- **Storing channel config in the database:** Channel visibility is ephemeral session state, not persisted data. A dict in memory is sufficient. If persistence is needed later, add it then.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Color-coded terminal output | ANSI escape code builder | `prompt_toolkit.print_formatted_text` + `FormattedText` | Handles terminal compatibility, works with `patch_stdout`, supports hex colors and named styles. |
| Channel toggle TUI | Custom ncurses/checkbox renderer | `prompt_toolkit.shortcuts.checkboxlist_dialog` | Full checkbox widget with keyboard navigation, styling, async support. Verified on 3.0.52. |
| Debug log file rotation | Custom file rotation logic | `logging.handlers.RotatingFileHandler` | If rotation is ever needed, it's one parameter change from `FileHandler`. |
| Log output interception | Custom monkey-patching of logger methods | `logging.Handler` subclass + `logger.addHandler()` | Standard Python pattern for intercepting log output. Used by every major framework. |

**Key insight:** Channel I/O is a thin orchestration layer. The display is prompt_toolkit's `print_formatted_text`. The persistence is the existing `SessionStore.record()`. The toggle UI is prompt_toolkit's `checkboxlist_dialog`. The debug capture is stdlib `logging.FileHandler`. Channels glue these together with a name, color, and visibility flag.

## Common Pitfalls

### Pitfall 1: Output Ordering Under patch_stdout

**What goes wrong:** Output from channels mixes with prompt_toolkit's `patch_stdout` rendering, causing interleaved or duplicated lines.

**Why it happens:** `patch_stdout()` replaces `sys.stdout` with a proxy that buffers output and renders it above the prompt. If channel output uses both `print()` (which goes through the proxy) and `print_formatted_text()` (which uses prompt_toolkit's renderer directly), output can appear in wrong order.

**How to avoid:** Use `print_formatted_text()` exclusively for all channel output. Never use bare `print()` for output that goes through channels. The existing `patch_stdout()` context in `CortexShell.run()` already wraps the REPL loop -- `print_formatted_text()` integrates with it correctly.

**Warning signs:** Lines appearing below the prompt instead of above, or duplicate output.

### Pitfall 2: checkboxlist_dialog Blocking the Event Loop

**What goes wrong:** Calling `checkboxlist_dialog(...).run()` (sync) inside the async REPL hangs because there's already a running event loop.

**Why it happens:** `.run()` calls `asyncio.run()` internally, which fails inside an existing event loop.

**How to avoid:** Always use `.run_async()`. The dialog returned by `checkboxlist_dialog()` is a `prompt_toolkit.Application`, and `run_async()` is an awaitable method. In the keybinding handler, use `run_in_terminal` or invoke from an async context.

**Warning signs:** `RuntimeError: This event loop is already running` or the REPL freezing.

### Pitfall 3: Graph Logger Handler Leak

**What goes wrong:** If `channel_arun()` throws an exception after adding the temporary logging handler but before removing it, the handler accumulates on repeated calls.

**Why it happens:** Missing `finally` block around handler cleanup.

**How to avoid:** Always use `try/finally` to add and remove the handler. The code example above demonstrates this pattern.

**Warning signs:** Duplicate log lines appearing after graph errors.

### Pitfall 4: Channel Write During async_exec stdout Capture

**What goes wrong:** During `async_exec`, `sys.stdout` is swapped to a `StringIO` buffer. If channel output tries to use `print_formatted_text()` during this window, it may write to the wrong destination or fail.

**Why it happens:** `async_exec` captures stdout for the duration of code execution. If the executed code triggers channel writes, those writes hit the StringIO buffer, not the terminal.

**How to avoid:** Channel writes should happen _after_ `async_exec` returns, not during. The current flow is: `async_exec` returns `(result, captured_stdout)` -> shell routes captured_stdout through the channel. This ordering is correct. Do not call `router.write()` from inside `async_exec`.

**Warning signs:** Channel prefixes appearing in captured stdout, or missing channel output during py execution.

### Pitfall 5: Namespace Collision Between `channels` and `store`

**What goes wrong:** Both `channels` and `store` are in the namespace. If a user assigns `channels = something`, the router is lost.

**Why it happens:** Shared namespace allows user reassignment.

**How to avoid:** This is a conscious design tradeoff (same as `store`). Document that `channels` is a reserved name. Do not try to prevent reassignment -- it breaks the Python mental model.

**Warning signs:** `AttributeError: 'str' object has no attribute 'py'` after user does `channels = "hello"`.

## Code Examples

### Default Channel Configuration

```python
# Source: Derived from existing Mode enum colors in modes.py
# Channel names map to REPL modes plus additional semantic channels

CHANNEL_DEFAULTS = {
    "py":    {"color": "#87ff87"},   # Green -- matches Mode.PY color
    "graph": {"color": "#ffaf87"},   # Orange -- matches Mode.GRAPH color
    "ai":    {"color": "#87d7ff"},   # Blue -- matches Mode.NL color
    "bash":  {"color": "#d7afff"},   # Purple -- matches Mode.BASH color
    "debug": {"color": "#808080"},   # Grey -- for internal/debug output
}
```

### Shell Integration (Replacing print/store with channels)

```python
# Current shell.py (Phase 15):
#   print(captured, end="")
#   self.store.record("PY", "repl", "output", captured, {"type": "stdout"})
#
# After Phase 16:
#   self.router.write("py", captured, mode="PY", metadata={"type": "stdout"})

# Current:
#   stdout, stderr = await dispatch_bash(text)
#   if stdout:
#       self.store.record("BASH", "stdout", "output", stdout)
#
# After Phase 16:
#   stdout, stderr = await dispatch_bash(text)
#   if stdout:
#       self.router.write("bash", stdout, mode="BASH")
#   if stderr:
#       self.router.write("bash", stderr, mode="BASH", metadata={"type": "stderr"})
```

### Keybinding for Channel Toggle

```python
# Source: prompt_toolkit keybinding pattern from existing shell.py

@kb.add("c-o")  # Ctrl+O opens channel toggle
def open_channel_toggle(event):
    """Open channel visibility toggle dialog."""
    async def _toggle():
        await toggle_channels(shell.router)
        event.app.invalidate()
    event.app.create_background_task(_toggle())
```

### Channels as Namespace Objects (CHAN-03)

```python
# In CortexShell.__init__():
self.router = ChannelRouter()
for name, cfg in CHANNEL_DEFAULTS.items():
    self.router.register(name, cfg["color"], store=self.store)
self.namespace["channels"] = self.router

# User can then:
#   py> channels.py
#   Channel('py', visible, 12 entries)
#
#   py> channels.py.visible = False
#   py> channels.py.visible
#   False
#
#   py> channels.graph._buffer[-1]
#   'GraphResult(trace=[...])'
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw `print()` for all output | `print_formatted_text(FormattedText(...))` for styled output | prompt_toolkit 3.0 (2020) | Terminal-compatible color output without raw ANSI codes |
| Global logging config for debug | Per-session FileHandler attached/detached | Always standard | Clean debug capture without polluting global logging state |
| Inline ANSI color codes | FormattedText tuple format `(style, text)` | prompt_toolkit 2.0+ | Structured style representation, theme-able |
| `asyncio.run()` for dialogs | `dialog.run_async()` awaitable | prompt_toolkit 3.0 | Dialogs can run inside existing event loops |

**Deprecated/outdated:**
- `prompt_toolkit.shortcuts.confirm()` -- exists but not what we need; checkboxlist_dialog is the right widget for multi-toggle
- `prompt_toolkit.layout.containers.Window` (low-level) -- use the `checkboxlist_dialog` shortcut instead of building a custom checkbox UI

## Open Questions

1. **Keybinding for channel toggle menu**
   - What we know: Shift+Tab is taken (mode cycling). Ctrl+O is available. F-keys are available.
   - What's unclear: Which key is most discoverable and doesn't conflict with terminal emulators
   - Recommendation: Use Ctrl+O. It's mnemonic ("Output channels"), unlikely to conflict, and available in most terminals. Show it in the bottom toolbar.

2. **Should channel buffer persist across sessions?**
   - What we know: `Channel._buffer` is in-memory. Store entries persist in SQLite.
   - What's unclear: Whether `_buffer` should be populated from store on startup
   - Recommendation: No. The buffer is for current-session inspection. Historical data is in the store. YAGNI.

3. **How should multiline output be prefixed?**
   - What we know: Each line should get a `[channel]` prefix for visual clarity
   - What's unclear: Whether the first line vs all lines get the prefix
   - Recommendation: All lines get the prefix. This is how terminal multiplexers (tmux, screen) handle pane labels. Makes grep/search of debug logs unambiguous.

4. **Should the TUI dialog be modal or should it use a ConditionalContainer overlay?**
   - What we know: `checkboxlist_dialog().run_async()` is modal (suspends the prompt). `ConditionalContainer` with `FloatContainer` would be an overlay.
   - What's unclear: Whether modal interruption is acceptable UX
   - Recommendation: Start with modal (`checkboxlist_dialog().run_async()`). It's simpler, fewer moving parts, and the user explicitly invokes it. Overlay can be added later if the interruption is annoying.

5. **Interaction between channel_arun wrapper and the existing GRAPH mode stub**
   - What we know: shell.py currently has a GRAPH mode stub that prints "Not yet implemented"
   - What's unclear: Whether Phase 16 should fully implement GRAPH mode dispatch or just prepare the wrapper
   - Recommendation: Implement the wrapper function (`channel_arun`) and update the GRAPH mode handler to call it if a graph is available in the namespace. If no graph is loaded, keep the stub message but route it through the `[graph]` channel.

## Sources

### Primary (HIGH confidence)
- prompt_toolkit 3.0.52 installed in project venv -- `checkboxlist_dialog`, `FormattedText`, `print_formatted_text`, `run_async` all verified working
- [prompt_toolkit Dialogs documentation](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/dialogs.html) -- checkboxlist_dialog API
- [prompt_toolkit Printing formatted text](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/printing_text.html) -- FormattedText tuple format, HTML class, Style
- [prompt_toolkit asyncio integration](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/asyncio.html) -- run_async pattern for dialogs
- [prompt_toolkit full screen apps](https://python-prompt-toolkit.readthedocs.io/en/master/pages/full_screen_apps.html) -- FloatContainer, ConditionalContainer, run_in_terminal
- [prompt_toolkit checkbox_dialog.py example](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/dialogs/checkbox_dialog.py) -- verified working pattern
- [prompt_toolkit asyncio-prompt.py example](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/asyncio-prompt.py) -- patch_stdout + create_task pattern
- [Python logging.handlers docs](https://docs.python.org/3/library/logging.handlers.html) -- FileHandler, RotatingFileHandler
- Existing codebase: `bae/graph.py` line 18 uses `logging.getLogger(__name__)` -- verified interception point
- Existing codebase: `bae/repl/shell.py` -- all output points identified (PY, BASH, NL, GRAPH modes)
- Existing codebase: `bae/repl/store.py` -- `SessionStore.record()` signature verified
- Runtime verification: `FormattedText([('#87ff87 bold', '[py]'), ('', ' '), ('', 'x = 42')])` renders correctly
- Runtime verification: `checkboxlist_dialog(values=...).run_async()` returns an awaitable

### Secondary (MEDIUM confidence)
- [prompt_toolkit issue #652](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/652) -- run_coroutine_in_terminal pattern for dialogs inside sessions
- [Python logging cookbook](https://docs.python.org/3/howto/logging-cookbook.html) -- multiple handler pattern

### Tertiary (LOW confidence)
- None. All findings verified with primary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All stdlib + existing prompt_toolkit 3.0.52. No new dependencies.
- Architecture: HIGH -- Channel/Router pattern derived directly from reading existing shell.py output points. All prompt_toolkit APIs verified working.
- Pitfalls: HIGH -- Output ordering, event loop conflicts, handler leaks, stdout capture interaction all identified from understanding the existing codebase flow.
- Graph wrapper: HIGH -- `logging.getLogger("bae.graph")` confirmed in source. Temporary handler pattern is standard Python.

**Research date:** 2026-02-13
**Valid until:** 2026-03-15 (stable stdlib + prompt_toolkit, unlikely to change)
