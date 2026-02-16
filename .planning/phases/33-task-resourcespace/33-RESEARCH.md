# Phase 33: Task Resourcespace - Research

**Researched:** 2026-02-16
**Domain:** Resourcespace protocol, SQLite persistence, FTS5 search, heapq priority ordering
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Fields: title, frontmatter (metadata), status, priority, tags, markdown body
- Priority uses semver-style tuple (major.minor.patch) for heapq ordering
- Tags are free-form strings with light friction for new tag creation; support AND/OR filtering semantics
- Track creator attribution (agent vs user)
- Created/updated timestamps
- Major versions (e.g., 1.0.0): full structured form, all sections enforced on creation
- Minor versions (e.g., 1.1.0): subtasks pointing to parent major, just title + own acceptance criteria
- Minor tasks complete independently; major task requires its own verification step even when all minors are done
- Priority IS the hierarchy -- semver encodes parent-child relationship
- Structured sections on creation: `<assumptions>`, `<reasoning/>`, `<background_research>`, `<acceptance_criteria/>`
- Structured sections on completion: `<outcome/>`, `<confidence/>`, `<retrospective/>`
- Five states: Open / In Progress / Blocked / Done / Cancelled
- Completion is final -- done tasks cannot be reopened (create new task instead)
- Done and Cancelled are both soft-delete (hidden from default view, never hard-deleted)
- Dependencies supported -- task B can be blocked by task A, entering Blocked state
- Status transitions logged (audit trail: when changed, by whom)
- No resolution note required on completion
- Default view: In Progress + Blocked at top, then Open tasks ordered by priority heap
- Done/Cancelled hidden from default view
- Each row shows: status, priority, title, tags (one line per task)
- Filtering supported via tool params: filter by tag, status, priority
- FTS search via .search()
- Tasks do NOT surface on session start -- only visible when navigating to tasks()
- No auto-resume of in-progress tasks
- Stale task detection is time-based (no activity for N days)
- Default: agent self-checks acceptance criteria before marking done
- Optional user gate: if user marks a task as user-gated, agent self-checks then asks user to confirm
- Major tasks always require verification even when all minor subtasks are complete

### Claude's Discretion
- SQLite schema design
- FTS5 configuration
- Exact display formatting and truncation
- How tag friction works (e.g., confirm new tag, suggest existing)
- Staleness threshold (N days)

### Deferred Ideas (OUT OF SCOPE)
- Alarming/scheduling as a separate resource -- stale task alarms, periodic checks, timer-based triggers
- Remove namespace object (`ns`) entirely -- everything becomes a resource
- Memory resourcespace (store/session as navigable resource) -- stays as Phase 34
- Background process for proactive stale task notification -- discuss when alarm resource is scoped
</user_constraints>

## Summary

Phase 33 adds a `tasks()` resourcespace backed by SQLite with FTS5 full-text search. The codebase already has an established resourcespace protocol (`Resourcespace` in `bae/repl/spaces/view.py`), a working SQLite+FTS5 pattern (`SessionStore` in `bae/repl/store.py`), and a mature example of a complex resourcespace with subresources and multiple tools (`SourceResourcespace` in `bae/repl/spaces/source/`).

The task resourcespace follows the existing view/service/models layering pattern. The service class implements `Resourcespace` protocol methods plus custom tool methods (`.add()`, `.done()`, `.update()`, `.search()`). The SQLite schema stores tasks with priority as three integer columns for heapq-compatible tuple ordering, tags in a junction table, status transitions in an audit log, and dependencies in a separate table. FTS5 indexes title + body using the external content pattern already proven in `store.py`.

**Primary recommendation:** Follow the `SourceResourcespace` pattern exactly (view/service/models split, protocol conformance, ResourceError for all errors with navigation hints). Place the DB at `{cwd}/.bae/tasks.db` alongside `store.db`. Register in `shell.py` the same way `source` is registered.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlite3 | stdlib | Task persistence and FTS5 | Already used by SessionStore; WAL mode, row_factory=sqlite3.Row |
| heapq | stdlib | Priority queue ordering | Semver tuples sort naturally as (major, minor, patch) |
| uuid | stdlib | Task ID generation | uuid7() already used by SessionStore for time-ordered IDs |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| time | stdlib | Timestamps | Created/updated timestamps, staleness detection |
| json | stdlib | Metadata serialization | Frontmatter stored as JSON in SQLite |
| re | stdlib | Tag validation | Light friction tag names |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sqlite3 | SQLAlchemy | Overkill for single-table CRUD; SessionStore sets the stdlib-only precedent |
| uuid7 | ULID | uuid7 already in use by store.py; consistency wins |
| Separate tasks.db | Same store.db | Separate DB keeps task data portable and independent of session store |

## Architecture Patterns

### Recommended Project Structure
```
bae/repl/spaces/
  tasks/
    __init__.py       # exports TaskResourcespace
    view.py           # Resourcespace protocol wrapper (thin, delegates to service)
    service.py        # TaskResourcespace class: CRUD, search, display, lifecycle
    models.py         # TaskStore: SQLite schema, queries, FTS5; data classes
```

### Pattern 1: Resourcespace Protocol Conformance
**What:** Every resourcespace implements the `Resourcespace` protocol from `bae/repl/spaces/view.py`
**When to use:** Always -- this is the navigation contract
**Example:**
```python
# Source: bae/repl/spaces/view.py (protocol definition)
@runtime_checkable
class Resourcespace(Protocol):
    name: str
    description: str
    def enter(self) -> str: ...
    def nav(self) -> str: ...
    def read(self, target: str = "") -> str: ...
    def supported_tools(self) -> set[str]: ...
    def children(self) -> dict[str, Resourcespace]: ...
    def tools(self) -> dict[str, Callable]: ...
```

The task resourcespace adds custom methods beyond the protocol (`.add()`, `.done()`, `.update()`, `.search()`) which get injected into the namespace alongside standard tools via `tools()`. These are NOT standard tool names from `_TOOL_NAMES` (`read`, `write`, `edit`, `glob`, `grep`) -- they are task-specific callables.

**Key insight from `_TOOL_NAMES` and `_put_tools()`:** The registry only manages the 5 standard tools. Custom methods like `.add()` and `.done()` need a different injection mechanism. Two options:

1. **Map to standard tools:** `.add()` -> `write()`, `.done()` -> `edit()` (conceptual stretch)
2. **Expose via the tools() dict with custom names:** The `_put_tools()` method in `ResourceRegistry` iterates `_TOOL_NAMES` but the `tools()` method returns arbitrary callables. The actual injection code is:
   ```python
   for tool_name, method in current.tools().items():
       self._namespace[tool_name] = self._make_tool_wrapper(tool_name, method)
   ```
   This injects whatever keys `tools()` returns, BUT `_put_tools()` only *removes* `_TOOL_NAMES` when switching. Custom names would persist across navigation unless cleaned up.

**Recommendation:** Extend `_TOOL_NAMES` or add a cleanup mechanism for custom tool names. Simplest: have `_put_tools()` also track and remove previously injected custom names. Or: use standard `read` for listing/reading, `write` for add/update, and provide `.done()` and `.search()` as extra callables returned from `tools()`.

### Pattern 2: External Content FTS5 with Triggers
**What:** FTS5 table backed by external content table, kept in sync via triggers
**When to use:** Full-text search over structured data that also needs SQL queries
**Example:**
```python
# Source: bae/repl/store.py (existing pattern)
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
```

For tasks, the FTS table should index title + body (the searchable text fields). Tags, status, and priority are better served by regular SQL WHERE clauses.

### Pattern 3: ResourceError with Navigation Hints
**What:** All errors include actionable hints with `resource()` hyperlink syntax
**When to use:** Every error path in the resourcespace
**Example:**
```python
# Source: bae/repl/spaces/view.py
raise ResourceError(
    f"Task '{task_id}' not found",
    hints=["tasks() to see all tasks", "search('keyword') to find tasks"],
)
```

### Pattern 4: NavResult for Display Strings
**What:** Return `NavResult(string)` from navigation methods so `repr()` preserves ANSI
**When to use:** Any string returned from `enter()`, `nav()`, or tool methods that will be displayed via `repr()` in the REPL

### Pattern 5: Registration in shell.py
**What:** Resourcespaces are registered in `CortexShell.__init__`
**When to use:** Exactly once, during shell initialization
**Example:**
```python
# Source: bae/repl/shell.py lines 241-243
source_rs = SourceResourcespace(Path.cwd())
self.registry.register(source_rs)
self.namespace["source"] = ResourceHandle("source", self.registry)
```
For tasks:
```python
task_rs = TaskResourcespace(Path.cwd() / ".bae" / "tasks.db")
self.registry.register(task_rs)
self.namespace["tasks"] = ResourceHandle("tasks", self.registry)
```

### Anti-Patterns to Avoid
- **Don't store priority as a string:** Use three INTEGER columns `(priority_major, priority_minor, priority_patch)` so ORDER BY works naturally and heapq can use the tuple directly.
- **Don't FTS-index metadata columns:** Tags, status, and priority are structured data; use SQL WHERE clauses, not full-text search. FTS is for title + body text.
- **Don't hardcode tool names as `_TOOL_NAMES` members:** Custom verbs like `add`, `done`, `search` aren't standard file tools. Track them separately.
- **Don't put the task DB inside store.db:** Separate concerns; tasks are a distinct resource with their own lifecycle.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Full-text search | Custom text scanning | SQLite FTS5 external content | Tokenization, ranking (BM25), prefix matching all built in |
| Priority sorting | Manual sort key generation | heapq with (major, minor, patch) tuples | stdlib, O(log n) insert, natural tuple comparison |
| UUID generation | Custom ID scheme | uuid.uuid7() | Time-ordered, already used by SessionStore |
| Parameter validation | Manual type checking | Pydantic via `_validate_tool_params` | Already integrated into tool wrapper pattern |

**Key insight:** The existing store.py already proves the FTS5 external content pattern works. Copy it exactly for the task table.

## Common Pitfalls

### Pitfall 1: Tool Name Collision
**What goes wrong:** Custom tool names (`add`, `done`, `search`, `update`) injected into namespace aren't cleaned up when navigating away, polluting namespace for next resource.
**Why it happens:** `_put_tools()` only removes names in `_TOOL_NAMES` (read, write, edit, glob, grep).
**How to avoid:** Either: (a) track injected custom names per-resource and clean them up in `_put_tools()`, or (b) use a `_custom_tool_names` set on the registry that gets cleared on navigation. Simplest approach: have `_put_tools()` also pop any names from a `_prev_custom` set.
**Warning signs:** After navigating from tasks() to source(), `add()` is still in namespace.

### Pitfall 2: FTS Trigger for UPDATE Missing
**What goes wrong:** Updating a task's title or body leaves stale content in the FTS index.
**Why it happens:** `store.py` doesn't have an UPDATE trigger (entries are insert-only). Tasks need UPDATE capability.
**How to avoid:** Add an AFTER UPDATE trigger that does delete-then-insert in the FTS table:
```sql
CREATE TRIGGER tasks_au AFTER UPDATE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, body)
        VALUES('delete', old.id, old.title, old.body);
    INSERT INTO tasks_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
```
**Warning signs:** Search returns stale results after task update.

### Pitfall 3: Semver Priority as Parent-Child Encoding
**What goes wrong:** Creating a minor task (1.1.0) requires knowing its parent (1.0.0) exists, but there's no foreign key enforcement.
**Why it happens:** Priority encodes hierarchy implicitly -- (1, 0, 0) is parent, (1, 1, 0) and (1, 2, 0) are children.
**How to avoid:** On minor task creation, validate that a major task with matching `major` component exists. Store `parent_id` column explicitly for direct lookup (priority encodes sort order, parent_id encodes hierarchy).
**Warning signs:** Orphan minor tasks with no parent major task.

### Pitfall 4: Blocked State Deadlock
**What goes wrong:** Task A blocked by Task B, Task B blocked by Task A.
**Why it happens:** No cycle detection in dependency graph.
**How to avoid:** On adding a dependency, walk the chain to detect cycles before inserting. With small task counts, a simple DFS from the target is sufficient.
**Warning signs:** Tasks stuck in Blocked state with no resolution path.

### Pitfall 5: Homespace Count Query Performance
**What goes wrong:** Counting outstanding tasks on every `home()` call queries the database.
**Why it happens:** The toolbar refreshes every 1 second, and home entry display calls count.
**How to avoid:** Cache the count in memory, invalidate on any task state change. The count only matters for display, not consistency. Or: only query on `home()` entry, not on toolbar refresh (TSK-08 says "Homespace entry shows outstanding task count").
**Warning signs:** Sluggish toolbar rendering.

## Code Examples

### SQLite Schema (Recommended)
```python
# Source: designed from existing store.py pattern + CONTEXT.md requirements
TASKS_SCHEMA = """
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
```

**Note on rowid:** FTS5 `content_rowid` must reference an integer. Since tasks use TEXT primary key (uuid7), use SQLite's implicit `rowid` column. The FTS table syncs via `rowid`, and we join back to tasks via `rowid` in search queries.

### Priority Tuple Ordering
```python
import heapq

# Tasks sorted by priority: (major, minor, patch)
# Lower numbers = higher priority (heapq is min-heap)
heap = []
heapq.heappush(heap, ((2, 0, 0), "low-priority task"))
heapq.heappush(heap, ((1, 0, 0), "high-priority major"))
heapq.heappush(heap, ((1, 1, 0), "subtask of major 1"))
heapq.heappush(heap, ((1, 2, 0), "second subtask"))

# Pop in priority order:
# (1, 0, 0) -> (1, 1, 0) -> (1, 2, 0) -> (2, 0, 0)
# Parent always comes before its children
```

### TaskResourcespace Skeleton
```python
class TaskResourcespace:
    name = "tasks"
    description = "Persistent task management with priority and search"

    def __init__(self, db_path: Path) -> None:
        self._store = TaskStore(db_path)

    def enter(self) -> str:
        """Show active task summary + functions table."""
        counts = self._store.status_counts()
        lines = [f"{self.description}\n"]
        lines.append(f"Open: {counts['open']}  In Progress: {counts['in_progress']}  Blocked: {counts['blocked']}")
        # Stale detection
        stale = self._store.stale_tasks(days=14)
        if stale:
            lines.append(f"Stale: {len(stale)} tasks with no activity for 14+ days")
        return "\n".join(lines)

    def supported_tools(self) -> set[str]:
        return {"read"}  # Standard tool: read for listing/details

    def tools(self) -> dict[str, Callable]:
        return {
            "read": self.read,      # List tasks or read task detail
            "add": self.add,        # Create task
            "done": self.done,      # Mark complete
            "update": self.update,  # Update fields
            "search": self.search,  # FTS search
        }
```

### Tag Friction Pattern
```python
def _tag_with_friction(self, task_id: str, new_tag: str) -> str:
    """Add tag, warning if it's new (not yet used by any task)."""
    existing = self._store.all_tags()
    if new_tag not in existing:
        # Light friction: warn but proceed
        result = self._store.add_tag(task_id, new_tag)
        return f"{result}\nNote: '{new_tag}' is a new tag. Existing tags: {', '.join(sorted(existing))}"
    return self._store.add_tag(task_id, new_tag)
```

### Default Listing Query
```sql
-- In Progress + Blocked first, then Open, ordered by priority heap
SELECT t.*, GROUP_CONCAT(tt.tag, ', ') as tags
FROM tasks t
LEFT JOIN task_tags tt ON t.id = tt.task_id
WHERE t.status IN ('in_progress', 'blocked', 'open')
GROUP BY t.id
ORDER BY
    CASE t.status
        WHEN 'in_progress' THEN 0
        WHEN 'blocked' THEN 1
        WHEN 'open' THEN 2
    END,
    t.priority_major, t.priority_minor, t.priority_patch
```

### Homespace Outstanding Count
```python
# In shell.py, during home() or orientation:
def _build_orientation(self) -> str:
    lines = ["home"]
    # ... existing code ...
    # Task count from TaskResourcespace
    if "tasks" in self._spaces:
        task_rs = self._spaces["tasks"]
        count = task_rs.outstanding_count()
        if count:
            lines.append(f"\nTasks: {count} outstanding")
    # ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FTS3/FTS4 | FTS5 | SQLite 3.9.0 (2015) | Better performance, BM25 ranking, external content |
| uuid4 (random) | uuid7 (time-ordered) | Python 3.14+ | Natural time ordering without extra timestamp column |
| Text-blob priority | Tuple integer priority | N/A (design choice) | heapq-compatible, SQL ORDER BY works natively |

**Deprecated/outdated:**
- FTS3/FTS4: Still works but FTS5 is the recommended replacement with better performance and features

## Open Questions

1. **Custom tool name cleanup in `_put_tools()`**
   - What we know: `_put_tools()` only removes `_TOOL_NAMES` (read/write/edit/glob/grep). Custom names like `add`, `done`, `search`, `update` will persist after navigating away.
   - What's unclear: Whether to extend `_TOOL_NAMES`, add a separate tracking mechanism, or accept this as a known limitation.
   - Recommendation: Add a `_prev_custom_tools: set[str]` on `ResourceRegistry` that gets cleared on each `_put_tools()` call. Minimal change, no protocol modification needed.

2. **FTS5 content_rowid with TEXT primary key**
   - What we know: FTS5 requires an integer rowid. Tasks use TEXT id (uuid7). SQLite provides implicit `rowid` for all tables.
   - What's unclear: Whether to use implicit rowid or add an explicit INTEGER id.
   - Recommendation: Use implicit `rowid`. It's always there, FTS5 works with it, and we join through it. The TEXT id remains the public-facing identifier.

3. **Structured section enforcement**
   - What we know: Major tasks must have `<assumptions>`, `<reasoning/>`, `<background_research>`, `<acceptance_criteria/>` in the body on creation.
   - What's unclear: Whether enforcement is in the service layer (Python validation) or relies on the agent to include them.
   - Recommendation: Validate in the service layer. Parse the body markdown on `.add()` and raise `ResourceError` if required sections are missing for major tasks. This ensures consistency regardless of whether the agent or user creates the task.

4. **Staleness threshold**
   - What we know: Stale = no activity for N days. Must be time-based.
   - What's unclear: What N should be.
   - Recommendation: 14 days. Long enough that active projects won't false-positive, short enough to catch abandoned tasks. Display stale count in `enter()` display.

## Sources

### Primary (HIGH confidence)
- `bae/repl/spaces/view.py` -- Resourcespace protocol, ResourceRegistry, ResourceHandle, NavResult, ResourceError
- `bae/repl/spaces/source/service.py` -- SourceResourcespace: complex resourcespace with subresources, multiple tools, error handling
- `bae/repl/store.py` -- SessionStore: SQLite + FTS5 external content pattern with triggers
- `bae/repl/shell.py` -- CortexShell: registration of resourcespaces, namespace injection, ResourceHandle creation
- `bae/repl/tools.py` -- ToolRouter: tool dispatch, parameter validation, pruning
- `tests/test_resource.py` -- Protocol conformance tests, registry tests, tool injection tests
- [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) -- Official FTS5 documentation: external content, tokenizers, triggers

### Secondary (MEDIUM confidence)
- [SQLite FTS5 Best Practices](https://www.slingacademy.com/article/best-practices-for-using-fts-virtual-tables-in-sqlite-applications/) -- FTS5 configuration patterns and performance tips
- [SQLite FTS5 in Practice](https://thelinuxcode.com/sqlite-full-text-search-fts5-in-practice-fast-search-ranking-and-real-world-patterns/) -- Real-world FTS5 patterns and ranking

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, patterns already proven in codebase
- Architecture: HIGH -- follows existing resourcespace convention exactly
- Pitfalls: HIGH -- identified from direct code reading of registry/tool injection
- Schema design: MEDIUM -- FTS5 rowid/TEXT-PK interaction needs validation during implementation

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (stable domain, stdlib-only stack)
