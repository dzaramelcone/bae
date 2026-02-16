"""CortexShell: async REPL with mode switching."""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from io import StringIO
from pathlib import Path

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
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
from bae.repl.engine import GraphRegistry
from bae.repl.channels import CHANNEL_DEFAULTS, ChannelRouter, toggle_channels
from bae.repl.resource import ResourceRegistry, ResourceHandle
from bae.repl.spaces.source import SourceResourcespace
from bae.repl.complete import NamespaceCompleter
from bae.repl.exec import async_exec
from bae.repl.modes import DEFAULT_MODE, MODE_COLORS, MODE_CYCLE, MODE_NAMES, Mode
from bae.repl.namespace import seed
from bae.repl.store import SessionStore
from bae.repl.tasks import TaskManager
from bae.repl.views import UserView, ViewMode, VIEW_CYCLE, VIEW_FORMATTERS
from bae.repl.toolbar import (
    TASKS_PER_PAGE,
    ToolbarConfig,
    make_cwd_widget,
    make_gates_widget,
    make_location_widget,
    make_mem_widget,
    make_mode_widget,
    make_tasks_widget,
    make_view_widget,
)
from bae.repl.tools import ToolRouter

# Register kitty keyboard protocol Shift+Enter (CSI u encoding).
# Terminals supporting the kitty protocol (Ghostty, kitty, iTerm2 CSI u mode)
# send \x1b[13;2u for Shift+Enter. Map it to Escape+Enter so the same
# "insert newline" binding handles both kitty Shift+Enter and Escape+Enter.
ANSI_SEQUENCES["\x1b[13;2u"] = (Keys.Escape, Keys.ControlM)


def _walk_coroutines(obj, close=False, _seen=None):
    """Recursively walk obj for unawaited coroutines.

    When close=False: returns True/False (contains check).
    When close=True: closes each coroutine, returns int count.
    """
    if _seen is None:
        _seen = set()
    obj_id = id(obj)
    if obj_id in _seen:
        return 0 if close else False
    _seen.add(obj_id)

    if asyncio.iscoroutine(obj):
        if close:
            obj.close()
            return 1
        return True
    if isinstance(obj, (list, tuple, set)):
        if close:
            return sum(_walk_coroutines(item, True, _seen) for item in obj)
        return any(_walk_coroutines(item, False, _seen) for item in obj)
    if isinstance(obj, dict):
        if close:
            return sum(_walk_coroutines(v, True, _seen) for v in obj.values())
        return any(_walk_coroutines(v, False, _seen) for v in obj.values())
    return 0 if close else False


def _print_task_menu(shell: CortexShell) -> None:
    """Print numbered task list to scrollback above the prompt."""
    active = shell.tm.active()
    if not active:
        return
    for i, tt in enumerate(active, start=1):
        line = FormattedText(
            [
                ("bold fg:ansiyellow", f"  {i}"),
                ("", f" {tt.name}"),
            ]
        )
        print_formatted_text(line)
    hint = FormattedText([("fg:#808080", "  #=cancel  ^C=all  esc=back")])
    print_formatted_text(hint)


def _bind_mode_controls(kb: KeyBindings, shell: CortexShell) -> None:
    """Mode cycling, view cycling, submit, newline, and channel toggle."""

    @kb.add("s-tab")
    def cycle_mode(event):
        idx = MODE_CYCLE.index(shell.mode)
        shell.mode = MODE_CYCLE[(idx + 1) % len(MODE_CYCLE)]
        event.app.invalidate()

    @kb.add("c-v")
    def cycle_view(event):
        idx = VIEW_CYCLE.index(shell.view_mode)
        shell._set_view(VIEW_CYCLE[(idx + 1) % len(VIEW_CYCLE)])
        event.app.invalidate()

    @kb.add("enter")
    def submit(event):
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def insert_newline(event):
        event.current_buffer.insert_text("\n")

    @kb.add("c-o")
    def open_channel_toggle(event):
        async def _toggle():
            await toggle_channels(shell.router)
            event.app.invalidate()
        event.app.create_background_task(_toggle())


def _bind_interrupt(kb: KeyBindings, shell: CortexShell) -> None:
    """Ctrl-C: exit if idle, kill-all if task menu open, open task menu."""

    @kb.add("c-c", eager=True)
    def handle_interrupt(event):
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
        _print_task_menu(shell)
        event.app.invalidate()


def _bind_task_menu(kb: KeyBindings, shell: CortexShell) -> None:
    """Task menu navigation: dismiss, page, cancel by digit."""
    from prompt_toolkit.filters import Condition

    task_menu_active = Condition(lambda: shell._task_menu)

    @kb.add("escape", eager=True, filter=task_menu_active)
    def dismiss_task_menu(event):
        shell._task_menu = False
        shell._task_menu_page = 0
        event.app.invalidate()

    @kb.add("left", filter=task_menu_active)
    def task_menu_prev_page(event):
        if shell._task_menu_page > 0:
            shell._task_menu_page -= 1
            event.app.invalidate()

    @kb.add("right", filter=task_menu_active)
    def task_menu_next_page(event):
        active = shell.tm.active()
        total_pages = (len(active) + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE
        if shell._task_menu_page < total_pages - 1:
            shell._task_menu_page += 1
            event.app.invalidate()

    for digit in "12345":
        @kb.add(digit, filter=task_menu_active)
        def cancel_by_digit(event, _d=digit):
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
            else:
                _print_task_menu(shell)
            event.app.invalidate()


def _build_key_bindings(shell: CortexShell) -> KeyBindings:
    """Key bindings for cortex REPL."""
    kb = KeyBindings()
    _bind_mode_controls(kb, shell)
    _bind_interrupt(kb, shell)
    _bind_task_menu(kb, shell)
    return kb


class CortexShell:
    """Async REPL with three modes."""

    def __init__(self) -> None:
        self.mode: Mode = DEFAULT_MODE
        self.namespace: dict = seed()
        self.tm = TaskManager()
        self.engine = GraphRegistry()
        self._task_menu = False
        self._task_menu_page = 0
        self.store = SessionStore(Path.cwd() / ".bae" / "store.db")
        self.namespace["store"] = self.store
        self.router = ChannelRouter()
        for name, cfg in CHANNEL_DEFAULTS.items():
            self.router.register(
                name, cfg["color"], store=self.store, markdown=cfg.get("markdown", False)
            )
        self.namespace["channels"] = self.router
        self.view_mode = ViewMode.USER
        self._set_view(ViewMode.USER)
        from bae.lm import ClaudeCLIBackend

        self._lm = ClaudeCLIBackend()
        self.registry = ResourceRegistry(namespace=self.namespace)
        self._tool_router = ToolRouter(self.registry)
        from bae.repl.spaces.home import _exec_read, _exec_glob, _exec_grep
        self.registry._home_tools = {
            "read": _exec_read,
            "glob": _exec_glob,
            "grep": _exec_grep,
        }
        self.namespace["home"] = lambda: self.registry.home()
        self.namespace["back"] = lambda: self.registry.back()
        source_rs = SourceResourcespace(Path.cwd())
        self.registry.register(source_rs)
        self.namespace["source"] = ResourceHandle("source", self.registry)
        self._ai_sessions: dict[str, AI] = {}
        self._active_session: str = "1"
        self.ai = self._get_or_create_session("1")
        self.namespace["ai"] = self.ai
        self.namespace["engine"] = self.engine
        self.toolbar = ToolbarConfig()
        self.toolbar.add("mode", make_mode_widget(self))
        self.toolbar.add("view", make_view_widget(self))
        self.toolbar.add("tasks", make_tasks_widget(self))
        self.toolbar.add("gates", make_gates_widget(self))
        self.toolbar.add("location", make_location_widget(self))
        self.toolbar.add("mem", make_mem_widget())
        self.toolbar.add("cwd", make_cwd_widget())
        self.namespace["toolbar"] = self.toolbar
        self.completer = NamespaceCompleter(self.namespace)

        # Set graph context for auto-registration of graphs created in the REPL
        from bae.repl.engine import _graph_ctx

        def _notify(content, meta=None):
            self.router.write("graph", content, mode="GRAPH", metadata=meta or {"type": "lifecycle"})

        _graph_ctx.set((self.engine, self.tm, self._lm, _notify))

        kb = _build_key_bindings(self)
        self.session = PromptSession(
            message=self._prompt,
            lexer=DynamicLexer(self._lexer),
            completer=DynamicCompleter(self._completer),
            multiline=True,
            bottom_toolbar=self._toolbar,
            refresh_interval=1.0,
            style=Style.from_dict(
                {
                    "bottom-toolbar": "bg:#1c1c1c #808080",
                    "bottom-toolbar.text": "",
                    "toolbar.mode": "bg:#303030 #ffffff bold",
                    "toolbar.view": "bg:#303030 #ffaf87",
                    "toolbar.tasks": "fg:ansiyellow bold",
                    "toolbar.gates": "fg:ansimagenta bold",
                    "toolbar.location": "fg:ansigreen",
                    "toolbar.mem": "#808080",
                    "toolbar.cwd": "#808080",
                }
            ),
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
        """Bottom toolbar: always normal widgets. Task menu prints to scrollback."""
        return self.toolbar.render()

    def _get_or_create_session(self, label: str) -> AI:
        """Return AI session by label, creating if needed."""
        if label not in self._ai_sessions:
            self._ai_sessions[label] = AI(
                lm=self._lm,
                router=self.router,
                namespace=self.namespace,
                tm=self.tm,
                label=label,
                tool_router=self._tool_router,
                registry=self.registry,
            )
        return self._ai_sessions[label]

    def _switch_session(self, label: str) -> None:
        """Switch active AI session, updating namespace pointer."""
        self._active_session = label
        self.ai = self._get_or_create_session(label)
        self.namespace["ai"] = self.ai

    def _set_view(self, mode: ViewMode) -> None:
        """Switch all channels to the given view mode."""
        self.view_mode = mode
        formatter = VIEW_FORMATTERS[mode]()
        for ch in self.router._channels.values():
            ch._formatter = formatter

    async def _run_nl(self, text: str) -> None:
        """NL mode: AI conversation, self-contained error handling.

        Parses @N prefix to route to a specific AI session.
        """
        try:
            await self.ai(text)
        except asyncio.CancelledError:
            self.router.write("debug", "cancelled ai task", mode="DEBUG")
        except Exception:
            tb = traceback.format_exc()
            self.router.write("ai", tb.rstrip("\n"), mode="NL", metadata={"type": "error"})

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

    async def _resolve_gate_input(self, gate_id: str, raw_value: str) -> None:
        """Resolve a pending gate from any mode via @g prefix."""
        gate = self.engine.get_pending_gate(gate_id)
        if gate is None:
            self.router.write("graph", f"no pending gate {gate_id}", mode="GRAPH")
            return

        from pydantic import TypeAdapter

        try:
            adapter = TypeAdapter(gate.field_type)
            value = adapter.validate_python(raw_value)
        except Exception as e:
            type_name = getattr(gate.field_type, "__name__", str(gate.field_type))
            self.router.write(
                "graph",
                f"invalid value for {gate.field_name} ({type_name}): {e}",
                mode="GRAPH",
            )
            return

        self.engine.resolve_gate(gate_id, value)
        self.router.write(
            "graph",
            f"resolved {gate_id}: {gate.field_name} = {value!r}",
            mode="GRAPH",
            metadata={"type": "lifecycle", "run_id": gate.run_id},
        )

    async def _run_py(self, text: str) -> None:
        """PY mode: execute expression, handle sync/async results."""
        try:
            result, captured = await async_exec(text, self.namespace)
            if captured:
                self.router.write(
                    "py", captured.rstrip("\n"), mode="PY", metadata={"type": "stdout"}
                )
            if asyncio.iscoroutine(result):

                async def _py_task(coro):
                    try:
                        val = await coro
                        if val is not None:
                            if _walk_coroutines(val):
                                n = _walk_coroutines(val, close=True)
                                msg = f"<{n} unawaited coroutine{'s' if n != 1 else ''}>"
                                self.router.write(
                                    "py", msg, mode="PY", metadata={"type": "warning"}
                                )
                            else:
                                self.router.write(
                                    "py", repr(val), mode="PY", metadata={"type": "expr_result"}
                                )
                    except asyncio.CancelledError:
                        self.router.write("debug", "cancelled py task", mode="DEBUG")
                    except Exception:
                        tb = traceback.format_exc()
                        self.router.write(
                            "py", tb.rstrip("\n"), mode="PY", metadata={"type": "error"}
                        )

                self.tm.submit(_py_task(result), name=f"py:{text[:30]}", mode="py")
            elif result is not None:
                if _walk_coroutines(result):
                    n = _walk_coroutines(result, close=True)
                    msg = f"<{n} unawaited coroutine{'s' if n != 1 else ''}>"
                    self.router.write("py", msg, mode="PY", metadata={"type": "warning"})
                    self.namespace.pop("_", None)
                else:
                    self.router.write(
                        "py", repr(result), mode="PY", metadata={"type": "expr_result"}
                    )
        except KeyboardInterrupt:
            pass
        except Exception:
            tb = traceback.format_exc()
            self.router.write("py", tb.rstrip("\n"), mode="PY", metadata={"type": "error"})

    async def _dispatch(self, text: str) -> None:
        """Route input to the active mode handler."""
        # Cross-mode gate input: @g<digits> <value>
        if self.mode in (Mode.PY, Mode.BASH) and text.startswith("@g") and len(text) > 2:
            rest = text[2:]
            space = rest.find(" ")
            if space > 0 and rest[:space].replace(".", "").isdigit():
                gate_id = "g" + rest[:space]
                raw_value = rest[space + 1:]
                await self._resolve_gate_input(gate_id, raw_value)
                return

        if self.mode == Mode.PY:
            await self._run_py(text)
        elif self.mode == Mode.NL:
            prompt = text
            if text.startswith("@") and len(text) > 1:
                rest = text[1:]
                space = rest.find(" ")
                if space > 0:
                    label, prompt = rest[:space], rest[space + 1 :]
                    self._switch_session(label)
            self.tm.submit(
                self._run_nl(prompt), name=f"ai:{self._active_session}:{prompt[:30]}", mode="nl"
            )
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


async def channel_arun(graph, router, *, lm=None, max_iters=10, **kwargs):
    """Wrap graph.arun() routing output through [graph] channel."""
    graph_logger = logging.getLogger("bae.graph")
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    graph_logger.addHandler(handler)
    old_level = graph_logger.level
    graph_logger.setLevel(logging.DEBUG)
    try:
        result = await graph.arun(lm=lm, max_iters=max_iters, **kwargs)
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
