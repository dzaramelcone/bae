"""CortexShell: async REPL with mode switching."""

from __future__ import annotations

import asyncio
import os
import traceback
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

from bae.repl.bash import dispatch_bash
from bae.repl.complete import NamespaceCompleter
from bae.repl.exec import async_exec
from bae.repl.modes import DEFAULT_MODE, MODE_COLORS, MODE_CYCLE, MODE_NAMES, Mode
from bae.repl.store import SessionStore, make_store_inspector

# Register kitty keyboard protocol Shift+Enter (CSI u encoding).
# Terminals supporting the kitty protocol (Ghostty, kitty, iTerm2 CSI u mode)
# send \x1b[13;2u for Shift+Enter. Map it to Escape+Enter so the same
# "insert newline" binding handles both kitty Shift+Enter and Escape+Enter.
ANSI_SEQUENCES["\x1b[13;2u"] = (Keys.Escape, Keys.ControlM)


def _build_key_bindings(shell: CortexShell) -> KeyBindings:
    """Key bindings for cortex REPL."""
    kb = KeyBindings()

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

    return kb


class CortexShell:
    """Async REPL with four modes."""

    def __init__(self) -> None:
        self.mode: Mode = DEFAULT_MODE
        self.namespace: dict = {"asyncio": asyncio, "os": os, "__builtins__": __builtins__}
        self.tasks: set[asyncio.Task] = set()
        self.store = SessionStore(Path.cwd() / ".bae" / "store.db")
        self.namespace["store"] = make_store_inspector(self.store)
        self.completer = NamespaceCompleter(self.namespace)

        kb = _build_key_bindings(self)
        self.session = PromptSession(
            message=self._prompt,
            lexer=DynamicLexer(self._lexer),
            completer=DynamicCompleter(self._completer),
            multiline=True,
            bottom_toolbar=self._toolbar,
            style=Style.from_dict({
                "bottom-toolbar": "bg:#1c1c1c #808080",
                "bottom-toolbar.text": "",
                "toolbar.mode": "bg:#303030 #ffffff bold",
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
        """Bottom toolbar: mode name + cwd."""
        name = MODE_NAMES[self.mode]
        cwd = os.getcwd()
        home = os.path.expanduser("~")
        if cwd.startswith(home):
            cwd = "~" + cwd[len(home):]
        return [("class:toolbar.mode", f" {name} "), ("class:toolbar.cwd", f" {cwd} ")]

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
            print(f"cancelled {cancelled} tasks")

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

                if self.mode == Mode.PY:
                    try:
                        result = await async_exec(text, self.namespace)
                        if result is not None:
                            output = repr(result)
                            print(output)
                            self.store.record("PY", "repl", "output", output, {"type": "expr_result"})
                    except KeyboardInterrupt:
                        pass
                    except Exception:
                        tb = traceback.format_exc()
                        print(tb, end="")
                        self.store.record("PY", "repl", "output", tb, {"type": "error"})
                elif self.mode == Mode.NL:
                    stub = f"(NL mode stub) {text}\nNL mode coming in Phase 18."
                    print(stub)
                    self.store.record("NL", "repl", "output", stub)
                elif self.mode == Mode.GRAPH:
                    stub = "(Graph mode stub) Not yet implemented."
                    print(stub)
                    self.store.record("GRAPH", "repl", "output", stub)
                elif self.mode == Mode.BASH:
                    stdout, stderr = await dispatch_bash(text)
                    if stdout:
                        self.store.record("BASH", "stdout", "output", stdout)
                    if stderr:
                        self.store.record("BASH", "stderr", "output", stderr, {"type": "stderr"})
