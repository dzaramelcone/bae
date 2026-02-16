# Stack Research

**Domain:** Hypermedia resourcespace, context-scoped tools, agent navigation
**Researched:** 2026-02-16
**Confidence:** HIGH

## Recommendation: Zero New Dependencies

Like v6.0, this milestone requires no new packages. Hypermedia resourcespace is a design pattern over existing infrastructure, not a technology problem. The resource tree, context-scoped tools, navigation, and cross-resourcespace search all map to Python 3.14 stdlib + existing dependencies (Pydantic 2.12.5, Rich 14.3.2, SQLite/FTS5 via SessionStore).

The closest external temptation is a tree library or URL-routing framework. Neither is warranted. The resource tree is a shallow dict-of-dicts with path-based lookup -- `dict` and `str.split("/")` cover it. URL routing frameworks (Starlette, FastAPI router) solve HTTP dispatch, not in-process namespace navigation.

**pyproject.toml: No changes.**

---

## Recommended Stack

### Resourcespace Core (Tree + Navigation)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `dict[str, Resource]` | stdlib | Resource tree registry | Flat dict with `/`-delimited keys. Resources register at paths like `/home`, `/source/bae/node.py`, `/memory/sessions`. No need for actual tree nodes -- path prefix matching via `str.startswith()` handles subtree queries. Same pattern as ChannelRouter._channels. |
| `Pydantic BaseModel` | 2.12.5 | Resource and Tool schema definitions | Resources declare their schema (what fields they expose) and tool schemas (what operations they support) as Pydantic models. Reuses the existing Node pattern -- resources ARE data frames, tools ARE typed operations. JSON schema generation via `.model_json_schema()` feeds the AI's tool awareness. |
| `typing.Protocol` | stdlib 3.14 | Resource and Tool protocols | `Resource` protocol defines the interface (path, tools, children, repr). `Tool` protocol defines callable operations. Same pattern as `ViewFormatter` protocol in channels.py. Runtime-checkable for registration validation. |
| `contextvars.ContextVar` | stdlib 3.14 | Current resource scope (working directory) | A contextvar holds the current resourcespace path. Navigation commands (`cd`, breadcrumbs) update it. Tool resolution reads it. Same pattern as `_graph_ctx` in engine.py. Async-safe, zero overhead when not navigating. |

**Integration point:** The resource registry lives on CortexShell alongside `_graph_registry`. It seeds into the REPL namespace as a navigable object (replacing or wrapping the current flat namespace). `_build_context()` in ai.py reads the current scope to populate AI context with only the relevant tools and resources.

**Why flat dict, not tree structure:** A tree (nested dicts, or a TreeNode class with children) requires traversal logic, parent pointers, and careful mutation handling. A flat dict with path keys gives O(1) lookup, trivial subtree listing via prefix scan, and zero structural overhead. The "tree" is implicit in the path strings -- same design as Redis keys or S3 object stores.

### Tool Call Pruning (I/O Only, 500 Token Cap)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `str` methods | stdlib | Content pruning for AI context window | Tool outputs already flow through `_MAX_TOOL_OUTPUT = 4000` in ai.py. Pruning to 500 tokens (~2000 chars) for context injection is string slicing. The pruning logic belongs in `_build_context()`, not a library. |
| `re` | stdlib | Strip non-I/O tool calls from conversation history | Already used extensively in ai.py for `_EXEC_BLOCK_RE`, `_TOOL_TAG_RE`, etc. Pruning "intermediate" tool calls (reads, globs) from context while preserving I/O (writes, final results) is regex filtering on metadata type tags. |

**Integration point:** Pruning hooks into the existing eval loop in `AI.__call__()`. The context builder (`_build_context`) gets a budget parameter. Tool call metadata already has `type` tags (ai_exec, tool_translated, ai_exec_result) -- filtering on these determines what enters context vs. what gets pruned.

### Source Resourcespace (Agent Modifies Bae Source)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `ast` | stdlib 3.14 | Parse Python source for structural navigation | `ast.parse()` + `ast.walk()` for extracting class/function/import structure from bae source files. Enables "list classes in node.py" without regex. Already handles Python 3.14 syntax. |
| `pathlib.Path` | stdlib 3.14 | File I/O for source reading/writing | Already used throughout (ai.py, store.py). Source resourcespace wraps Path operations with resource protocol. |
| `inspect.getsource` | stdlib 3.14 | Get source of live objects in namespace | For resources that point to loaded modules -- get the actual current source without re-reading files. |
| `tokenize` | stdlib 3.14 | Preserve formatting in source edits | When the agent edits source, tokenize preserves comments and whitespace that ast discards. For read-only structural queries, ast suffices. For writes, the existing `_exec_edit_replace` line-range approach in ai.py is sufficient -- no AST-level rewriting needed. |

**Integration point:** Source resourcespace registers at `/source/`. Each Python file in the bae package becomes a child resource at `/source/bae/node.py`, `/source/bae/graph.py`, etc. Tools: `read(path, lines?)`, `edit(path, start, end, content)`, `search(pattern)`. These delegate to the existing tool implementations in ai.py (`_exec_read`, `_exec_edit_replace`, `_exec_grep`).

**Why NOT `libcst` or `rope`:** CST-preserving transformation libraries are for automated refactoring tools. The agent writes code directly -- it does not need a CST intermediate representation. `ast` for structural queries + line-range edits for modifications is the right weight.

### Memory Resourcespace (Explore/Tag Session Memories)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `SessionStore` (existing) | bae | FTS5 search, session listing, entry retrieval | Already has `search()`, `recent()`, `sessions()`, `session_entries()`. Memory resourcespace is a thin protocol wrapper over these methods. Zero new storage code needed. |
| `sqlite3` | stdlib 3.14 | Tag storage (new table for entry tags) | Tags are a new concept: `entry_tags(entry_id, tag)` table with FTS5 integration. SQLite ALTER TABLE or schema migration in SessionStore. One new table, one new trigger. |
| `json` | stdlib 3.14 | Metadata enrichment for tagged entries | Entry metadata already stores as JSON text. Tags can also live in metadata, but a separate table enables tag-based FTS queries without JSON parsing. |

**Integration point:** Memory resourcespace registers at `/memory/`. Children: `/memory/sessions`, `/memory/search`, `/memory/tags`. Tools: `search(query)`, `recent(n)`, `tag(entry_id, tag)`, `untag(entry_id, tag)`, `by_tag(tag)`. All delegate to SessionStore methods (existing or new).

**Schema addition:** One new table in SessionStore:

```sql
CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id),
    tag TEXT NOT NULL,
    PRIMARY KEY (entry_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags(tag);
```

### Task Resourcespace (CRUD/Search, Persistent)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `sqlite3` | stdlib 3.14 | Task persistence (new table in SessionStore DB) | Tasks need to survive across sessions. A `tasks` table in the existing SQLite DB with FTS5 integration. Same connection, same WAL journal, same file. |
| `Pydantic BaseModel` | 2.12.5 | Task schema definition | Task model with typed fields: title, status, priority, tags, description, created_at, updated_at. Validates on create/update. JSON schema for AI tool awareness. |
| `enum.Enum` | stdlib | Task status and priority enums | `TaskStatus(OPEN, IN_PROGRESS, DONE, CANCELLED)`, `TaskPriority(LOW, MEDIUM, HIGH, CRITICAL)`. |
| `uuid.uuid7()` | stdlib 3.14 | Task IDs | Sortable, timestamp-embedded. Already used for session_id in SessionStore. |

**Integration point:** Task resourcespace registers at `/tasks/`. Tools: `create(title, ...)`, `update(id, ...)`, `list(status?, priority?)`, `search(query)`, `delete(id)`. FTS5 indexes task title + description for natural language search.

**Schema addition:**

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'medium',
    description TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
    title, description, content=tasks, content_rowid=rowid
);
```

### Search Resourcespace (Cross-Resourcespace Search)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `sqlite3 FTS5` | stdlib 3.14 | Unified search across resourcespaces | Each resourcespace that supports search registers a search provider. The search resourcespace fans out queries to all providers, merges results with source attribution. FTS5 MATCH syntax is already used in SessionStore.search(). |

**Integration point:** Search resourcespace at `/search/`. It does not store data -- it dispatches. A `SearchProvider` protocol: `search(query, limit) -> list[SearchResult]`. Each resourcespace optionally implements it. `/search/` calls all providers, deduplicates, ranks by relevance (FTS5 rank score), and returns unified results with source paths.

**Why NOT Elasticsearch/Whoosh/Tantivy:** All are external search engines for large-scale full-text search. Bae's data fits in SQLite. FTS5 provides BM25 ranking, prefix queries, phrase matching, and boolean operators. For a single-user REPL with thousands of entries, FTS5 is the correct scale.

### Context-Scoped Tool Declaration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `Pydantic BaseModel` | 2.12.5 | Tool schema as Pydantic models | Each tool declares its parameters as a Pydantic model. `model_json_schema()` generates the schema the AI sees. Same pattern as Node field schemas. |
| `typing.Callable` | stdlib 3.14 | Tool implementation as async callables | Tools are `async def` functions with typed parameters. The resource declares which tools it supports. When the AI is in that resource's scope, only those tools appear in context. |
| `functools.wraps` | stdlib | Preserve tool metadata through wrappers | Tools may be wrapped for logging, permission checks, or scope validation. `wraps` preserves `__name__`, `__doc__`, and annotations. |

**Integration point:** The AI's system prompt dynamically includes tool schemas based on current resourcespace scope. `_build_context()` in ai.py queries the resource registry for the current path's tools, serializes their schemas, and injects them. This replaces the current static namespace dump with a context-aware tool menu.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Resource tree | Flat dict with path keys | `anytree` / `treelib` | External dependency for a shallow tree (3-4 levels deep). Path-prefix matching on a flat dict is simpler, faster, and zero-dependency. |
| Resource tree | Flat dict with path keys | Nested dict-of-dicts | Nested dicts require recursive traversal, parent tracking, and careful mutation. Flat dict is O(1) lookup. |
| Navigation | `contextvars.ContextVar` | Thread-local | Cortex is async. Thread-locals do not propagate across await boundaries. ContextVars do. Already proven in engine.py's `_graph_ctx`. |
| Source analysis | `ast` stdlib | `libcst` / `parso` | CST libraries preserve formatting for automated refactoring. The agent writes code directly via line-range edits. AST provides structural queries; line-range edits preserve formatting by operating on raw text. |
| Source analysis | `ast` stdlib | `rope` (refactoring library) | Rope is a full refactoring engine. Overkill for "list classes" and "show function signature" queries. |
| Search | SQLite FTS5 | `whoosh` | Pure-Python search engine, unmaintained since 2015. FTS5 is built into Python's sqlite3, actively maintained, and already used in SessionStore. |
| Search | SQLite FTS5 | `tantivy-py` (Rust bindings) | Compiled extension, designed for millions of documents. Bae has thousands. FTS5 handles this scale trivially. |
| Task storage | Same SQLite DB | Separate JSON files | JSON files require manual indexing, lack transactions, and cannot do FTS. SQLite already open, WAL-mode, with proven patterns in SessionStore. |
| Task storage | Same SQLite DB | `TinyDB` | External dependency. SQLite is stdlib, already in use, and supports FTS5. TinyDB would add a dependency for less capability. |
| Tool schemas | Pydantic models | JSON Schema literals | Hand-written JSON schemas are error-prone and drift from implementation. Pydantic generates correct schemas from type annotations, which is the entire philosophy of bae. |
| Tool schemas | Pydantic models | `dataclasses` | Dataclasses lack validation and JSON schema generation. Tools need both (validate agent input, generate schema for AI context). Pydantic is already a core dependency. |

---

## What NOT to Add

| Temptation | Why Resist |
|------------|-----------|
| `fastapi` / `starlette` Router | HTTP URL routing frameworks. Resourcespace paths are in-process dict lookups, not HTTP endpoints. Router middleware, dependency injection, request/response objects -- all irrelevant. |
| `anytree` / `treelib` | Tree data structure libraries. The resource tree is 3-4 levels deep. A flat dict with path-prefix matching is simpler and faster. |
| `libcst` / `rope` | CST-preserving code transformation. The agent writes code via line-range edits, not AST manipulation. `ast` for read-only structural queries is sufficient. |
| `whoosh` / `tantivy` / `elasticsearch` | External search engines. FTS5 is built into sqlite3, already in use, handles bae's scale (thousands of entries, not millions). |
| `TinyDB` / `peewee` / `SQLAlchemy` | ORMs and alternative databases. Raw sqlite3 with explicit SQL is bae's pattern (see SessionStore). ORMs add abstraction over a simple schema. |
| `pydantic-settings` | Settings management. Resourcespace config is in-process state, not environment variable parsing. |
| `click` / `argparse` (for resource commands) | CLI argument parsing for resource navigation commands. The agent invokes tools via typed Pydantic models, not CLI-style string parsing. |
| `MCP` (Model Context Protocol) | External tool protocol for multi-model orchestration. Bae's tools are in-process Python callables in a single-agent REPL. MCP's JSON-RPC transport layer adds latency and complexity for zero benefit in this architecture. |

---

## Existing Dependencies (Unchanged)

No version changes needed. Current installed versions are sufficient for all v7.0 features.

| Package | Installed | Required | v7.0 Usage |
|---------|-----------|----------|------------|
| `pydantic` | 2.12.5 | >=2.0 | Resource schemas, Tool parameter models, Task model. `model_json_schema()` for AI tool awareness. |
| `prompt-toolkit` | 3.0.52 | >=3.0.50 | REPL navigation commands, completions for resource paths, `print_formatted_text` for resource display. |
| `rich` | 14.3.2 | >=14.3 | Resource tree rendering (Rich Tree), task list rendering (Rich Table), breadcrumb display (Rich Text). |
| `pygments` | 2.19.2 | >=2.19 | Python syntax highlighting in source resourcespace views. |
| `typer` | (installed) | >=0.12 | CLI entry point (unchanged). |

---

## New Stdlib Usage Summary

Everything below is Python 3.14 stdlib. Zero `pip install` commands.

```
# Resourcespace core
dict[str, Resource]         -- flat path-keyed registry
typing.Protocol             -- Resource, Tool, SearchProvider protocols
contextvars.ContextVar      -- current scope (working directory)
dataclasses.dataclass       -- lightweight internal structs (SearchResult, Breadcrumb)

# Tool call pruning
str slicing + re            -- content truncation and I/O filtering in context builder

# Source resourcespace
ast.parse / ast.walk        -- Python source structural queries
pathlib.Path                -- file I/O (already used)
inspect.getsource           -- live object source retrieval

# Memory resourcespace
sqlite3                     -- entry_tags table (already open via SessionStore)

# Task resourcespace
sqlite3                     -- tasks + tasks_fts tables (same DB, same connection)
uuid.uuid7                  -- sortable task IDs (already used for sessions)
enum.Enum                   -- TaskStatus, TaskPriority

# Search resourcespace
sqlite3 FTS5 MATCH          -- cross-resourcespace full-text search (already used)

# Tool schemas
pydantic.BaseModel          -- tool parameter models (already a dependency)
```

---

## Key Integration Points with Existing Architecture

### Namespace (bae/repl/namespace.py)
- `seed()` gains a resource registry alongside the flat namespace.
- Resources appear as navigable objects in the namespace. `ns()` shows current scope's resources and tools.
- NsInspector delegates to resource protocol for inspection.

### AI Context (bae/repl/ai.py)
- `_build_context()` reads the current resourcespace scope instead of dumping the entire namespace.
- Tool schemas from the current scope's resources replace the static `_SKIP` set.
- Pruning logic trims tool call history to I/O-only within token budget.
- `MAX_CONTEXT_CHARS` budget is allocated across: scope tools (schema), recent tool results (I/O only), navigation breadcrumb.

### SessionStore (bae/repl/store.py)
- Schema gains `entry_tags` and `tasks` tables.
- `SCHEMA` string extended (no migration framework -- CREATE IF NOT EXISTS is idempotent).
- New methods: `create_task()`, `update_task()`, `search_tasks()`, `tag_entry()`, `entries_by_tag()`.
- Same connection, same WAL journal, same file. No second database.

### ChannelRouter (bae/repl/channels.py)
- Resource navigation events write to a `"nav"` channel (or reuse `"debug"` channel).
- Tool execution within resourcespaces writes to `"py"` channel with metadata tags (same as ai_exec).

### ViewFormatter (bae/repl/views.py)
- UserView gains resource-aware rendering: breadcrumb header, tool call panels scoped to resource.
- No new ViewFormatter subclass needed -- metadata-driven rendering on existing views.

### GraphRegistry (bae/repl/engine.py)
- No changes. Resourcespaces are orthogonal to graph execution.
- A graph CAN use resourcespace tools via Dep functions, but the engine does not know about resourcespaces.

---

## Rich Components for Resource Display

Rich (already installed at 14.3.2) provides rendering primitives that map directly to resourcespace display needs:

| Rich Component | Use In v7.0 | Already Used? |
|----------------|-------------|---------------|
| `rich.tree.Tree` | Render resource subtree hierarchy | No (new usage) |
| `rich.table.Table` | Task list, search results, tool parameter docs | Yes (views.py) |
| `rich.panel.Panel` | Resource detail view, tool output framing | Yes (views.py) |
| `rich.text.Text` | Breadcrumb trail, inline resource links | Yes (views.py) |
| `rich.syntax.Syntax` | Source resourcespace file content | Yes (views.py) |
| `rich.markdown.Markdown` | Resource descriptions, help text | Yes (channels.py) |

`rich.tree.Tree` is the one new Rich component. It renders nested tree structures with connecting lines -- ideal for `ns()` showing the resource hierarchy. Render via existing `_rich_to_ansi()` -> `print_formatted_text(ANSI(...))` pattern from views.py.

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Zero new dependencies | HIGH | Every feature maps to stdlib + existing deps. Verified against pyproject.toml and installed packages. Same conclusion as v6.0. |
| Pydantic for tool/resource schemas | HIGH | `model_json_schema()` is core Pydantic 2.x. Already used for Node field schemas in fill(). |
| SQLite FTS5 for cross-resourcespace search | HIGH | Already in production in SessionStore. Same MATCH syntax, same ranking. |
| ast for source structural queries | HIGH | stdlib since Python 2. Python 3.14 AST handles all current syntax. |
| contextvars for scope tracking | HIGH | Already proven in engine.py's `_graph_ctx`. Async-safe, zero overhead. |
| Rich Tree for resource display | MEDIUM | Rich Tree exists and is documented, but untested in bae's `_rich_to_ansi()` pipeline. Should work (same Console rendering path), but needs validation. |
| Schema migration for new tables | HIGH | CREATE IF NOT EXISTS is idempotent. Same pattern as SessionStore's current SCHEMA. No migration framework needed. |

---

## Sources

### Existing Codebase (PRIMARY -- all verified by reading source)
- `bae/repl/store.py` -- SessionStore schema, FTS5 integration, CRUD patterns
- `bae/repl/ai.py` -- AI context building, tool call execution, eval loop
- `bae/repl/engine.py` -- GraphRegistry, contextvars usage, lifecycle patterns
- `bae/repl/channels.py` -- ChannelRouter, ViewFormatter protocol, Channel dataclass
- `bae/repl/views.py` -- Rich rendering pipeline, `_rich_to_ansi()`, UserView
- `bae/repl/namespace.py` -- NsInspector, `seed()`, namespace structure
- `bae/repl/tasks.py` -- TaskManager, TrackedTask patterns

### Official Documentation (HIGH confidence)
- [Python 3.14 ast module](https://docs.python.org/3/library/ast.html) -- parse, walk, NodeVisitor
- [Python 3.14 contextvars](https://docs.python.org/3/library/contextvars.html) -- ContextVar async semantics
- [SQLite FTS5](https://www.sqlite.org/fts5.html) -- MATCH syntax, BM25 ranking, content tables
- [Pydantic model_json_schema](https://docs.pydantic.dev/latest/concepts/json_schema/) -- JSON Schema generation from models
- [Rich Tree](https://rich.readthedocs.io/en/stable/tree.html) -- Tree rendering API

---
*Stack research for: Hypermedia resourcespace, context-scoped tools, agent navigation*
*Researched: 2026-02-16*
