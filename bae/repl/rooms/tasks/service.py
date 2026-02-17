"""Task room: navigable task management with priority and search.

Implements the Room protocol, delegating storage to TaskStore.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from bae.repl.rooms.view import ResourceError, Room
from bae.repl.rooms.tasks.models import TaskStore, _MAJOR_REQUIRED_SECTIONS
from bae.repl.rooms.tasks.view import (
    format_task_detail,
    format_task_list,
    format_search_results,
)


def _parse_priority(s: str) -> tuple[int, int, int]:
    """Parse 'major.minor.patch' string into tuple."""
    parts = s.split(".")
    if len(parts) != 3:
        raise ResourceError(
            f"Invalid priority '{s}'. Use major.minor.patch format (e.g. '1.0.0').",
            hints=["Priority format: major.minor.patch (e.g. 1.0.0, 2.1.0)"],
        )
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        raise ResourceError(
            f"Invalid priority '{s}'. Each part must be an integer.",
            hints=["Priority format: major.minor.patch (e.g. 1.0.0, 2.1.0)"],
        )


class TaskRoom:
    """Persistent task management with priority and search."""

    name = "tasks"
    description = "Manage todo lists"

    def __init__(self, db_path: Path) -> None:
        self._store = TaskStore(db_path)

    def enter(self) -> str:
        """Status counts and stale task warning."""
        counts = self._store.status_counts()
        lines = [
            f"open: {counts['open']}  in_progress: {counts['in_progress']}  blocked: {counts['blocked']}",
        ]
        stale = self._store.stale_tasks()
        if stale:
            lines.append(f"\nStale: {len(stale)} task{'s' if len(stale) != 1 else ''} with no activity for 14+ days")
        return "\n".join(lines)

    def nav(self) -> str:
        """No subresources."""
        return ""

    def read(self, target: str = "") -> str:
        """List active tasks, read a task by ID, or filter by status/tag/priority."""
        if not target:
            tasks = self._store.list_active()
            return format_task_list(tasks, "Active tasks")

        # Filter: status:value, tag:value, priority:value
        if ":" in target:
            key, _, value = target.partition(":")
            if key == "status":
                tasks = self._store.list_active(status_filter=value)
                return format_task_list(tasks, f"Tasks with status '{value}'")
            elif key == "tag":
                tasks = self._store.list_active(tag_filter=[value])
                return format_task_list(tasks, f"Tasks tagged '{value}'")
            elif key == "priority":
                pri = _parse_priority(value)
                tasks = self._store.list_active(priority_filter=pri)
                return format_task_list(tasks, f"Tasks at priority {value}")
            else:
                raise ResourceError(
                    f"Unknown filter '{key}'.",
                    hints=["Filters: status:<value>, tag:<value>, priority:<major.minor.patch>"],
                )

        # Task ID lookup
        try:
            task = self._store.get(target)
            return format_task_detail(task)
        except ValueError:
            raise ResourceError(
                f"Task '{target}' not found.",
                hints=["read() to list all tasks", "grep('keyword') to search"],
            )

    def write(self, title: str, body: str = "", priority: str = "0.0.0", creator: str = "agent", parent: str = "", tags: str = "") -> str:
        """Create a task with title, body, priority, and tags."""
        pri = _parse_priority(priority)

        # Parse tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        # Check for new tags
        existing_tags = self._store.all_tags()
        new_tags = [t for t in tag_list if t not in existing_tags]

        # Major task body validation hint
        if pri[1] == 0 and pri[2] == 0 and pri[0] > 0:
            missing = [s for s in _MAJOR_REQUIRED_SECTIONS if s not in body]
            if missing:
                raise ResourceError(
                    f"Major task body must contain structured sections: {', '.join(missing)}",
                    hints=[f"Include {', '.join(missing)} in body"],
                )

        try:
            task = self._store.create(
                title=title,
                body=body,
                priority=pri,
                creator=creator,
                parent_id=parent or None,
                user_gated=False,
            )
        except ValueError as e:
            raise ResourceError(str(e), hints=["read() to list all tasks"])

        # Add tags
        for tag in tag_list:
            self._store.add_tag(task["id"], tag)

        # Build response
        result = f"Created task {task['id']}: {title}"
        if new_tags and existing_tags:
            result += f"\nNew tag{'s' if len(new_tags) != 1 else ''}: {', '.join(new_tags)}"
            result += f"\nExisting tags: {', '.join(sorted(existing_tags))}"
        return result

    def edit(self, task_id: str, **kwargs) -> str:
        """Update task fields: status, priority, title, body, tags, user_gated."""
        try:
            self._store.get(task_id)
        except ValueError:
            raise ResourceError(
                f"Task '{task_id}' not found.",
                hints=["read() to list all tasks"],
            )

        # Parse tags from comma-separated string
        if "tags" in kwargs and isinstance(kwargs["tags"], str):
            tag_str = kwargs.pop("tags")
            tag_list = [t.strip() for t in tag_str.split(",") if t.strip()]
            current = self._store.get(task_id)
            merged = list(set(current["tags"]) | set(tag_list))
            kwargs["tags"] = merged

        # Parse priority string if provided
        if "priority" in kwargs:
            pri = _parse_priority(kwargs.pop("priority"))
            kwargs["priority_major"] = pri[0]
            kwargs["priority_minor"] = pri[1]
            kwargs["priority_patch"] = pri[2]

        # status="done" goes through mark_done for lifecycle validation
        if kwargs.get("status") == "done":
            remaining = {k: v for k, v in kwargs.items() if k != "status"}
            if remaining:
                self._store.update(task_id, **remaining)
            try:
                result = self._store.mark_done(task_id)
            except ValueError as e:
                raise ResourceError(str(e), hints=["read() to list all tasks"])
            response = f"Updated\n{format_task_detail(result)}"
            undone = result.get("_subtasks_undone")
            if undone:
                response += f"\nNote: {len(undone)} subtask{'s' if len(undone) != 1 else ''} still open"
            return response

        try:
            result = self._store.update(task_id, **kwargs)
        except ValueError as e:
            raise ResourceError(str(e), hints=["read() to list all tasks"])

        return f"Updated\n{format_task_detail(result)}"

    def grep(self, query: str) -> str:
        """Full-text search across task titles and bodies."""
        try:
            results = self._store.search(query)
        except Exception:
            results = []
        # Fall back to LIKE for short/unindexed terms
        if not results:
            results = self._store.search_like(query)
        if not results:
            return format_search_results([], query) + "\nTry: read() to list all active tasks, or broader keywords"
        return format_search_results(results, query)

    def glob(self, pattern: str) -> str:
        """Match task titles by glob pattern."""
        import fnmatch
        # Auto-wrap bare strings: "oo" → "*oo*"
        if "*" not in pattern and "?" not in pattern and "[" not in pattern:
            pattern = f"*{pattern}*"
        tasks = self._store.list_all()
        matched = [t for t in tasks if fnmatch.fnmatch(t["title"].lower(), pattern.lower())]
        if not matched:
            return f"No tasks matching '{pattern}'"
        return format_task_list(matched, f"Tasks matching '{pattern}'")

    def status_counts(self) -> dict[str, int]:
        """Count of tasks per status."""
        return self._store.status_counts()

    def outstanding_count(self) -> int:
        """Count of open + in_progress + blocked tasks."""
        return self._store.outstanding_count()

    def supported_tools(self) -> set[str]:
        return {"read", "write", "edit", "glob", "grep"}

    def tools(self) -> dict[str, Callable]:
        return {
            "read": self.read,
            "write": self.write,
            "edit": self.edit,
            "glob": self.glob,
            "grep": self.grep,
        }

    def children(self) -> dict[str, Room]:
        return {}
