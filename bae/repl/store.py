"""SQLite persistence for REPL I/O with FTS5 full-text search."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

MAX_CONTENT = 10_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    cwd TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    timestamp REAL NOT NULL,
    mode TEXT NOT NULL,
    channel TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('input', 'output')),
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    content,
    content=entries,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, content)
        VALUES('delete', old.id, old.content);
END;

CREATE INDEX IF NOT EXISTS idx_entries_session ON entries(session_id);
CREATE INDEX IF NOT EXISTS idx_entries_mode ON entries(mode);
CREATE INDEX IF NOT EXISTS idx_entries_channel ON entries(channel);
CREATE INDEX IF NOT EXISTS idx_entries_timestamp ON entries(timestamp);
"""


class SessionStore:
    """SQLite persistence for REPL I/O."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self.session_id = str(uuid.uuid7())
        self._conn.execute(
            "INSERT INTO sessions(id, started_at, cwd) VALUES (?, ?, ?)",
            (self.session_id, time.time(), str(Path.cwd())),
        )
        self._conn.commit()

    def record(
        self,
        mode: str,
        channel: str,
        direction: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """Persist a single I/O entry."""
        meta = dict(metadata) if metadata else {}
        if len(content) > MAX_CONTENT:
            meta["truncated"] = True
            meta["original_length"] = len(content)
            content = content[:MAX_CONTENT]
        self._conn.execute(
            "INSERT INTO entries(session_id, timestamp, mode, channel, direction, content, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.session_id, time.time(), mode, channel, direction, content, json.dumps(meta)),
        )
        self._conn.commit()

    def search(self, query: str, limit: int = 20) -> list[sqlite3.Row]:
        """Full-text search across all entries."""
        return self._conn.execute(
            "SELECT e.* FROM entries_fts fts JOIN entries e ON e.id = fts.rowid "
            "WHERE fts.content MATCH ? ORDER BY e.timestamp DESC LIMIT ?",
            (query, limit),
        ).fetchall()

    def recent(self, n: int = 50) -> list[sqlite3.Row]:
        """Most recent entries across all sessions."""
        return self._conn.execute(
            "SELECT * FROM entries ORDER BY timestamp DESC LIMIT ?",
            (n,),
        ).fetchall()

    def session_entries(self, session_id: str | None = None) -> list[sqlite3.Row]:
        """All entries for a session (default: current)."""
        sid = session_id or self.session_id
        return self._conn.execute(
            "SELECT * FROM entries WHERE session_id = ? ORDER BY timestamp",
            (sid,),
        ).fetchall()

    def sessions(self) -> list[sqlite3.Row]:
        """List all sessions."""
        return self._conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC",
        ).fetchall()

    def __call__(self, query: str | None = None, n: int = 20) -> None:
        """Inspect stored context. store() shows session, store('query') searches."""
        if query:
            entries = self.search(query, limit=n)
            for e in entries:
                d = dict(e)
                print(f"[{d['mode']}:{d['channel']}:{d['direction']}] {d['content'][:80]}")
        else:
            entries = self.session_entries()
            print(f"Session {self.session_id}: {len(entries)} entries")
            for e in entries[-n:]:
                d = dict(e)
                print(f"  [{d['mode']}:{d['direction']}] {d['content'][:60]}")

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
