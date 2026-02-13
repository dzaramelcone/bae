"""Integration tests for SessionStore recording across all REPL modes."""

from __future__ import annotations

import json

import pytest

from bae.repl.bash import dispatch_bash
from bae.repl.store import SessionStore


@pytest.fixture
def store(tmp_path):
    """Create a SessionStore with a temporary database."""
    s = SessionStore(tmp_path / "test.db")
    yield s
    s.close()


def test_py_mode_records_input_and_output(store):
    """PY mode input and expr_result output are recorded with correct fields."""
    store.record("PY", "repl", "input", "2 + 2")
    store.record("PY", "repl", "output", "4", {"type": "expr_result"})
    entries = store.session_entries()
    assert len(entries) == 2

    inp = entries[0]
    assert inp["mode"] == "PY"
    assert inp["channel"] == "repl"
    assert inp["direction"] == "input"
    assert inp["content"] == "2 + 2"

    out = entries[1]
    assert out["mode"] == "PY"
    assert out["channel"] == "repl"
    assert out["direction"] == "output"
    assert out["content"] == "4"
    meta = json.loads(out["metadata"])
    assert meta["type"] == "expr_result"


def test_bash_mode_records_stdout_and_stderr(store):
    """BASH stdout and stderr are recorded as separate entries with stream metadata."""
    store.record("BASH", "stdout", "output", "file1.txt\nfile2.txt\n")
    store.record("BASH", "stderr", "output", "warning: something\n", {"type": "stderr"})
    entries = store.session_entries()
    assert len(entries) == 2

    stdout_entry = entries[0]
    assert stdout_entry["mode"] == "BASH"
    assert stdout_entry["channel"] == "stdout"
    assert stdout_entry["direction"] == "output"

    stderr_entry = entries[1]
    assert stderr_entry["mode"] == "BASH"
    assert stderr_entry["channel"] == "stderr"
    assert stderr_entry["direction"] == "output"
    meta = json.loads(stderr_entry["metadata"])
    assert meta["type"] == "stderr"


def test_nl_mode_records_stub(store):
    """NL mode input and stub output are recorded."""
    store.record("NL", "repl", "input", "summarize this")
    store.record("NL", "repl", "output", "(NL mode stub) summarize this\nNL mode coming in Phase 18.")
    entries = store.session_entries()
    assert len(entries) == 2
    assert entries[0]["mode"] == "NL"
    assert entries[0]["direction"] == "input"
    assert entries[1]["mode"] == "NL"
    assert entries[1]["direction"] == "output"


def test_store_inspector_prints_session(store, capsys):
    """store() prints session ID and entry count, returns None."""
    store.record("PY", "repl", "input", "x = 1")
    store.record("PY", "repl", "output", "None")
    store.record("PY", "repl", "input", "x + 1")
    result = store()
    captured = capsys.readouterr()
    assert f"Session {store.session_id}: 3 entries" in captured.out
    assert result is None


def test_store_inspector_search(store, capsys):
    """store('query') searches via FTS5 and prints matching entries, returns None."""
    store.record("PY", "repl", "input", "hello world")
    store.record("PY", "repl", "input", "goodbye moon")
    store.record("BASH", "stdout", "output", "hello again")
    result = store("hello")
    captured = capsys.readouterr()
    assert result is None
    assert "hello" in captured.out


def test_store_sessions_accessible(store):
    """store.sessions() returns a list including the current session ID."""
    sessions = store.sessions()
    assert isinstance(sessions, list)
    ids = [dict(s)["id"] for s in sessions]
    assert store.session_id in ids


@pytest.mark.asyncio
async def test_dispatch_bash_returns_tuple():
    """dispatch_bash returns a (stdout, stderr) tuple."""
    stdout, stderr = await dispatch_bash("echo hello")
    assert "hello" in stdout
    assert isinstance(stderr, str)


@pytest.mark.asyncio
async def test_dispatch_bash_cd_returns_empty(tmp_path):
    """dispatch_bash('cd /tmp') returns ('', '') on success."""
    import os

    original = os.getcwd()
    try:
        stdout, stderr = await dispatch_bash(f"cd {tmp_path}")
        assert stdout == ""
        assert stderr == ""
    finally:
        os.chdir(original)


def test_cross_session_persistence(tmp_path):
    """Multiple sessions on the same db file share data and are all visible."""
    db = tmp_path / "shared.db"

    s1 = SessionStore(db)
    s1.record("PY", "repl", "input", "session one input")
    s1.close()

    s2 = SessionStore(db)
    s2.record("BASH", "stdout", "output", "session two output")
    s2.close()

    s3 = SessionStore(db)
    sessions = s3.sessions()
    assert len(sessions) == 3  # s1, s2, s3

    recent = s3.recent()
    contents = [r["content"] for r in recent]
    assert "session one input" in contents
    assert "session two output" in contents
    s3.close()
