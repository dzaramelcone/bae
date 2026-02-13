"""Tests for SessionStore SQLite persistence layer."""

from __future__ import annotations

import sqlite3

import pytest

from bae.repl.store import SessionStore


@pytest.fixture
def store(tmp_path):
    """Create a SessionStore with a temporary database."""
    s = SessionStore(tmp_path / "test.db")
    yield s
    s.close()


def test_init_creates_session(tmp_path):
    """SessionStore creates a session row with uuid7 id, timestamp, and cwd."""
    s = SessionStore(tmp_path / "test.db")
    rows = s._conn.execute("SELECT id, started_at, cwd FROM sessions").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert len(row["id"]) == 36  # UUID format
    assert row["started_at"] > 0
    assert row["cwd"]  # non-empty
    s.close()


def test_record_persists_entry(store):
    """record() inserts a row with correct session_id, mode, channel, direction, content."""
    store.record("PY", "repl", "input", "x = 42")
    rows = store._conn.execute("SELECT * FROM entries").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == store.session_id
    assert row["mode"] == "PY"
    assert row["channel"] == "repl"
    assert row["direction"] == "input"
    assert row["content"] == "x = 42"
    assert row["timestamp"] > 0


def test_record_with_metadata(store):
    """record() stores JSON metadata retrievable via json_extract."""
    store.record("PY", "repl", "output", "42", {"type": "expr_result"})
    row = store._conn.execute(
        "SELECT json_extract(metadata, '$.type') AS mtype FROM entries"
    ).fetchone()
    assert row["mtype"] == "expr_result"


def test_search_fts(store):
    """search() returns entries matching FTS5 MATCH query."""
    store.record("PY", "repl", "input", "hello world")
    store.record("PY", "repl", "input", "goodbye world")
    store.record("PY", "repl", "input", "something else")
    results = store.search("hello")
    assert len(results) == 1
    assert results[0]["content"] == "hello world"


def test_search_returns_empty_for_no_match(store):
    """search() returns empty list when no entries match."""
    store.record("PY", "repl", "input", "hello world")
    results = store.search("nonexistent")
    assert results == []


def test_recent_returns_latest(store):
    """recent(n) returns the n most recent entries by timestamp descending."""
    import time

    for i in range(5):
        store.record("PY", "repl", "input", f"entry {i}")
        time.sleep(0.01)  # ensure distinct timestamps
    results = store.recent(3)
    assert len(results) == 3
    # Most recent first
    assert results[0]["content"] == "entry 4"
    assert results[1]["content"] == "entry 3"
    assert results[2]["content"] == "entry 2"


def test_session_entries_returns_current(store):
    """session_entries() returns only entries for the current session."""
    store.record("PY", "repl", "input", "current session entry")
    # Insert an entry for a fake different session directly
    store._conn.execute(
        "INSERT INTO entries(session_id, timestamp, mode, channel, direction, content) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("other-session-id", 0.0, "PY", "repl", "input", "other session entry"),
    )
    store._conn.commit()
    results = store.session_entries()
    assert len(results) == 1
    assert results[0]["content"] == "current session entry"


def test_sessions_lists_all(store):
    """sessions() returns a list including the current session."""
    results = store.sessions()
    assert len(results) >= 1
    ids = [r["id"] for r in results]
    assert store.session_id in ids


def test_content_truncation(store):
    """Content longer than 10,000 chars is truncated with metadata flag."""
    long_content = "x" * 15_000
    store.record("PY", "repl", "output", long_content)
    row = store._conn.execute("SELECT content, metadata FROM entries").fetchone()
    assert len(row["content"]) == 10_000
    import json

    meta = json.loads(row["metadata"])
    assert meta["truncated"] is True
    assert meta["original_length"] == 15_000


def test_close(store):
    """After close(), further operations raise."""
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        store.record("PY", "repl", "input", "should fail")
