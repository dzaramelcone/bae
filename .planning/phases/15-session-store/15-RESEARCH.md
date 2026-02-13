# Phase 15: Session Store - Research

**Researched:** 2026-02-13
**Domain:** Local persistence layer for REPL I/O -- SQLite with FTS5, structured metadata, cross-session recall
**Confidence:** HIGH

## Summary

Phase 15 adds a persistence layer underneath the cortex REPL so that every input and output is automatically labeled, indexed, and stored in a SQLite database. The store serves three consumers: (1) the user, who can inspect what has been captured, (2) the future AI agent (Phase 18), which retrieves cross-session context via RAG queries, and (3) the future channel system (Phase 16), which writes channel-labeled output to the store.

The core technical finding is that **Python 3.14's built-in SQLite (3.51.2) has everything needed**. FTS5 is compiled in and working. JSON functions (`json_extract`, `json_object`) are available. No ORM or external database is required. The session store is a single `.db` file with a entries table, an FTS5 virtual table for text search, JSON metadata columns for structured queries, and indexes for common access patterns. This is ~100 lines of code for the store itself, plus ~50 lines to hook it into the REPL loop.

The key architectural decision is **where** the store hooks in. The REPL loop in `shell.py` has exactly two I/O points: (1) the return value of `session.prompt_async()` (user input), and (2) the output produced by each mode handler (Py exec result, bash stdout/stderr, NL stub text). Phase 15 wraps these points with store calls. Phase 16 (Channel I/O) later replaces raw output with channel-routed output, and channels write to the store themselves. But Phase 15 must not require channels -- it stores I/O directly.

For cross-session persistence (STORE-03), the store file lives at a project-local path (`.bae/store.db` in the working directory). This means each project gets its own session history -- when the AI loads context from previous sessions, it gets project-relevant context, not unrelated work. Session IDs use `uuid.uuid7()` (available in Python 3.14), which are time-sortable.

**Primary recommendation:** Build `bae/repl/store.py` with a `SessionStore` class backed by stdlib `sqlite3`. Use FTS5 for text search, JSON columns for structured metadata. Hook the store into `CortexShell.run()` with minimal changes to the REPL loop. Expose `store()` in the namespace for user inspection.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite3` (stdlib) | 3.51.2 (bundled) | Persistence backend | Zero dependencies. FTS5, JSON functions, WAL mode all available in Python 3.14's bundled SQLite. No external DB needed for a local REPL. |
| `uuid` (stdlib) | 3.14 | Session IDs via `uuid.uuid7()` | Time-sortable UUIDs. New in Python 3.14 (PEP 697). Sessions naturally sort chronologically. |
| `json` (stdlib) | 3.14 | Metadata serialization | Entry metadata stored as JSON text in SQLite. `json_extract()` in SQL queries, `json.dumps()` in Python. |
| `time` (stdlib) | 3.14 | Timestamps via `time.time()` | Floating-point epoch seconds for entry timestamps. Sortable, queryable in SQL. |
| `pathlib` (stdlib) | 3.14 | Store file path management | `.bae/store.db` relative to cwd. `Path.mkdir(parents=True, exist_ok=True)` for directory creation. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sqlite-vec` | 0.1.6 | Vector similarity search for future RAG | **NOT in Phase 15.** Verified working on Python 3.14 (tested). Listed here because STORE-02 mentions "structured for RAG queries." FTS5 covers keyword RAG. Vector RAG is a Phase 18 concern when the AI agent needs semantic similarity. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `sqlite3` | SQLAlchemy / Peewee ORM | ORM adds a dependency for ~5 tables. Raw SQL is simpler, explicit, and the queries are straightforward (INSERT, SELECT with WHERE/JOIN). ORM is overkill for this schema size. |
| SQLite file | JSON lines file (`.jsonl`) | JSONL is append-only and simple, but lacks indexing, FTS, and structured queries. Would need to load entire file for search. SQLite gives indexed queries, FTS5, and ACID for free. |
| Project-local `.bae/store.db` | Global `~/.bae/store.db` | Global store mixes context from different projects. Project-local keeps context relevant. Downside: user must be in the project directory. Mitigation: store also records `cwd` in session metadata. |
| `uuid.uuid7()` | Incrementing integer session IDs | Integers require coordination (read max, increment). uuid7 is globally unique and time-sortable with no coordination. |
| FTS5 for text search | Simple `LIKE '%term%'` queries | LIKE scans every row. FTS5 uses an inverted index -- O(1) lookup per term vs O(n) scan. For thousands of entries, FTS5 is necessary. |

**Installation:**
```bash
# No new dependencies. All stdlib.
```

## Architecture Patterns

### Recommended Project Structure

```
bae/repl/
    store.py        # SessionStore: SQLite persistence layer
    shell.py        # CortexShell: modified to call store on I/O (minimal changes)
    # ... existing files unchanged
```

### Pattern 1: SessionStore as Context Manager

**What:** A `SessionStore` class that opens a SQLite connection on init, creates tables if needed, and provides `record()` and `query()` methods. Passed into `CortexShell` as a dependency.

**When to use:** Every REPL session. Store is created during `CortexShell.__init__()` and closed during shutdown.

```python
import sqlite3
import json
import time
import uuid
from pathlib import Path

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
        self._conn.execute(
            "INSERT INTO entries(session_id, timestamp, mode, channel, direction, content, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.session_id, time.time(), mode, channel, direction, content, json.dumps(metadata or {})),
        )
        self._conn.commit()

    def search(self, query: str, limit: int = 20) -> list[sqlite3.Row]:
        """Full-text search across all entries."""
        return self._conn.execute(
            "SELECT e.* FROM entries_fts fts JOIN entries e ON e.id = fts.rowid WHERE fts.content MATCH ? ORDER BY e.timestamp DESC LIMIT ?",
            (query, limit),
        ).fetchall()

    def recent(self, n: int = 50) -> list[sqlite3.Row]:
        """Most recent entries across all sessions."""
        return self._conn.execute(
            "SELECT * FROM entries ORDER BY timestamp DESC LIMIT ?", (n,),
        ).fetchall()

    def session_entries(self, session_id: str | None = None) -> list[sqlite3.Row]:
        """All entries for a session (default: current)."""
        sid = session_id or self.session_id
        return self._conn.execute(
            "SELECT * FROM entries WHERE session_id = ? ORDER BY timestamp", (sid,),
        ).fetchall()

    def sessions(self) -> list[sqlite3.Row]:
        """List all sessions."""
        return self._conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC",
        ).fetchall()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
```

**Confidence:** HIGH -- verified FTS5, JSON functions, WAL mode, uuid7 all work on Python 3.14.3. Schema tested with INSERT, MATCH, json_extract queries.

### Pattern 2: REPL Loop Integration (Minimal Hooks)

**What:** The REPL loop in `shell.py` calls `store.record()` after each input and output. The changes to `shell.py` are surgical -- two `record()` calls in the main loop, one for input and one for output.

**When to use:** Every REPL turn.

```python
# In CortexShell.run(), the current loop:
#   text = await self.session.prompt_async()
#   ... mode dispatch ...
#
# Becomes:
#   text = await self.session.prompt_async()
#   self.store.record(self.mode.value, "repl", "input", text)
#   ... mode dispatch (output also recorded) ...

# Py mode example:
if self.mode == Mode.PY:
    try:
        result = await async_exec(text, self.namespace)
        if result is not None:
            output = repr(result)
            print(output)
            self.store.record("PY", "repl", "output", output, {"type": "expr_result"})
    except Exception:
        tb = traceback.format_exc()
        traceback.print_exc()
        self.store.record("PY", "repl", "output", tb, {"type": "error"})
```

**Confidence:** HIGH -- the integration points are clear from reading `shell.py`.

### Pattern 3: `store()` Namespace Callable for Inspection

**What:** A callable added to the REPL namespace that lets users inspect stored context. Satisfies STORE-04.

**When to use:** User wants to see what's been captured.

```python
def make_store_inspector(store: SessionStore):
    """Create a namespace callable for store inspection."""
    def store_fn(query: str | None = None, n: int = 20):
        if query:
            entries = store.search(query, limit=n)
            for e in entries:
                print(f"[{e['mode']}:{e['channel']}:{e['direction']}] {e['content'][:80]}")
        else:
            entries = store.session_entries()
            print(f"Session {store.session_id}: {len(entries)} entries")
            for e in entries[-n:]:
                print(f"  [{e['mode']}:{e['direction']}] {e['content'][:60]}")
        return entries
    store_fn.__doc__ = "Inspect stored context. store() shows current session, store('query') searches."
    return store_fn
```

**Confidence:** HIGH -- simple pattern. The callable is added to `self.namespace["store"]` in `CortexShell.__init__()`.

### Pattern 4: Project-Local Storage Path

**What:** Store file lives at `.bae/store.db` relative to the working directory where cortex launches. Each project gets isolated session history.

**When to use:** Always. The path is determined at `CortexShell.__init__()` time.

```python
store_path = Path.cwd() / ".bae" / "store.db"
self.store = SessionStore(store_path)
```

**Why project-local:**
- Cross-session context (STORE-03) should be project-relevant, not contaminated with other projects
- The AI agent (Phase 18) querying the store gets context about THIS project
- `.bae/` follows the convention of `.git/`, `.venv/`, `.mypy_cache/` -- project metadata directories
- User can add `.bae/` to `.gitignore` if they don't want to commit session data

**Confidence:** HIGH -- straightforward Path operations.

### Anti-Patterns to Avoid

- **Async SQLite wrapper:** sqlite3 operations are fast for small writes (microseconds). Wrapping in `asyncio.to_thread()` adds complexity for negligible benefit. A single `INSERT` does not block the event loop perceptibly. If this ever becomes a problem (bulk writes), batch writes in a background task. Do not pre-optimize.
- **Store as global singleton:** The store should be a field on `CortexShell`, injected at construction time. This keeps it testable (pass a `:memory:` store in tests) and explicit.
- **Recording to store inside `async_exec`:** The REPL loop owns recording, not the execution engine. `async_exec` should remain a pure execution function. The shell records input before dispatch and output after.
- **Storing raw binary/pickled objects:** Content must be text. If an output is a complex object, store `repr(obj)` or `json.dumps(obj.model_dump())` for Pydantic objects. Opaque blobs defeat STORE-02 (structured for RAG).
- **WAL mode without explicit pragma:** SQLite's default journal mode is DELETE. WAL (Write-Ahead Log) gives better concurrent read/write performance. Set `PRAGMA journal_mode=WAL` on connection open.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Full-text search | Custom inverted index / regex scanning | SQLite FTS5 | FTS5 handles tokenization, stemming, ranking, phrase queries, boolean operators. Tested working on Python 3.14.3. |
| Structured metadata queries | Custom JSON parser on text blobs | SQLite `json_extract()` | SQL-native JSON path queries. `WHERE json_extract(metadata, '$.model') = 'claude-sonnet-4'` works out of the box. |
| Session isolation | Manual file management per session | SQLite `WHERE session_id = ?` | Single database, multiple sessions via foreign key. No file-per-session management. |
| Schema migration | Custom version tracking | `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` | For Phase 15's small schema, idempotent DDL is sufficient. Schema migration tooling (Alembic) is overkill. If the schema evolves in future phases, add a `schema_version` table then. |
| Time-sortable IDs | Custom snowflake ID generator | `uuid.uuid7()` | stdlib, RFC 9562, 128-bit, time-sortable. New in Python 3.14. |

**Key insight:** The session store is a thin layer over stdlib sqlite3. The complexity is in the schema design and the hook placement in the REPL loop, not in the storage implementation.

## Common Pitfalls

### Pitfall 1: FTS5 Trigger Synchronization

**What goes wrong:** FTS5 `content=entries` tables require explicit triggers to stay in sync. If entries are inserted without triggers, the FTS index becomes stale -- searches return wrong results or crash.

**Why it happens:** FTS5's `content=` mode is an external content table. FTS5 does not automatically observe changes to the content table. You must create AFTER INSERT/UPDATE/DELETE triggers.

**How to avoid:** The schema includes `CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries ...`. This is set up during table creation. Never insert into `entries` outside of the normal SQL path (no raw writes to the shadow tables).

**Warning signs:** `SELECT * FROM entries_fts WHERE content MATCH 'x'` returns no results even though `entries` has matching rows.

### Pitfall 2: SQLite Connection Thread Safety

**What goes wrong:** sqlite3 connections cannot be shared across threads by default. Python 3.14 raises `ProgrammingError` if you use a connection from a different thread.

**Why it happens:** sqlite3 module checks thread ownership. Cortex is single-threaded (asyncio), so this should not happen, but if anyone calls store methods from a thread pool (e.g., `asyncio.to_thread()`), it will fail.

**How to avoid:** Keep all store operations on the main thread. The REPL loop is async but single-threaded. Store writes are synchronous and fast (microseconds). If thread access is ever needed, use `check_same_thread=False` on the connection, but do not do this by default.

**Warning signs:** `ProgrammingError: SQLite objects created in a thread can only be used in that same thread.`

### Pitfall 3: Forgetting to Commit

**What goes wrong:** SQLite operations are transactional. Without `conn.commit()`, changes are lost on crash or ungraceful exit.

**Why it happens:** Python's sqlite3 module auto-begins transactions but does not auto-commit.

**How to avoid:** Call `self._conn.commit()` after each `record()` call. For Phase 15, each entry is a single INSERT -- commit immediately. In future phases with batch writes, commit after the batch. Alternatively, use `conn.autocommit = True` (Python 3.12+ feature) but explicit commits are clearer.

**Warning signs:** Entries disappear after a cortex crash or Ctrl-C.

### Pitfall 4: Oversized Content Strings

**What goes wrong:** If a Python execution produces enormous output (megabytes of text), storing the entire output bloats the database.

**Why it happens:** `repr(result)` on a large data structure can produce unbounded text.

**How to avoid:** Truncate content at a reasonable limit (e.g., 10,000 characters) with a metadata flag `{"truncated": true}`. The full output was already displayed to the user in the terminal -- the store captures a searchable summary, not a byte-perfect copy.

**Warning signs:** `.bae/store.db` grows rapidly. `SELECT length(content) FROM entries ORDER BY length(content) DESC LIMIT 5` shows multi-megabyte entries.

### Pitfall 5: Storing Sensitive Data

**What goes wrong:** The store persists everything -- including passwords, API keys, or secrets the user types into the REPL.

**Why it happens:** STORE-01 says "all I/O." If the user types `export API_KEY=sk-...` in bash mode, that's stored.

**How to avoid:** This is a conscious design tradeoff. The store is project-local (not cloud-synced) and lives in `.bae/` which the user controls. Document that `.bae/store.db` contains session data and should be `.gitignore`d. Do NOT try to filter sensitive content automatically -- that's fragile and gives false confidence. The user owns their local data.

**Warning signs:** `.bae/store.db` committed to git.

## Code Examples

### Complete Schema (Verified on Python 3.14.3)

```python
# Source: Verified on Python 3.14.3 with SQLite 3.51.2
# FTS5, json_extract, INSERT/SELECT/MATCH all tested

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
```

### REPL Loop Integration

```python
# Source: Based on existing shell.py (Phase 14), showing minimal modifications

# In CortexShell.__init__():
self.store = SessionStore(Path.cwd() / ".bae" / "store.db")
self.namespace["store"] = make_store_inspector(self.store)

# In CortexShell.run(), after prompt_async:
text = await self.session.prompt_async()
if not text.strip():
    continue
self.store.record(self.mode.value, "repl", "input", text)

# After Py mode execution:
if result is not None:
    output = repr(result)
    print(output)
    self.store.record("PY", "repl", "output", output, {"type": "expr_result"})

# After Bash execution (in dispatch_bash or wrapper):
if stdout:
    self.store.record("BASH", "bash", "output", stdout[:10000])
if stderr:
    self.store.record("BASH", "bash", "output", stderr[:10000], {"type": "stderr"})
```

### Query Patterns for Future RAG (Phase 18)

```python
# Source: Verified on Python 3.14.3 with FTS5 + json_extract

# 1. Recent context for current project (cross-session)
recent = store._conn.execute("""
    SELECT e.mode, e.direction, e.content, s.started_at
    FROM entries e
    JOIN sessions s ON s.id = e.session_id
    WHERE s.cwd = ?
    ORDER BY e.timestamp DESC
    LIMIT 100
""", (str(Path.cwd()),)).fetchall()

# 2. Full-text search across all sessions
results = store._conn.execute("""
    SELECT e.*, s.cwd
    FROM entries_fts fts
    JOIN entries e ON e.id = fts.rowid
    JOIN sessions s ON s.id = e.session_id
    WHERE fts.content MATCH ?
    ORDER BY rank
    LIMIT 20
""", (query,)).fetchall()

# 3. Filter by mode and metadata
py_errors = store._conn.execute("""
    SELECT content, timestamp
    FROM entries
    WHERE mode = 'PY'
      AND json_extract(metadata, '$.type') = 'error'
    ORDER BY timestamp DESC
    LIMIT 10
""").fetchall()

# 4. Session summary
summary = store._conn.execute("""
    SELECT
        session_id,
        COUNT(*) as entry_count,
        MIN(timestamp) as first_entry,
        MAX(timestamp) as last_entry,
        COUNT(DISTINCT mode) as modes_used
    FROM entries
    GROUP BY session_id
    ORDER BY first_entry DESC
""").fetchall()
```

### User Inspection (STORE-04)

```python
# In the REPL, the user calls store():
# py> store()
# Session 019c58e6-1e1d-7607-ba79-1336de91d81d: 12 entries
#   [PY:input] x = 42
#   [PY:output] 42
#   [NL:input] what does the graph do?
#   [NL:output] (NL mode stub) what does the graph do?
#   [BASH:input] ls -la
#   [BASH:output] total 24...

# py> store("graph")
# [NL:repl:input] what does the graph do?
# [NL:repl:output] (NL mode stub) what does the graph do?

# py> store.sessions()  -- future: list all sessions
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JSON lines / pickle files | SQLite with FTS5 | FTS5 stable since SQLite 3.9 (2015) | Structured queries, full-text search, ACID guarantees |
| uuid4 for session IDs | `uuid.uuid7()` time-sortable | Python 3.14 (PEP 697) | Sessions sort chronologically without timestamp column |
| External vector DB (Pinecone, Qdrant) | sqlite-vec for local vector search | sqlite-vec 0.1.0 (Aug 2024) | Local-first RAG without server dependency |
| `asyncio.Queue.shutdown()` not available | Available in stdlib | Python 3.13 | Clean store shutdown without external libs |
| `get_event_loop()` for DB access | Single-thread sync access in async loop | Python 3.10+ (deprecated old) | No thread gymnastics needed for sqlite3 in asyncio |

**Deprecated/outdated:**
- `sqlite-vss` (Faiss-based vector search): Replaced by `sqlite-vec` which is pure C with no dependencies
- `aiosqlite` (async sqlite3 wrapper): Unnecessary for single-writer REPL workload. Sync sqlite3 writes are fast enough.

## Open Questions

1. **Should bash mode recording capture interleaved stdout/stderr or merged?**
   - What we know: `dispatch_bash()` currently gets stdout and stderr separately from `proc.communicate()`
   - What's unclear: Whether to store them as two entries (one stdout, one stderr) or merge into one entry with metadata distinguishing them
   - Recommendation: Two entries. Each with `channel="bash"`, metadata `{"stream": "stdout"}` or `{"stream": "stderr"}`. This preserves the structure.

2. **Content truncation limit**
   - What we know: Large outputs can bloat the database. FTS5 indexes all content.
   - What's unclear: What truncation limit balances searchability vs storage
   - Recommendation: 10,000 characters per entry. Metadata `{"truncated": true, "original_length": N}` when truncated. This covers most useful content while preventing multi-MB entries.

3. **When to add sqlite-vec for vector RAG?**
   - What we know: sqlite-vec 0.1.6 works on Python 3.14 (verified). STORE-02 says "structured for RAG queries."
   - What's unclear: Whether Phase 15 should add vector embeddings or defer to Phase 18 (AI Agent)
   - Recommendation: **Defer.** FTS5 keyword search satisfies STORE-02 for Phase 15. Vector embeddings require an embedding model, which is an AI concern. Phase 18 can add a `vec0` table alongside the existing FTS5 table. The schema is designed to be additive.

4. **Should store.record() be synchronous or async?**
   - What we know: SQLite writes complete in microseconds. The REPL is single-threaded async.
   - What's unclear: Whether `await store.record()` would be cleaner API even if the implementation is sync
   - Recommendation: **Synchronous.** `store.record()` is a single INSERT + commit. Making it async adds `await` noise everywhere for zero performance benefit. If writes ever become slow (they won't for single INSERTs), wrap in `to_thread` later.

5. **`.bae/` in .gitignore**
   - What we know: `.bae/store.db` contains session data that should not be committed
   - What's unclear: Whether Phase 15 should auto-create `.gitignore` or just document it
   - Recommendation: Document it. Do not auto-modify `.gitignore` -- that's a git operation that requires user consent.

## Sources

### Primary (HIGH confidence)
- [Python 3.14 sqlite3 docs](https://docs.python.org/3/library/sqlite3.html) -- DB-API 2.0, Row factory, executescript, autocommit
- [SQLite FTS5 Extension docs](https://www.sqlite.org/fts5.html) -- External content tables, triggers, MATCH, rank
- [SQLite JSON1 functions](https://www.sqlite.org/json1.html) -- json_extract, json_object, json_array
- Runtime verification on Python 3.14.3: FTS5 enabled (`ENABLE_FTS5` in compile options), JSON functions working, SQLite version 3.51.2
- Runtime verification: `uuid.uuid7()` produces time-sortable UUIDs on Python 3.14.3
- Runtime verification: FTS5 content tables with triggers, INSERT + MATCH queries working
- Runtime verification: `json_extract()` queries on metadata columns working
- [sqlite-vec v0.1.6](https://pypi.org/project/sqlite-vec/) -- Tested and working on Python 3.14 with `sqlite_vec.load(conn)`. KNN queries on vec0 virtual tables verified.

### Secondary (MEDIUM confidence)
- [sqlite-vec Python docs](https://alexgarcia.xyz/sqlite-vec/python.html) -- Python integration pattern
- [Building a RAG on SQLite](https://blog.sqlite.ai/building-a-rag-on-sqlite) -- FTS5 + sqlite-vector hybrid search pattern (Reciprocal Rank Fusion)
- [OpenAI Agents SDK SQLiteSession](https://openai.github.io/openai-agents-python/sessions/advanced_sqlite_session/) -- Prior art for session persistence with SQLite

### Tertiary (LOW confidence)
- platformdirs is available as transitive dep (v4.5.1 via fastmcp) but not used -- project-local `.bae/` is simpler and more appropriate

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All stdlib, no new dependencies. SQLite 3.51.2 with FTS5, JSON, all verified on Python 3.14.3.
- Architecture: HIGH -- REPL loop integration points identified from reading existing shell.py. Schema tested with real queries.
- Pitfalls: HIGH -- FTS5 trigger sync, thread safety, commit discipline all well-documented. Content truncation and sensitive data are practical concerns with clear mitigations.
- Future RAG integration: MEDIUM -- FTS5 keyword search is proven. Vector search (sqlite-vec) tested but deferred to Phase 18.

**Research date:** 2026-02-13
**Valid until:** 2026-03-15 (stable stdlib, unlikely to change)
