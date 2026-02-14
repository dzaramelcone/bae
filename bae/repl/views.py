"""Concrete display formatters for channel content.

UserView renders AI code execution as framed Rich Panels with syntax
highlighting and buffered code+output grouping. Non-AI writes fall
through to standard color-coded prefix display.
"""

from __future__ import annotations

import os
from io import StringIO

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI, FormattedText
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text


def _rich_to_ansi(renderable, width=None):
    """Render a Rich renderable to ANSI string for prompt_toolkit."""
    if width is None:
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 80
    buf = StringIO()
    console = Console(file=buf, width=width, force_terminal=True)
    console.print(renderable)
    return buf.getvalue()


class UserView:
    """Framed panel display for AI code execution on [py] channel.

    Buffers ai_exec writes, renders grouped code+output panels on ai_exec_result.
    All other py channel writes fall through to standard prefix display.
    """

    def __init__(self):
        self._pending_code: str | None = None
        self._pending_meta: dict | None = None

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")

        if content_type == "ai_exec":
            if self._pending_code is not None:
                self._render_code_panel(self._pending_code, self._pending_meta or {})
            self._pending_code = content
            self._pending_meta = meta
            return

        if content_type == "ai_exec_result" and self._pending_code is not None:
            self._render_grouped_panel(self._pending_code, content, self._pending_meta or {})
            self._pending_code = None
            self._pending_meta = None
            return

        self._render_prefixed(channel_name, color, content, meta)

    def _render_grouped_panel(self, code, output, meta):
        """Render code + output as a single framed panel."""
        label = meta.get("label", "")
        title = f"ai:{label}" if label else "exec"

        parts = [Syntax(code, "python", theme="monokai")]
        if output and output != "(no output)":
            parts.append(Rule(style="dim"))
            parts.append(Text(output))
        else:
            parts.append(Rule(style="dim"))
            parts.append(Text("(executed)", style="dim italic"))

        panel = Panel(
            Group(*parts),
            title=f"[bold cyan]{title}[/]",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        ansi = _rich_to_ansi(panel)
        print_formatted_text(ANSI(ansi))

    def _render_code_panel(self, code, meta):
        """Render code-only panel (when output was never received)."""
        label = meta.get("label", "")
        title = f"ai:{label}" if label else "exec"

        panel = Panel(
            Group(
                Syntax(code, "python", theme="monokai"),
                Rule(style="dim"),
                Text("(executed)", style="dim italic"),
            ),
            title=f"[bold cyan]{title}[/]",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        ansi = _rich_to_ansi(panel)
        print_formatted_text(ANSI(ansi))

    def _render_prefixed(self, channel_name, color, content, meta):
        """Standard line-by-line display with channel prefix."""
        label = f"[{channel_name}]"
        if meta and "label" in meta:
            label = f"[{channel_name}:{meta['label']}]"
        for line in content.splitlines():
            text = FormattedText([
                (f"{color} bold", label),
                ("", " "),
                ("", line),
            ])
            print_formatted_text(text)
