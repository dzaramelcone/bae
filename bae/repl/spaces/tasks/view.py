"""Display formatting for task listing and detail views.

Stateless, pure string output functions for rendering tasks in the REPL.
"""

from __future__ import annotations

import time

_STATUS_LABELS = {
    "open": "OPEN",
    "in_progress": "PROG",
    "blocked": "BLKD",
    "done": "DONE",
    "cancelled": "CNCL",
}

_MAX_TITLE = 50


def format_task_row(task: dict) -> str:
    """One-line format: id | status | priority | title | tags."""
    status = _STATUS_LABELS.get(task["status"], task["status"].upper())
    priority = f"{task['priority_major']}.{task['priority_minor']}.{task['priority_patch']}"
    title = task["title"]
    if len(title) > _MAX_TITLE:
        title = title[: _MAX_TITLE - 3] + "..."
    tags = ", ".join(task.get("tags") or [])
    parts = [task["id"], status, priority, title]
    if tags:
        parts.append(tags)
    return " | ".join(parts)


def format_task_detail(task: dict) -> str:
    """Full task detail view with all fields, body, tags, and audit."""
    lines = []
    lines.append(f"Task: {task['id']}")
    lines.append(f"Title: {task['title']}")
    status = _STATUS_LABELS.get(task["status"], task["status"].upper())
    lines.append(f"Status: {status}")
    priority = f"{task['priority_major']}.{task['priority_minor']}.{task['priority_patch']}"
    lines.append(f"Priority: {priority}")
    lines.append(f"Creator: {task['creator']}")
    if task.get("parent_id"):
        lines.append(f"Parent: {task['parent_id']}")
    if task.get("user_gated"):
        lines.append("User-gated: yes")
    tags = task.get("tags") or []
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")
    created = time.strftime("%Y-%m-%d %H:%M", time.localtime(task["created_at"]))
    updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(task["updated_at"]))
    lines.append(f"Created: {created}")
    lines.append(f"Updated: {updated}")
    if task.get("body"):
        lines.append("")
        lines.append(task["body"])
    return "\n".join(lines)


def format_task_list(tasks: list[dict], header: str = "") -> str:
    """Header + rows via format_task_row. Empty state message if no tasks."""
    if not tasks:
        return header + "\n(no tasks)" if header else "(no tasks)"
    lines = []
    if header:
        lines.append(header)
    lines.append(f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}:")
    for task in tasks:
        lines.append(f"  {format_task_row(task)}")
    return "\n".join(lines)


def format_search_results(tasks: list[dict], query: str) -> str:
    """Search header + results with rank indication."""
    if not tasks:
        return f"No results for '{query}'"
    lines = [f"Search: '{query}' ({len(tasks)} result{'s' if len(tasks) != 1 else ''})"]
    for i, task in enumerate(tasks, 1):
        lines.append(f"  #{i} {format_task_row(task)}")
    return "\n".join(lines)
