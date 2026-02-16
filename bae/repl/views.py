"""Concrete display formatters for channel content.

UserView renders AI code execution as framed Rich Panels with syntax
highlighting and buffered code+output grouping. Non-AI writes fall
through to standard color-coded prefix display.

DebugView renders raw channel data with full metadata headers.

AISelfView labels writes with AI-perspective tags (ai-output, exec-code, etc).
"""

from __future__ import annotations

import os
import re
from enum import Enum
from io import StringIO
from pathlib import Path

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI, FormattedText
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text


# File path pattern: path ending in known extension, optionally with :line[:col]
_SOURCE_EXTS = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".rb", ".lua",
    ".sh", ".bash", ".zsh", ".c", ".h", ".cpp", ".hpp", ".java", ".swift",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".cfg", ".ini",
    ".html", ".css", ".scss", ".sql", ".xml", ".svg", ".conf", ".env",
)
_EXT_PAT = "|".join(re.escape(e) for e in _SOURCE_EXTS)

# Standalone paths: /foo/bar.py:42:3 or ./foo.py or ~/bar.md
_PATH_RE = re.compile(
    r"(?<!\033)(?<!\w)"
    r"((?:[/~]|\.\.?/)[^\s:\"]+?(?:" + _EXT_PAT + r"))"
    r"(?::(\d+)(?::(\d+))?)?"
    r"(?=[\s,)\]}>\"']|$)"
)

# Python traceback: File "path.py", line N
_TB_RE = re.compile(
    r'(File ")((?:[^"]+?(?:' + _EXT_PAT + r')))", line (\d+)'
)


def _osc8(uri: str, display: str) -> str:
    """Wrap display text in an OSC 8 hyperlink."""
    return f"\033]8;;{uri}\033\\{display}\033]8;;\033\\"


def _vscode_uri(filepath: str, line: str | None = None, col: str | None = None) -> str:
    """Build vscode://file/ URI from a path and optional line/col."""
    p = Path(filepath).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    uri = f"vscode://file{p}"
    if line:
        uri += f":{line}"
        if col:
            uri += f":{col}"
    return uri


def linkify_paths(text: str) -> str:
    """Wrap file paths in OSC 8 terminal hyperlinks opening in VS Code."""
    # Traceback lines first (more specific pattern)
    def _tb_replace(m):
        prefix, filepath, line = m.group(1), m.group(2), m.group(3)
        uri = _vscode_uri(filepath, line)
        linked_path = _osc8(uri, f'{filepath}"), line {line}')
        return f'{prefix}{linked_path}'

    def _path_replace(m):
        filepath, line, col = m.group(1), m.group(2), m.group(3)
        uri = _vscode_uri(filepath, line, col)
        return _osc8(uri, m.group(0))

    text = _TB_RE.sub(_tb_replace, text)
    text = _PATH_RE.sub(_path_replace, text)
    return text


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


_STRIP_RUN_RE = re.compile(r"<run>\s*\n?.*?\n?\s*</run>", re.DOTALL)
_STRIP_TOOL_RE = re.compile(
    r"^[ \t]*<(?:R|Read|W|Write|E|Edit|G|Glob|Grep):[^>]+>.*$",
    re.MULTILINE | re.IGNORECASE,
)
_STRIP_WRITE_RE = re.compile(
    r"^[ \t]*<(?:W|Write):[^>]+>\s*\n.*?\n[ \t]*</(?:W|Write)>",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)


def _strip_executable(text):
    """Strip <run> blocks and tool tags from AI response for clean display."""
    text = _STRIP_WRITE_RE.sub("", text)   # Multi-line Write tags first
    text = _STRIP_RUN_RE.sub("", text)
    text = _STRIP_TOOL_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)  # Collapse blank runs
    return text.strip()


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

        if content_type == "ansi":
            print_formatted_text(ANSI(content))
            return

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

        if content_type == "response":
            cleaned = _strip_executable(content)
            if cleaned:
                self._render_prefixed(channel_name, color, cleaned, meta)
            return

        if content_type == "tool_translated":
            summary = linkify_paths(meta.get("tool_summary", content))
            print_formatted_text(ANSI(
                f"\033[1m[{channel_name}]\033[0m \033[3;38;5;244m{summary}\033[0m"
            ))
            return

        if content_type == "lifecycle" and channel_name == "graph":
            label = f"[{channel_name}:{meta.get('run_id', '')}]"
            event = meta.get("event", "")
            style_map = {"start": "fg:#808080", "complete": "fg:#87ff87", "fail": "fg:red", "cancel": "fg:ansiyellow", "transition": "fg:#808080"}
            style = style_map.get(event, "")
            print_formatted_text(FormattedText([
                (f"{color} bold", label),
                ("", " "),
                (style, content),
            ]))
            return

        self._render_prefixed(channel_name, color, content, meta)

    def _render_grouped_panel(self, code, output, meta):
        """Render code + output as a single framed panel."""
        label = meta.get("label", "")
        title = f"ai:{label}" if label else "exec"

        parts = [Syntax(code, "python", theme="monokai")]
        if output and output != "(no output)":
            parts.append(Rule(style="dim"))
            parts.append(Text.from_ansi(linkify_paths(output)))
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
        """Display with channel prefix on first line, indented continuation."""
        label = f"[{channel_name}]"
        if meta and "label" in meta:
            label = f"[{channel_name}:{meta['label']}]"
        linked = linkify_paths(content)
        lines = linked.splitlines()
        if not lines:
            return
        print_formatted_text(FormattedText([
            (f"{color} bold", label),
            ("", " "),
        ]), end="")
        print_formatted_text(ANSI(lines[0]))
        for line in lines[1:]:
            print_formatted_text(ANSI(f"  {line}"))


class DebugView:
    """Raw channel data with full metadata headers for debugging.

    Renders [channel] key=value header followed by indented content lines.
    No Rich panels, no syntax highlighting, no markdown -- raw data only.
    """

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        if meta.get("type") == "ansi":
            meta_str = " ".join(f"{k}={v}" for k, v in sorted(meta.items()))
            header = f"[{channel_name}] {meta_str}"
            print_formatted_text(FormattedText([(f"{color} bold", header)]))
            print_formatted_text(ANSI(content))
            return
        meta_str = " ".join(f"{k}={v}" for k, v in sorted(meta.items()))
        header = f"[{channel_name}] {meta_str}" if meta_str else f"[{channel_name}]"
        print_formatted_text(FormattedText([(f"{color} bold", header)]))
        linked = linkify_paths(content)
        for line in linked.splitlines():
            print_formatted_text(ANSI(f"  {line}"))


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
        if content_type == "ansi":
            print_formatted_text(FormattedText([("fg:#b0b040 bold", f"[{tag}]")]))
            print_formatted_text(ANSI(content))
            return
        display = _strip_executable(content) if content_type == "response" else content
        print_formatted_text(FormattedText([("fg:#b0b040 bold", f"[{tag}]")]))
        linked = linkify_paths(display)
        for line in linked.splitlines():
            print_formatted_text(ANSI(f"  {line}"))


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
