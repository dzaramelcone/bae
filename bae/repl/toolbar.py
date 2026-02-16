"""Configurable toolbar with named widgets returning prompt_toolkit style tuples.

Users register callable widgets that render into the bottom toolbar.
Built-in widgets cover mode name, running task count, and cwd.
render_task_menu() provides the numbered task list for the inline kill menu.
"""

from __future__ import annotations

import os
import resource
import sys
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from bae.repl.tasks import TaskManager

ToolbarWidget = Callable[[], list[tuple[str, str]]]

TASKS_PER_PAGE = 5


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
        n = len(shell.tm.active())
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


def make_mem_widget() -> ToolbarWidget:
    """Built-in widget: interpreter RSS memory usage."""

    def widget():
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS returns bytes, Linux returns KB
        mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
        return [("class:toolbar.mem", f" {mb:.0f}M ")]

    return widget


def make_gates_widget(shell) -> ToolbarWidget:
    """Built-in widget: pending input gate count (hidden when zero)."""

    def widget():
        n = shell.engine.pending_gate_count()
        if n == 0:
            return []
        label = f" {n} gate{'s' if n != 1 else ''} "
        return [("class:toolbar.gates", label)]

    return widget


def make_view_widget(shell) -> ToolbarWidget:
    """Built-in widget: active view mode (hidden in default user view)."""
    def widget():
        if shell.view_mode.value == "user":
            return []
        return [("class:toolbar.view", f" {shell.view_mode.value} ")]
    return widget


def render_task_menu(tm: TaskManager, page: int = 0) -> list[tuple[str, str]]:
    """Render numbered task list for the inline kill menu, with pagination."""
    active = tm.active()
    if not active:
        return [("fg:#808080", " no tasks running ")]

    total_pages = (len(active) + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE
    page = min(page, total_pages - 1)
    start = page * TASKS_PER_PAGE
    page_tasks = active[start:start + TASKS_PER_PAGE]

    parts: list[tuple[str, str]] = []
    for i, tt in enumerate(page_tasks, start=1):
        parts.append(("bold fg:ansiyellow", f" {i}"))
        parts.append(("", f" {tt.name} "))

    parts.append(("fg:#808080", " | "))
    parts.append(("fg:#808080", "#=cancel "))
    parts.append(("fg:#808080 bold", "^C"))
    parts.append(("fg:#808080", "=all "))
    parts.append(("fg:#808080 bold", "esc"))
    parts.append(("fg:#808080", "=back"))

    if total_pages > 1:
        parts.append(("fg:#808080", f" \u2190/\u2192 {page + 1}/{total_pages}"))

    return parts
