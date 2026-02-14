"""CortexShell: async REPL with mode switching."""

from __future__ import annotations

import asyncio
import logging
import os
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
from bae.repl.tasks import TaskManager
from bae.repl.toolbar import TASKS_PER_PAGE, ToolbarConfig, make_cwd_widget, make_mode_widget, make_tasks_widget, render_task_menu

# Register kitty keyboard protocol Shift+Enter (CSI u encoding).
# Terminals supporting the kitty protocol (Ghostty, kitty, iTerm2 CSI u mode)
# send \x1b[13;2u for Shift+Enter. Map it to Escape+Enter so the same
# "insert newline" binding handles both kitty Shift+Enter and Escape+Enter.
ANSI_SEQUENCES["\x1b[13;2u"] = (Keys.Escape, Keys.ControlM)


def _build_key_bindings(shell: CortexShell) -> KeyBindings:
    """Key bindings for cortex REPL."""
    from prompt_toolkit.filters import Condition

    kb = KeyBindings()
    task_menu_active = Condition(lambda: shell._task_menu)

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
        """Ctrl-C: exit if idle, kill-all if task menu open, open task menu if tasks running."""
        if shell._task_menu:
            shell.tm.revoke_all(graceful=False)
            shell._task_menu = False
            shell._task_menu_page = 0
            shell.router.write("debug", "killed all tasks", mode="DEBUG")
            event.app.invalidate()
            return
        if not shell.tm.active():
            event.app.exit(exception=KeyboardInterrupt())
            return
        shell._task_menu = True
        shell._task_menu_page = 0
        event.app.invalidate()

    @kb.add("escape", eager=True, filter=task_menu_active)
    def dismiss_task_menu(event):
        """Esc: close task menu, return to normal toolbar."""
        shell._task_menu = False
        shell._task_menu_page = 0
        event.app.invalidate()

    @kb.add("left", filter=task_menu_active)
    def task_menu_prev_page(event):
        """Left arrow: previous page."""
        if shell._task_menu_page > 0:
            shell._task_menu_page -= 1
            event.app.invalidate()

    @kb.add("right", filter=task_menu_active)
    def task_menu_next_page(event):
        """Right arrow: next page."""
        active = shell.tm.active()
        total_pages = (len(active) + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE
        if shell._task_menu_page < total_pages - 1:
            shell._task_menu_page += 1
            event.app.invalidate()

    for digit in "12345":
        @kb.add(digit, filter=task_menu_active)
        def cancel_by_digit(event, _d=digit):
            """Digit key: cancel task at that position on current page."""
            idx = int(_d) - 1
            active = shell.tm.active()
            offset = shell._task_menu_page * TASKS_PER_PAGE
            pos = offset + idx
            if pos < len(active):
                tt = active[pos]
                shell.tm.revoke(tt.task_id)
                shell.router.write("debug", f"cancelled {tt.name}", mode="DEBUG")
            if not shell.tm.active():
                shell._task_menu = False
                shell._task_menu_page = 0
            event.app.invalidate()

    return kb


class CortexShell:
    """Async REPL with four modes."""

    def __init__(self) -> None:
        self.mode: Mode = DEFAULT_MODE
        self.namespace: dict = seed()
        self.tm = TaskManager()
        self._task_menu = False
        self._task_menu_page = 0
        self.store = SessionStore(Path.cwd() / ".bae" / "store.db")
        self.namespace["store"] = self.store
        self.router = ChannelRouter()
        for name, cfg in CHANNEL_DEFAULTS.items():
            self.router.register(name, cfg["color"], store=self.store)
        self.namespace["channels"] = self.router
        from bae.lm import ClaudeCLIBackend
        self.ai = AI(lm=ClaudeCLIBackend(), router=self.router, namespace=self.namespace, tm=self.tm)
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
        """Bottom toolbar: task menu when active, normal widgets otherwise."""
        if self._task_menu:
            return render_task_menu(self.tm, self._task_menu_page)
        return self.toolbar.render()

    async def _run_nl(self, text: str) -> None:
        """NL mode: AI conversation, self-contained error handling."""
        try:
            await self.ai(text)
        except asyncio.CancelledError:
            self.router.write("debug", "cancelled ai task", mode="DEBUG")
        except Exception:
            tb = traceback.format_exc()
            self.router.write("ai", tb.rstrip("\n"), mode="NL", metadata={"type": "error"})

    async def _run_graph(self, text: str) -> None:
        """GRAPH mode: graph execution, self-contained error handling."""
        graph = self.namespace.get("graph")
        if not graph:
            self.router.write("graph", "(Graph mode stub) Not yet implemented.", mode="GRAPH")
            return
        try:
            result = await channel_arun(graph, text, self.router)
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

    async def _run_bash(self, text: str) -> None:
        """BASH mode: shell command, self-contained error handling."""
        try:
            stdout, stderr = await dispatch_bash(text, tm=self.tm)
        except asyncio.CancelledError:
            self.router.write("debug", "cancelled bash task", mode="DEBUG")
            return
        except Exception:
            tb = traceback.format_exc()
            self.router.write("bash", tb.rstrip("\n"), mode="BASH", metadata={"type": "error"})
            return
        if stdout:
            self.router.write("bash", stdout.rstrip("\n"), mode="BASH")
        if stderr:
            self.router.write("bash", stderr.rstrip("\n"), mode="BASH", metadata={"type": "stderr"})

    async def _dispatch(self, text: str) -> None:
        """Route input to the active mode handler.

        PY sync expressions execute sequentially. PY async expressions
        (await ...) are tracked via TaskManager. NL/GRAPH/BASH modes fire
        as background tasks so prompt_async() stays active.
        """
        if self.mode == Mode.PY:
            try:
                result, captured = await async_exec(text, self.namespace)
                if captured:
                    self.router.write("py", captured.rstrip("\n"), mode="PY", metadata={"type": "stdout"})
                if asyncio.iscoroutine(result):
                    async def _py_task(coro):
                        try:
                            val = await coro
                            if val is not None:
                                self.router.write("py", repr(val), mode="PY", metadata={"type": "expr_result"})
                        except asyncio.CancelledError:
                            self.router.write("debug", "cancelled py task", mode="DEBUG")
                        except Exception:
                            tb = traceback.format_exc()
                            self.router.write("py", tb.rstrip("\n"), mode="PY", metadata={"type": "error"})
                    self.tm.submit(_py_task(result), name=f"py:{text[:30]}", mode="py")
                elif result is not None:
                    self.router.write("py", repr(result), mode="PY", metadata={"type": "expr_result"})
            except KeyboardInterrupt:
                pass
            except Exception:
                tb = traceback.format_exc()
                self.router.write("py", tb.rstrip("\n"), mode="PY", metadata={"type": "error"})
        elif self.mode == Mode.NL:
            self.tm.submit(self._run_nl(text), name=f"ai:{text[:30]}", mode="nl")
        elif self.mode == Mode.GRAPH:
            self.tm.submit(self._run_graph(text), name=f"graph:{text[:30]}", mode="graph")
        elif self.mode == Mode.BASH:
            self.tm.submit(self._run_bash(text), name=f"bash:{text[:30]}", mode="bash")

    async def _shutdown(self) -> None:
        """Revoke all tasks, close store."""
        self.store.close()
        await self.tm.shutdown()

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
                    self.tm.revoke_all(graceful=False)
                    self.router.write("debug", "interrupted, revoked all tasks", mode="DEBUG")


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
