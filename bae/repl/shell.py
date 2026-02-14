"""CortexShell: async REPL with mode switching."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
from io import StringIO
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import DynamicCompleter
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.lexers import DynamicLexer, PygmentsLexer
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from pygments.lexers.python import PythonLexer

from bae.repl.ai import AI
from bae.repl.bash import dispatch_bash
from bae.repl.channels import CHANNEL_DEFAULTS, ChannelRouter, toggle_channels
from bae.repl.complete import NamespaceCompleter
from bae.repl.exec import async_exec
from bae.repl.modes import DEFAULT_MODE, MODE_COLORS, MODE_CYCLE, MODE_NAMES, Mode
from bae.repl.namespace import seed
from bae.repl.store import SessionStore
from bae.repl.toolbar import ToolbarConfig, make_cwd_widget, make_mode_widget, make_tasks_widget

# Register kitty keyboard protocol Shift+Enter (CSI u encoding).
# Terminals supporting the kitty protocol (Ghostty, kitty, iTerm2 CSI u mode)
# send \x1b[13;2u for Shift+Enter. Map it to Escape+Enter so the same
# "insert newline" binding handles both kitty Shift+Enter and Escape+Enter.
ANSI_SEQUENCES["\x1b[13;2u"] = (Keys.Escape, Keys.ControlM)


DOUBLE_PRESS_THRESHOLD = 0.4


async def _show_kill_menu(shell: CortexShell) -> None:
    """Show checkbox dialog to select running tasks to kill."""
    from prompt_toolkit.shortcuts import checkboxlist_dialog

    tasks = list(shell.tasks)
    if not tasks:
        return
    values = [(task, task.get_name()) for task in tasks]
    result = await checkboxlist_dialog(
        title="Kill Tasks",
        text="Select tasks to cancel:",
        values=values,
    ).run_async()
    if result is None:
        return
    for task in result:
        task.cancel()
    if result:
        shell.router.write("debug", f"killed {len(result)} tasks", mode="DEBUG")


def _build_key_bindings(shell: CortexShell) -> KeyBindings:
    """Key bindings for cortex REPL."""
    kb = KeyBindings()
    _last_sigint = [0.0]

    @kb.add("s-tab")
    def cycle_mode(event):
        """Shift+Tab cycles modes."""
        idx = MODE_CYCLE.index(shell.mode)
        shell.mode = MODE_CYCLE[(idx + 1) % len(MODE_CYCLE)]
        event.app.invalidate()

    @kb.add("enter")
    def submit(event):
        """Enter submits input."""
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def insert_newline(event):
        """Escape+Enter inserts newline (also handles kitty Shift+Enter)."""
        event.current_buffer.insert_text("\n")

    @kb.add("c-o")
    def open_channel_toggle(event):
        """Ctrl+O opens channel visibility toggle."""
        async def _toggle():
            await toggle_channels(shell.router)
            event.app.invalidate()
        event.app.create_background_task(_toggle())

    @kb.add("c-c", eager=True)
    def handle_interrupt(event):
        """Ctrl-C: exit if idle, kill-all on double-press, kill menu on single."""
        if not shell.tasks:
            event.app.exit(exception=KeyboardInterrupt())
            return
        now = time.monotonic()
        elapsed = now - _last_sigint[0]
        _last_sigint[0] = now
        if elapsed < DOUBLE_PRESS_THRESHOLD:
            for task in list(shell.tasks):
                task.cancel()
            shell.router.write("debug", f"killed all {len(shell.tasks)} tasks", mode="DEBUG")
        else:
            event.app.create_background_task(_show_kill_menu(shell))

    return kb


class CortexShell:
    """Async REPL with four modes."""

    def __init__(self) -> None:
        self.mode: Mode = DEFAULT_MODE
        self.namespace: dict = seed()
        self.tasks: set[asyncio.Task] = set()
        self.store = SessionStore(Path.cwd() / ".bae" / "store.db")
        self.namespace["store"] = self.store
        self.router = ChannelRouter()
        for name, cfg in CHANNEL_DEFAULTS.items():
            self.router.register(name, cfg["color"], store=self.store)
        self.namespace["channels"] = self.router
        from bae.lm import ClaudeCLIBackend
        self.ai = AI(lm=ClaudeCLIBackend(), router=self.router, namespace=self.namespace)
        self.namespace["ai"] = self.ai
        self.toolbar = ToolbarConfig()
        self.toolbar.add("mode", make_mode_widget(self))
        self.toolbar.add("tasks", make_tasks_widget(self))
        self.toolbar.add("cwd", make_cwd_widget())
        self.namespace["toolbar"] = self.toolbar
        self.completer = NamespaceCompleter(self.namespace)

        kb = _build_key_bindings(self)
        self.session = PromptSession(
            message=self._prompt,
            lexer=DynamicLexer(self._lexer),
            completer=DynamicCompleter(self._completer),
            multiline=True,
            bottom_toolbar=self._toolbar,
            refresh_interval=1.0,
            style=Style.from_dict({
                "bottom-toolbar": "bg:#1c1c1c #808080",
                "bottom-toolbar.text": "",
                "toolbar.mode": "bg:#303030 #ffffff bold",
                "toolbar.tasks": "fg:ansiyellow bold",
                "toolbar.cwd": "#808080",
            }),
            key_bindings=kb,
        )

    def _prompt(self):
        """Colored prompt based on current mode."""
        color = MODE_COLORS[self.mode]
        return [("fg:" + color, "> ")]

    def _completer(self):
        """Namespace completer in PY mode, none otherwise."""
        if self.mode == Mode.PY:
            return self.completer
        return None

    def _lexer(self):
        """Python lexer in PY mode, none otherwise."""
        if self.mode == Mode.PY:
            return PygmentsLexer(PythonLexer)
        return None

    def _toolbar(self):
        """Bottom toolbar rendered from ToolbarConfig widgets."""
        return self.toolbar.render()

    def _track_task(self, coro, *, name: str) -> asyncio.Task:
        """Wrap a coroutine in a tracked asyncio.Task."""
        task = asyncio.create_task(coro, name=name)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def _dispatch(self, text: str) -> None:
        """Route input to the active mode handler."""
        if self.mode == Mode.PY:
            try:
                result, captured = await async_exec(text, self.namespace)
                if captured:
                    self.router.write("py", captured.rstrip("\n"), mode="PY", metadata={"type": "stdout"})
                if result is not None:
                    output = repr(result)
                    self.router.write("py", output, mode="PY", metadata={"type": "expr_result"})
            except KeyboardInterrupt:
                pass
            except Exception:
                tb = traceback.format_exc()
                self.router.write("py", tb.rstrip("\n"), mode="PY", metadata={"type": "error"})
        elif self.mode == Mode.NL:
            task = self._track_task(self.ai(text), name=f"ai:{text[:30]}")
            try:
                await task
            except asyncio.CancelledError:
                self.router.write("debug", f"cancelled ai task", mode="DEBUG")
            except Exception:
                tb = traceback.format_exc()
                self.router.write("ai", tb.rstrip("\n"), mode="NL", metadata={"type": "error"})
        elif self.mode == Mode.GRAPH:
            graph = self.namespace.get("graph")
            if graph:
                task = self._track_task(
                    channel_arun(graph, text, self.router), name=f"graph:{text[:30]}",
                )
                try:
                    result = await task
                    if result and result.trace:
                        self.namespace["_trace"] = result.trace
                except asyncio.CancelledError:
                    self.router.write("debug", f"cancelled graph task", mode="DEBUG")
                except Exception as exc:
                    trace = getattr(exc, "trace", None)
                    if trace:
                        self.namespace["_trace"] = trace
                    tb = traceback.format_exc()
                    self.router.write("graph", tb.rstrip("\n"), mode="GRAPH", metadata={"type": "error"})
            else:
                stub = "(Graph mode stub) Not yet implemented."
                self.router.write("graph", stub, mode="GRAPH")
        elif self.mode == Mode.BASH:
            task = self._track_task(dispatch_bash(text), name=f"bash:{text[:30]}")
            try:
                stdout, stderr = await task
            except asyncio.CancelledError:
                self.router.write("debug", f"cancelled bash task", mode="DEBUG")
                return
            except Exception:
                tb = traceback.format_exc()
                self.router.write("bash", tb.rstrip("\n"), mode="BASH", metadata={"type": "error"})
                return
            if stdout:
                self.router.write("bash", stdout.rstrip("\n"), mode="BASH")
            if stderr:
                self.router.write("bash", stderr.rstrip("\n"), mode="BASH", metadata={"type": "stderr"})

    async def _shutdown(self) -> None:
        """Cancel tasks, close store, report summary."""
        self.store.close()
        if not self.tasks:
            return
        for task in self.tasks:
            task.cancel()
        results = await asyncio.gather(*self.tasks, return_exceptions=True)
        cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        if cancelled:
            self.router.write("debug", f"cancelled {cancelled} tasks", mode="DEBUG")

    async def run(self) -> None:
        """Main REPL loop."""
        with patch_stdout():
            while True:
                try:
                    text = await self.session.prompt_async()
                except KeyboardInterrupt:
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
                    for task in list(self.tasks):
                        task.cancel()
                    self.router.write("debug", "interrupted, cancelled tracked tasks", mode="DEBUG")


async def channel_arun(graph, start_node, router, *, lm=None, max_iters=10):
    """Wrap graph.arun() routing output through [graph] channel."""
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
    captured = buf.getvalue()
    if captured:
        router.write("graph", captured.rstrip(), mode="GRAPH", metadata={"type": "log"})
    if result and result.trace:
        terminal = result.trace[-1]
        router.write("graph", repr(terminal), mode="GRAPH", metadata={"type": "result"})
    return result
