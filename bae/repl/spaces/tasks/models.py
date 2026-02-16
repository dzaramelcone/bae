"""SQLite persistence for task management with FTS5 full-text search."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open', 'in_progress', 'blocked', 'done', 'cancelled')),
    priority_major INTEGER NOT NULL DEFAULT 0,
    priority_minor INTEGER NOT NULL DEFAULT 0,
    priority_patch INTEGER NOT NULL DEFAULT 0,
    parent_id TEXT REFERENCES tasks(id),
    creator TEXT NOT NULL DEFAULT 'agent'
        CHECK(creator IN ('agent', 'user')),
    user_gated INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id TEXT NOT NULL REFERENCES tasks(id),
    tag TEXT NOT NULL,
    PRIMARY KEY (task_id, tag)
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id),
    blocked_by TEXT NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (task_id, blocked_by)
);

CREATE TABLE IF NOT EXISTS task_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    timestamp REAL NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by TEXT NOT NULL DEFAULT 'agent'
);

CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
    title, body,
    content=tasks,
    content_rowid=rowid,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS tasks_ai AFTER INSERT ON tasks BEGIN
    INSERT INTO tasks_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS tasks_ad AFTER DELETE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, body)
        VALUES('delete', old.rowid, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS tasks_au AFTER UPDATE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, body)
        VALUES('delete', old.rowid, old.title, old.body);
    INSERT INTO tasks_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority_major, priority_minor, priority_patch);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
"""

_FINAL_STATUSES = frozenset({"done", "cancelled"})
_ACTIVE_STATUSES = frozenset({"open", "in_progress", "blocked"})
_VALID_STATUSES = frozenset({"open", "in_progress", "blocked", "done", "cancelled"})

_MAJOR_REQUIRED_SECTIONS = {"<assumptions>", "<reasoning", "<background_research>", "<acceptance_criteria"}
_COMPLETION_SECTIONS = {"<outcome>", "<confidence>", "<retrospective>"}

_UPDATABLE_FIELDS = frozenset({
    "title", "body", "status", "priority_major", "priority_minor",
    "priority_patch", "tags", "user_gated", "metadata",
})


class TaskStore:
    """SQLite persistence for task management."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")

    def create(
        self,
        title: str,
        body: str = "",
        priority: tuple[int, int, int] = (0, 0, 0),
        creator: str = "agent",
        parent_id: str | None = None,
        user_gated: bool = False,
        metadata: dict | None = None,
    ) -> dict:
        """Insert a task and return it as a dict."""
        major, minor, patch = priority
        now = time.time()
        task_id = str(uuid.uuid7())

        # Major task body validation
        if minor == 0 and patch == 0:
            for section in _MAJOR_REQUIRED_SECTIONS:
                if section not in body:
                    raise ValueError(
                        f"Major task body must contain {section}. "
                        f"Missing sections: {', '.join(s for s in _MAJOR_REQUIRED_SECTIONS if s not in body)}"
                    )

        # Minor task parent validation
        if minor > 0:
            if parent_id is None:
                # Find parent by matching major number
                row = self._conn.execute(
                    "SELECT id FROM tasks WHERE priority_major = ? AND priority_minor = 0 AND priority_patch = 0",
                    (major,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"No major task found with priority_major={major}")
                parent_id = row["id"]
            else:
                parent = self._conn.execute("SELECT id FROM tasks WHERE id = ?", (parent_id,)).fetchone()
                if parent is None:
                    raise ValueError(f"Parent task '{parent_id}' not found")

        self._conn.execute(
            "INSERT INTO tasks(id, title, body, priority_major, priority_minor, priority_patch, "
            "parent_id, creator, user_gated, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, title, body, major, minor, patch, parent_id, creator,
             int(user_gated), now, now, json.dumps(metadata or {})),
        )
        self._conn.commit()
        return self.get(task_id)

    def get(self, task_id: str) -> dict:
        """Fetch a task by id with tags. Raises ValueError if not found."""
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError(f"Task '{task_id}' not found")
        return self._task_to_dict(row)

    def list_active(
        self,
        status_filter: str | None = None,
        tag_filter: list[str] | None = None,
        priority_filter: tuple[int, int, int] | None = None,
    ) -> list[dict]:
        """Active tasks: in_progress + blocked first, then open, ordered by priority."""
        if status_filter:
            query = (
                "SELECT t.* FROM tasks t WHERE t.status = ? "
                "ORDER BY t.priority_major, t.priority_minor, t.priority_patch"
            )
            params: list = [status_filter]
        else:
            query = (
                "SELECT t.* FROM tasks t WHERE t.status IN ('in_progress', 'blocked', 'open') "
                "ORDER BY CASE t.status "
                "WHEN 'in_progress' THEN 0 WHEN 'blocked' THEN 1 WHEN 'open' THEN 2 END, "
                "t.priority_major, t.priority_minor, t.priority_patch"
            )
            params = []

        rows = self._conn.execute(query, params).fetchall()
        result = [self._task_to_dict(row) for row in rows]

        if tag_filter:
            result = [
                t for t in result
                if all(tag in t["tags"] for tag in tag_filter)
            ]

        if priority_filter:
            maj, mi, pa = priority_filter
            result = [
                t for t in result
                if t["priority_major"] == maj and t["priority_minor"] == mi and t["priority_patch"] == pa
            ]

        return result

    def list_all(self, include_done: bool = False) -> list[dict]:
        """All tasks, optionally including done/cancelled."""
        if include_done:
            query = (
                "SELECT * FROM tasks ORDER BY "
                "priority_major, priority_minor, priority_patch"
            )
        else:
            query = (
                "SELECT * FROM tasks WHERE status NOT IN ('done', 'cancelled') ORDER BY "
                "priority_major, priority_minor, priority_patch"
            )
        rows = self._conn.execute(query).fetchall()
        return [self._task_to_dict(row) for row in rows]

    def update(self, task_id: str, changed_by: str = "agent", **fields) -> dict:
        """Update allowed fields, log each change in audit."""
        task = self.get(task_id)

        # Handle tags separately
        tags = fields.pop("tags", None)

        for key in fields:
            if key not in _UPDATABLE_FIELDS:
                raise ValueError(f"Cannot update field '{key}'")

        # Enforce lifecycle: done/cancelled are final
        if "status" in fields:
            new_status = fields["status"]
            if new_status not in _VALID_STATUSES:
                raise ValueError(f"Invalid status '{new_status}'")
            if task["status"] in _FINAL_STATUSES:
                raise ValueError(
                    f"Task is '{task['status']}' (final). Create a new task instead."
                )

        for key, value in fields.items():
            old_value = task.get(key)
            if old_value != value:
                self._audit(task_id, key, str(old_value), str(value), changed_by)

        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values())
            values.append(time.time())
            values.append(task_id)
            self._conn.execute(
                f"UPDATE tasks SET {set_clause}, updated_at = ? WHERE id = ?",
                values,
            )
            self._conn.commit()

        if tags is not None:
            # Replace all tags
            current_tags = set(task["tags"])
            new_tags = set(tags)
            for tag in current_tags - new_tags:
                self.remove_tag(task_id, tag)
            for tag in new_tags - current_tags:
                self.add_tag(task_id, tag)

        return self.get(task_id)

    def mark_done(self, task_id: str, changed_by: str = "agent") -> dict:
        """Transition task to done. Checks dependencies and completion sections."""
        task = self.get(task_id)

        if task["status"] in _FINAL_STATUSES:
            raise ValueError(f"Task is already '{task['status']}'")

        # Check dependencies
        blockers = self._conn.execute(
            "SELECT d.blocked_by, t.status FROM task_dependencies d "
            "JOIN tasks t ON t.id = d.blocked_by "
            "WHERE d.task_id = ? AND t.status NOT IN ('done', 'cancelled')",
            (task_id,),
        ).fetchall()
        if blockers:
            ids = [row["blocked_by"] for row in blockers]
            raise ValueError(f"Task blocked by unfinished tasks: {', '.join(ids)}")

        # Major task completion validation
        is_major = task["priority_minor"] == 0 and task["priority_patch"] == 0
        if is_major:
            for section in _COMPLETION_SECTIONS:
                if section not in task["body"]:
                    raise ValueError(
                        f"Major task must contain completion sections before done. "
                        f"Missing: {', '.join(s for s in _COMPLETION_SECTIONS if s not in task['body'])}"
                    )

        self._audit(task_id, "status", task["status"], "done", changed_by)
        self._conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ?",
            (time.time(), task_id),
        )
        self._conn.commit()

        result = self.get(task_id)

        # Major task self-verification
        if is_major:
            subtasks = self._conn.execute(
                "SELECT id, status FROM tasks WHERE parent_id = ?", (task_id,)
            ).fetchall()
            undone = [r["id"] for r in subtasks if r["status"] not in _FINAL_STATUSES]
            if undone:
                result["_subtasks_undone"] = undone

        if task["user_gated"]:
            result["_user_gated"] = True

        return result

    def cancel(self, task_id: str, changed_by: str = "agent") -> dict:
        """Transition task to cancelled."""
        task = self.get(task_id)
        if task["status"] in _FINAL_STATUSES:
            raise ValueError(f"Task is already '{task['status']}'")
        self._audit(task_id, "status", task["status"], "cancelled", changed_by)
        self._conn.execute(
            "UPDATE tasks SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (time.time(), task_id),
        )
        self._conn.commit()
        return self.get(task_id)

    def add_tag(self, task_id: str, tag: str) -> str:
        """Add a tag to a task. Returns the tag name."""
        self.get(task_id)  # validate exists
        self._conn.execute(
            "INSERT OR IGNORE INTO task_tags(task_id, tag) VALUES (?, ?)",
            (task_id, tag),
        )
        self._conn.commit()
        return tag

    def remove_tag(self, task_id: str, tag: str) -> str:
        """Remove a tag from a task. Returns the tag name."""
        self.get(task_id)  # validate exists
        self._conn.execute(
            "DELETE FROM task_tags WHERE task_id = ? AND tag = ?",
            (task_id, tag),
        )
        self._conn.commit()
        return tag

    def all_tags(self) -> set[str]:
        """Distinct tags across all tasks."""
        rows = self._conn.execute("SELECT DISTINCT tag FROM task_tags").fetchall()
        return {row["tag"] for row in rows}

    def add_dependency(self, task_id: str, blocked_by_id: str) -> None:
        """Add dependency with cycle detection."""
        self.get(task_id)
        self.get(blocked_by_id)

        # Cycle detection: DFS from blocked_by_id looking for task_id
        if self._has_path(blocked_by_id, task_id):
            raise ValueError(
                f"Cycle detected: {blocked_by_id} already depends on {task_id}"
            )

        self._conn.execute(
            "INSERT OR IGNORE INTO task_dependencies(task_id, blocked_by) VALUES (?, ?)",
            (task_id, blocked_by_id),
        )

        # Set status to blocked if currently open
        task = self.get(task_id)
        if task["status"] == "open":
            self._conn.execute(
                "UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?",
                (time.time(), task_id),
            )
            self._audit(task_id, "status", "open", "blocked", "agent")

        self._conn.commit()

    def remove_dependency(self, task_id: str, blocked_by_id: str) -> None:
        """Remove dependency. If no remaining blockers, transition from blocked to open."""
        self._conn.execute(
            "DELETE FROM task_dependencies WHERE task_id = ? AND blocked_by = ?",
            (task_id, blocked_by_id),
        )

        remaining = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM task_dependencies WHERE task_id = ?",
            (task_id,),
        ).fetchone()["cnt"]

        task = self.get(task_id)
        if remaining == 0 and task["status"] == "blocked":
            self._conn.execute(
                "UPDATE tasks SET status = 'open', updated_at = ? WHERE id = ?",
                (time.time(), task_id),
            )
            self._audit(task_id, "status", "blocked", "open", "agent")

        self._conn.commit()

    def search(self, query: str) -> list[dict]:
        """FTS5 search on title + body. Returns tasks ordered by BM25 rank."""
        rows = self._conn.execute(
            "SELECT t.* FROM tasks_fts fts "
            "JOIN tasks t ON t.rowid = fts.rowid "
            "WHERE tasks_fts MATCH ? "
            "ORDER BY bm25(tasks_fts)",
            (query,),
        ).fetchall()
        return [self._task_to_dict(row) for row in rows]

    def status_counts(self) -> dict[str, int]:
        """Count of tasks per status."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ).fetchall()
        counts = {s: 0 for s in _VALID_STATUSES}
        for row in rows:
            counts[row["status"]] = row["cnt"]
        return counts

    def stale_tasks(self, days: int = 14) -> list[dict]:
        """Tasks with no activity for N days, status in open/in_progress."""
        cutoff = time.time() - (days * 86400)
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE updated_at < ? AND status IN ('open', 'in_progress') "
            "ORDER BY updated_at",
            (cutoff,),
        ).fetchall()
        return [self._task_to_dict(row) for row in rows]

    def outstanding_count(self) -> int:
        """Count of open + in_progress + blocked tasks."""
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status IN ('open', 'in_progress', 'blocked')"
        ).fetchone()
        return row["cnt"]

    def _audit(self, task_id: str, field: str, old: str, new: str, changed_by: str) -> None:
        """Log a field change to the audit table."""
        self._conn.execute(
            "INSERT INTO task_audit(task_id, timestamp, field, old_value, new_value, changed_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, time.time(), field, old, new, changed_by),
        )

    def _task_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a sqlite3.Row to dict with tags list attached."""
        d = dict(row)
        tags_rows = self._conn.execute(
            "SELECT tag FROM task_tags WHERE task_id = ?", (d["id"],)
        ).fetchall()
        d["tags"] = [r["tag"] for r in tags_rows]
        return d

    def _has_path(self, from_id: str, to_id: str) -> bool:
        """DFS cycle detection: check if from_id transitively depends on to_id."""
        visited: set[str] = set()
        stack = [from_id]
        while stack:
            current = stack.pop()
            if current == to_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            deps = self._conn.execute(
                "SELECT blocked_by FROM task_dependencies WHERE task_id = ?",
                (current,),
            ).fetchall()
            stack.extend(row["blocked_by"] for row in deps)
        return False
