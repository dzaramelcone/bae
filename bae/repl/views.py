"""Concrete display formatters for channel content.

UserView renders AI code execution as framed Rich Panels with syntax
highlighting and buffered code+output grouping. Non-AI writes fall
through to standard color-coded prefix display.

DebugView renders raw channel data with full metadata headers.

AISelfView labels writes with AI-perspective tags (ai-output, exec-code, etc).
"""

from __future__ import annotations

import os
from enum import Enum
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


class DebugView:
    """Raw channel data with full metadata headers for debugging.

    Renders [channel] key=value header followed by indented content lines.
    No Rich panels, no syntax highlighting, no markdown -- raw data only.
    """

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        meta_str = " ".join(f"{k}={v}" for k, v in sorted(meta.items()))
        header = f"[{channel_name}] {meta_str}" if meta_str else f"[{channel_name}]"
        print_formatted_text(FormattedText([(f"{color} bold", header)]))
        for line in content.splitlines():
            print_formatted_text(FormattedText([
                ("fg:#808080", "  "),
                ("", line),
            ]))


class AISelfView:
    """AI-perspective display labeling each write by semantic role.

    Tags: ai-output, exec-code, exec-result, tool-call, tool-output, error.
    No buffering, no transformation, no Rich panels.
    """

    _tag_map = {
        "response": "ai-output",
        "ai_exec": "exec-code",
        "ai_exec_result": "exec-result",
        "tool_translated": "tool-call",
        "tool_result": "tool-output",
        "error": "error",
    }

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")
        tag = self._tag_map.get(content_type, content_type or channel_name)
        if "label" in meta:
            tag = f"{tag}:{meta['label']}"
        print_formatted_text(FormattedText([("fg:#b0b040 bold", f"[{tag}]")]))
        for line in content.splitlines():
            print_formatted_text(FormattedText([
                ("fg:#808080", "  "),
                ("", line),
            ]))


class ViewMode(Enum):
    """Display modes for channel content rendering."""
    USER = "user"
    DEBUG = "debug"
    AI_SELF = "ai-self"


VIEW_CYCLE: list[ViewMode] = [ViewMode.USER, ViewMode.DEBUG, ViewMode.AI_SELF]

VIEW_FORMATTERS: dict[ViewMode, type] = {
    ViewMode.USER: UserView,
    ViewMode.DEBUG: DebugView,
    ViewMode.AI_SELF: AISelfView,
}
