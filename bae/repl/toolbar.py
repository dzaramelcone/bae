"""Configurable toolbar with named widgets returning prompt_toolkit style tuples.

Users register callable widgets that render into the bottom toolbar.
Built-in widgets cover mode name, running task count, and cwd.
"""

from __future__ import annotations

import os
from typing import Callable

ToolbarWidget = Callable[[], list[tuple[str, str]]]


class ToolbarConfig:
    """User-configurable toolbar with named widgets.

    toolbar.add("name", fn)   -- register widget
    toolbar.remove("name")    -- unregister widget
    toolbar.widgets           -- list widget names
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
