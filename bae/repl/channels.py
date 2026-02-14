"""Output multiplexing with labeled, color-coded channels."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.shortcuts import checkboxlist_dialog
from rich.console import Console
from rich.markdown import Markdown

if TYPE_CHECKING:
    from bae.repl.store import SessionStore

CHANNEL_DEFAULTS = {
    "py":    {"color": "#87ff87"},
    "graph": {"color": "#ffaf87"},
    "ai":    {"color": "#87d7ff", "markdown": True},
    "bash":  {"color": "#d7afff"},
    "debug": {"color": "#808080"},
}


def render_markdown(text: str, width: int | None = None) -> str:
    """Convert markdown text to ANSI-escaped string via Rich."""
    if width is None:
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 80
    buf = StringIO()
    console = Console(file=buf, width=width, force_terminal=True)
    console.print(Markdown(text))
    return buf.getvalue()


@dataclass
class Channel:
    """A labeled output stream with color-coded display and store integration."""

    name: str
    color: str
    visible: bool = True
    markdown: bool = False
    store: SessionStore | None = None
    _buffer: list[str] = field(default_factory=list, repr=False)

    @property
    def label(self) -> str:
        """Channel prefix tag for display."""
        return f"[{self.name}]"

    def write(
        self,
        content: str,
        *,
        mode: str = "",
        direction: str = "output",
        metadata: dict | None = None,
    ) -> None:
        """Write content through this channel -- record, buffer, conditionally display."""
        if self.store:
            self.store.record(
                mode or self.name.upper(), self.name, direction, content, metadata,
            )
        self._buffer.append(content)
        if self.visible:
            self._display(content, metadata=metadata)

    def _display(self, content: str, *, metadata: dict | None = None) -> None:
        """Render content with color-coded channel prefix.

        Markdown channels render the entire response as one Rich Markdown block,
        preserving headers, code blocks, and lists. Non-markdown channels render
        line-by-line with a color-coded prefix.
        """
        label_text = self.label
        if metadata and "label" in metadata:
            label_text = f"[{self.name}:{metadata['label']}]"

        if self.markdown:
            label = FormattedText([(f"{self.color} bold", label_text)])
            print_formatted_text(label)
            ansi_text = render_markdown(content)
            print_formatted_text(ANSI(ansi_text))
        else:
            for line in content.splitlines():
                text = FormattedText([
                    (f"{self.color} bold", label_text),
                    ("", " "),
                    ("", line),
                ])
                print_formatted_text(text)

    def __repr__(self) -> str:
        vis = "visible" if self.visible else "hidden"
        return f"Channel({self.name!r}, {vis}, {len(self._buffer)} entries)"


@dataclass
class ChannelRouter:
    """Registry of output channels with visibility control and debug logging."""

    _channels: dict[str, Channel] = field(default_factory=dict, repr=False)
    debug_handler: logging.FileHandler | None = field(default=None, repr=False)

    def register(
        self, name: str, color: str, store: SessionStore | None = None,
        *, markdown: bool = False,
    ) -> Channel:
        """Register a new channel."""
        ch = Channel(name=name, color=color, markdown=markdown, store=store)
        self._channels[name] = ch
        return ch

    def write(self, channel: str, content: str, **kwargs) -> None:
        """Write to a named channel. No-op for unknown channels."""
        ch = self._channels.get(channel)
        if ch:
            ch.write(content, **kwargs)
            if self.debug_handler:
                record = logging.LogRecord(
                    name=channel,
                    level=logging.DEBUG,
                    pathname="",
                    lineno=0,
                    msg=content,
                    args=(),
                    exc_info=None,
                )
                self.debug_handler.emit(record)

    def __getattr__(self, name: str) -> Channel:
        """Namespace access: router.py, router.graph, etc."""
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._channels:
            return self._channels[name]
        raise AttributeError(f"No channel {name!r}")

    @property
    def visible(self) -> list[str]:
        """Channel names with visible=True."""
        return [n for n, ch in self._channels.items() if ch.visible]

    @property
    def all(self) -> list[str]:
        """All registered channel names."""
        return list(self._channels.keys())


def enable_debug(router: ChannelRouter, log_dir: Path | None = None) -> None:
    """Attach a FileHandler to router for debug logging to .bae/debug.log."""
    log_path = (log_dir or Path.cwd() / ".bae") / "debug.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    router.debug_handler = handler


def disable_debug(router: ChannelRouter) -> None:
    """Close and remove the debug handler."""
    if router.debug_handler:
        router.debug_handler.close()
        router.debug_handler = None


async def toggle_channels(router: ChannelRouter) -> None:
    """Show checkbox dialog for channel visibility toggles."""
    values = [(name, f"[{name}] channel") for name in router.all]
    default = router.visible

    result = await checkboxlist_dialog(
        title="Channel Visibility",
        text="Toggle which channels are displayed:",
        values=values,
        default_values=default,
    ).run_async()

    if result is not None:
        for name in router.all:
            router._channels[name].visible = name in result
