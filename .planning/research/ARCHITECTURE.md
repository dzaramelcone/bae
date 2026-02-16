# Architecture Patterns

**Domain:** Hypermedia resourcespace layer for async REPL AI agent
**Researched:** 2026-02-16
**Confidence:** HIGH (direct codebase analysis, all integration points verified against existing source)

## Recommended Architecture

The resourcespace system is a **navigation layer** that sits between the AI agent's tool calls and their execution. It introduces "current location" that scopes tool behavior -- the same `<R:path>` tag means "read a file" at homespace but "read a resource" when navigated into a resourcespace.

### Core Insight: Tool Interception, Not New Tools

The AI already has Read/Write/Edit/Glob/Grep via `run_tool_calls()` in `ai.py`. Resourcespaces do NOT add new tool verbs. They redefine what existing verbs operate on based on navigation context. This is the hypermedia pattern: the agent navigates a space of resources, and its standard tools become context-aware.

```
                     +-------------------+
                     |   AI (ai.py)      |
                     | emits tool tags   |
                     +--------+----------+
                              |
                     +--------v----------+
                     | ToolRouter        |
                     | (new component)   |
                     |                   |
                     | location == home? |
                     |   -> filesystem   |
                     | location == rs?   |
                     |   -> rs.dispatch  |
                     +--------+----------+
                              |
              +-------+-------+-------+--------+
              |       |               |        |
     +--------v--+  +-v--------+  +--v-----+ +v---------+
     | Filesystem |  | SourceRS |  | MemRS  | | TaskRS   |
     | (existing) |  | (new)    |  | (new)  | | (new)    |
     +------------+  +----------+  +--------+ +----------+
```

### Component Boundaries

| Component | Responsibility | Communicates With | Status |
|-----------|---------------|-------------------|--------|
| `bae/repl/resource.py` | Resourcespace protocol, ResourceRegistry, navigation state | ToolRouter, shell | **NEW** |
| `bae/repl/tools.py` | ToolRouter -- intercept tool calls, dispatch by location, output pruning | AI, Resourcespaces, filesystem fns | **NEW** |
| `bae/repl/resources/source.py` | Source RS -- bae source tree as navigable resource | ToolRouter, filesystem | **NEW** |
| `bae/repl/resources/memory.py` | Memory RS -- session memories as navigable resources | ToolRouter, SessionStore | **NEW** |
| `bae/repl/resources/tasks.py` | Task RS -- persistent TODO CRUD | ToolRouter, TaskStore | **NEW** |
| `bae/repl/resources/task_store.py` | TaskStore -- SQLite persistence for tasks | Task RS | **NEW** |
| `bae/repl/ai.py` | Replace direct `_exec_*` calls with ToolRouter dispatch; add `<nav:>` tag | ToolRouter | **MODIFIED** |
| `bae/repl/ai_prompt.md` | Add navigation commands + resourcespace awareness | AI | **MODIFIED** |
| `bae/repl/shell.py` | Create ResourceRegistry, pass ToolRouter to AI, register resourcespaces, add toolbar widget | resource registry | **MODIFIED (minimal)** |
| `bae/repl/toolbar.py` | Location widget showing current resourcespace | navigation state | **MODIFIED (minimal)** |

### Data Flow

**Tool call lifecycle (current -- ai.py lines 393-456):**
```
AI response text
  -> run_tool_calls() scans for tool tags via regex
  -> finds <R:path>, <W:path>content</W>, <G:pattern>, <Grep:pattern>
  -> calls _exec_read(path), _exec_write(path, content), _exec_glob(pattern), _exec_grep(pattern)
  -> direct filesystem operations (Path.read_text, Path.write_text, glob.glob)
  -> output string returned to AI as feedback
```

**Tool call lifecycle (with resourcespaces):**
```
AI response text
  -> run_tool_calls() scans for tool tags via regex (UNCHANGED)
  -> finds <R:id>, <W:id>content</W>, <G:pattern>, <Grep:pattern>
  -> calls ToolRouter.read(id), ToolRouter.write(id, content), etc. (NEW indirection)
  -> ToolRouter checks registry.current:
       None (homespace) -> _exec_read(path), _exec_write(path, content) (UNCHANGED)
       Resourcespace    -> rs.read(resource_id), rs.write(resource_id, content)
  -> output pruned to ~500 tokens if from resourcespace (NEW)
  -> output string returned to AI as feedback (UNCHANGED)
```

**Navigation lifecycle (new):**
```
AI response text
  -> run_tool_calls() scans for <nav:target> tag (NEW regex)
  -> ToolRouter.navigate(target)
  -> ResourceRegistry.navigate(target) updates location state
  -> returns confirmation string ("navigated to source") to AI as feedback
  -> AI's next tool calls are now scoped to that resourcespace
```

## New Component Designs

### 1. Resourcespace Protocol (`bae/repl/resource.py`)

Follows the same Protocol+Registry pattern as ChannelRouter/Channel in `channels.py`.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Resourcespace(Protocol):
    """A navigable domain that responds to standard tool verbs."""

    name: str  # "source", "memory", "tasks"

    def read(self, resource_id: str) -> str:
        """Read a resource by ID. Equivalent to <R:id> when navigated."""
        ...

    def write(self, resource_id: str, content: str) -> str:
        """Write content to a resource. Equivalent to <W:id>content</W>."""
        ...

    def edit(self, resource_id: str, start: int, end: int, content: str) -> str:
        """Replace lines in a resource. Equivalent to <E:id:start-end>."""
        ...

    def glob(self, pattern: str) -> str:
        """List resources matching pattern. Equivalent to <G:pattern>."""
        ...

    def grep(self, pattern: str) -> str:
        """Search resource content. Equivalent to <Grep:pattern>."""
        ...

    def context(self) -> str:
        """Summary for AI context injection (~200 chars max)."""
        ...
```

Not all verbs need implementation per resourcespace. `NotImplementedError` for unsupported ops -- ToolRouter catches it and returns a clear error to the AI.

### 2. ResourceRegistry + Navigation State

Navigation is a single mutable string: the current location. Locations use path-like convention.

```python
class ResourceRegistry:
    """Registry of resourcespaces with navigation state."""

    def __init__(self):
        self._spaces: dict[str, Resourcespace] = {}
        self.location: str = ""  # "" = homespace

    def register(self, rs: Resourcespace) -> None:
        self._spaces[rs.name] = rs

    @property
    def current(self) -> Resourcespace | None:
        if not self.location:
            return None
        root = self.location.split("/")[0]
        return self._spaces.get(root)

    @property
    def resource_path(self) -> str:
        """Sub-path within the current resourcespace."""
        if "/" in self.location:
            return self.location.split("/", 1)[1]
        return ""

    def navigate(self, target: str) -> str:
        if target in ("", "home", "~"):
            self.location = ""
            return "homespace"
        root = target.split("/")[0]
        if root not in self._spaces:
            return f"unknown: {root}. available: {', '.join(self._spaces)}"
        self.location = target
        return f"{target}"

    def spaces(self) -> list[str]:
        return list(self._spaces.keys())
```

**Location convention:**
```
""                         -> homespace (filesystem)
"source"                   -> source RS root
"source/bae/repl/ai.py"   -> specific file within source RS
"memory"                   -> memory RS root
"memory/recent"            -> recent entries
"tasks"                    -> task RS root
```

### 3. ToolRouter (`bae/repl/tools.py`)

Replaces direct filesystem calls in `run_tool_calls`. The existing `_exec_*` functions from `ai.py` move here as the homespace implementation.

```python
_OUTPUT_BUDGET = 2000  # ~500 tokens

class ToolRouter:
    """Dispatch tool calls by navigation context."""

    def __init__(self, registry: ResourceRegistry):
        self._registry = registry

    def read(self, arg: str) -> str:
        rs = self._registry.current
        if rs is None:
            return _exec_read(arg)
        try:
            return self._prune(rs.read(arg))
        except NotImplementedError:
            return f"{rs.name}: read not supported"

    def write(self, filepath: str, content: str) -> str:
        rs = self._registry.current
        if rs is None:
            return _exec_write(filepath, content)
        try:
            return self._prune(rs.write(filepath, content))
        except NotImplementedError:
            return f"{rs.name}: write not supported"

    def edit(self, filepath: str, start: int, end: int, content: str) -> str:
        rs = self._registry.current
        if rs is None:
            return _exec_edit_replace(filepath, start, end, content)
        try:
            return self._prune(rs.edit(filepath, start, end, content))
        except NotImplementedError:
            return f"{rs.name}: edit not supported"

    def glob(self, pattern: str) -> str:
        rs = self._registry.current
        if rs is None:
            return _exec_glob(pattern)
        try:
            return self._prune(rs.glob(pattern))
        except NotImplementedError:
            return f"{rs.name}: glob not supported"

    def grep(self, pattern: str) -> str:
        rs = self._registry.current
        if rs is None:
            return _exec_grep(pattern)
        try:
            return self._prune(rs.grep(pattern))
        except NotImplementedError:
            return f"{rs.name}: grep not supported"

    def navigate(self, target: str) -> str:
        return self._registry.navigate(target)

    def _prune(self, output: str) -> str:
        """Prune resourcespace output to budget."""
        if len(output) > _OUTPUT_BUDGET:
            return output[:_OUTPUT_BUDGET] + "\n... (pruned)"
        return output
```

### 4. AI Integration Point: How `run_tool_calls` Changes

The key change is in `ai.py`'s `run_tool_calls()`. Currently, the `_TOOL_EXEC` dict maps tool types to filesystem functions:

```python
# Current (ai.py line 356-361)
_TOOL_EXEC = {
    "R": _exec_read,
    "E": _exec_edit_read,
    "G": _exec_glob,
    "Grep": _exec_grep,
}
```

With ToolRouter, `run_tool_calls` receives a `ToolRouter` parameter. The dispatch changes from calling functions directly to calling router methods:

```python
def run_tool_calls(text: str, router: ToolRouter | None = None) -> list[tuple[str, str]]:
    """Detect and execute tool call tags, dispatching through router."""
    # ... existing regex scanning unchanged ...

    # Single-line tags dispatch through router
    for m in _TOOL_TAG_RE.finditer(prose):
        tool = _TOOL_NAMES.get(m.group(1).lower())
        if tool == "R":
            pending.append((m.start(), tag, lambda a=m.group(2): router.read(a)))
        elif tool == "G":
            pending.append((m.start(), tag, lambda a=m.group(2): router.glob(a)))
        # ... etc

    # Navigation tags (new)
    for m in _NAV_TAG_RE.finditer(prose):
        tag = m.group(0).strip()
        pending.append((m.start(), tag, lambda t=m.group(1): router.navigate(t)))
```

The `_exec_*` functions remain in the codebase but live in `tools.py` as the homespace implementation. They are called by ToolRouter when `registry.current is None`.

**Backward compatibility:** If `router` is None (e.g., tests that call `run_tool_calls` directly), fall back to direct filesystem calls as before.

### 5. Navigation via AI Tool Tags

Navigation is a new tool tag type, parsed alongside existing ones:

```
<nav:source>           navigate to source resourcespace
<nav:source/bae/repl>  navigate into a subpath
<nav:>                 return to homespace
<nav:?>                list available resourcespaces
```

New regex (follows existing tag patterns):

```python
_NAV_TAG_RE = re.compile(
    r"^[ \t]*<nav:([^>]*)>\s*$",
    re.MULTILINE | re.IGNORECASE,
)
```

### 6. Context Injection Changes

`_build_context` in `ai.py` (lines 464-526) summarizes namespace for the AI. With resourcespaces, it adds location state:

```python
# In _build_context(), after existing user_vars section:
registry = namespace.get("resources")
if registry and registry.location:
    rs = registry.current
    lines.append(f">>> location: {registry.location}")
    if rs:
        lines.append(f"  {rs.context()}")
elif registry:
    lines.append(f">>> location: homespace")
    lines.append(f"  resourcespaces: {', '.join(registry.spaces())}")
```

### 7. System Prompt Updates

`ai_prompt.md` needs navigation docs appended:

```markdown
## Navigation
Navigate resourcespaces to scope tools to a domain.
`<nav:source>` enter source code. `<nav:memory>` enter session memory.
`<nav:tasks>` enter tasks. `<nav:>` return to homespace. `<nav:?>` list spaces.
When navigated, R/W/E/G/Grep operate on resources in that space, not filesystem.
```

## Concrete Resourcespace Designs

### Source Resourcespace

Scoped to the bae package root. All standard tools supported. The most straightforward RS because it maps directly to filesystem operations with a constrained root.

```python
class SourceResourcespace:
    name = "source"

    def __init__(self, root: Path):
        self._root = root  # Path to bae package

    def read(self, resource_id: str) -> str:
        return (self._root / resource_id).read_text()

    def write(self, resource_id: str, content: str) -> str:
        path = self._root / resource_id
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"wrote {len(content)} chars to {resource_id}"

    def edit(self, resource_id: str, start: int, end: int, content: str) -> str:
        path = self._root / resource_id
        lines = path.read_text().splitlines(True)
        lines[start - 1:end] = content.splitlines(True)
        path.write_text("".join(lines))
        return f"replaced lines {start}-{end} in {resource_id}"

    def glob(self, pattern: str) -> str:
        hits = sorted(self._root.glob(pattern))
        return "\n".join(str(h.relative_to(self._root)) for h in hits[:50])

    def grep(self, pattern: str) -> str:
        # Search *.py files under root
        matches = []
        for f in sorted(self._root.rglob("*.py")):
            try:
                for i, ln in enumerate(f.read_text().splitlines(), 1):
                    if re.search(pattern, ln):
                        rel = f.relative_to(self._root)
                        matches.append(f"{rel}:{i}:{ln}")
            except (OSError, UnicodeDecodeError):
                pass
        return "\n".join(matches[:40]) or "(no matches)"

    def context(self) -> str:
        n = sum(1 for _ in self._root.rglob("*.py"))
        return f"source: bae ({n} .py files)"
```

### Memory Resourcespace

Wraps SessionStore. Read lists entries, glob lists sessions, grep uses FTS5. Write adds tags/annotations (future, could raise NotImplementedError initially).

```python
class MemoryResourcespace:
    name = "memory"

    def __init__(self, store: SessionStore):
        self._store = store

    def read(self, resource_id: str) -> str:
        if resource_id in ("recent", ""):
            entries = self._store.recent(20)
        else:
            entries = self._store.session_entries(resource_id)
        return "\n".join(self._store._format_entry(e) for e in entries)

    def write(self, resource_id: str, content: str) -> str:
        raise NotImplementedError  # Phase 1: read-only

    def edit(self, resource_id: str, start: int, end: int, content: str) -> str:
        raise NotImplementedError

    def glob(self, pattern: str) -> str:
        sessions = self._store.sessions()
        lines = []
        for s in sessions:
            lines.append(f"{s['id'][:8]}  started {s['started_at']:.0f}  {s['cwd']}")
        return "\n".join(lines) or "(no sessions)"

    def grep(self, pattern: str) -> str:
        results = self._store.search(pattern)
        return "\n".join(self._store._format_entry(e) for e in results) or "(no matches)"

    def context(self) -> str:
        sessions = self._store.sessions()
        return f"memory: {len(sessions)} sessions"
```

### Task Resourcespace

Needs a new `TaskStore` (SQLite table alongside SessionStore's tables). Persistent TODO items with status, tags, cross-session search.

```python
class TaskResourcespace:
    name = "tasks"

    def __init__(self, task_store: TaskStore):
        self._store = task_store

    def read(self, resource_id: str) -> str:
        if resource_id in ("", "open"):
            return self._store.list_open()
        if resource_id == "all":
            return self._store.list_all()
        return self._store.get(resource_id)

    def write(self, resource_id: str, content: str) -> str:
        if resource_id == "new":
            return self._store.create(content)
        return self._store.update(resource_id, content)

    def grep(self, pattern: str) -> str:
        return self._store.search(pattern)

    def glob(self, pattern: str) -> str:
        return self._store.list_by_tag(pattern)

    def context(self) -> str:
        return f"tasks: {self._store.open_count()} open"
```

**TaskStore schema:**
```sql
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    tags TEXT DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    session_id TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(content, content=tasks, content_rowid=rowid);
```

## Integration: What Changes in Each Existing File

### `bae/repl/ai.py` -- Medium Risk

**Changes:**
1. `run_tool_calls(text, router=None)` -- add optional `router` param. When provided, dispatch through router methods instead of `_TOOL_EXEC` dict. When None, fall back to existing behavior (backward compat).
2. Add `_NAV_TAG_RE` regex for `<nav:target>` parsing.
3. Move `_exec_*` functions to `tools.py`. Import them there as homespace implementation.
4. `_build_context` -- add location state (3-5 lines).
5. `AI.__call__` -- pass `self._router` (ToolRouter) to `run_tool_calls`.
6. `AI.__init__` -- accept `router: ToolRouter | None = None` param.

**What stays unchanged:** All regex patterns for existing tool tags. The eval loop. `_send`. Session management. Fill/choose_type. The tool tag format the AI emits.

### `bae/repl/shell.py` -- Low Risk

**Changes:**
1. `__init__`: Create `ResourceRegistry`, create `ToolRouter`, register resourcespaces, add to namespace.
2. `__init__`: Pass router to `AI.__init__`.
3. `__init__`: Add location toolbar widget.

**What stays unchanged:** Mode dispatch, prompt, key bindings, session management, all _run_* methods.

### `bae/repl/ai_prompt.md` -- Low Risk

Append navigation section (~5 lines).

### `bae/repl/toolbar.py` -- Low Risk

Add `make_location_widget(shell)` function (~10 lines).

### `bae/repl/namespace.py` -- Low Risk

Add `resources` to `_PRELOADED` or seed it from shell (probably shell, since it needs the registry instance).

## Patterns to Follow

### Pattern 1: Protocol + Registry (from Channel/ChannelRouter)
**What:** Channels.py already defines this pattern. Resourcespace/ResourceRegistry follows the same shape.
**When:** Any pluggable subsystem where multiple implementations register under names.
```python
# channels.py pattern:
router.register("py", "#87ff87")
router.write("py", content)

# resource.py pattern:
registry.register(SourceResourcespace(root))
registry.navigate("source")
```

### Pattern 2: Tag-Based Tool Dispatch (from existing tool call system)
**What:** The `<R:path>`, `<W:path>content</W>` regex-based system already works. `<nav:target>` is one more tag type.
**When:** Adding new capabilities the AI can invoke from prose.
**Example:** `_NAV_TAG_RE` follows `_TOOL_TAG_RE` pattern exactly.

### Pattern 3: Toolbar Widget for Transient State (from gates widget)
**What:** `make_gates_widget` shows gate count only when nonzero. Location widget shows resourcespace only when not at homespace.
**When:** State that's usually invisible but important when active.
```python
def make_location_widget(shell) -> ToolbarWidget:
    def widget():
        loc = shell.resources.location
        if not loc:
            return []
        return [("class:toolbar.location", f" @{loc} ")]
    return widget
```

### Pattern 4: Context Injection (from existing _build_context)
**What:** `_build_context` already summarizes namespace. Adding location state follows the same accumulator pattern.
**When:** AI needs awareness of state that affects its tool behavior.

### Pattern 5: Backward-Compatible Parameter Addition (from dep_cache in v6.0)
**What:** `Graph.arun()` got `dep_cache=None` in v6.0 without breaking callers. `run_tool_calls(text, router=None)` follows the same pattern.
**When:** Modifying a function signature that has existing callers.

## Anti-Patterns to Avoid

### Anti-Pattern 1: New Mode for Resourcespace Navigation
**What:** Adding a RESOURCE mode to the Mode enum for resourcespace management.
**Why bad:** Navigation is the AI's job, not Dzara's. Dzara speaks natural language; the AI decides when and where to navigate. A mode would force manual navigation management.
**Instead:** Navigation happens through AI tool tags (`<nav:target>`), transparent in debug view but invisible in user view.

### Anti-Pattern 2: New Tool Verbs Per Resourcespace
**What:** `<source-read:path>`, `<memory-search:query>`, `<task-create:title>`.
**Why bad:** Explodes AI tool vocabulary. Each new RS adds N new tags the AI must learn. Context-scoping is simpler -- same 5 tools, different targets.
**Instead:** Navigate first, then use standard R/W/E/G/Grep. The AI already knows these.

### Anti-Pattern 3: Eager Resource Loading
**What:** Loading all session memories or all source files into context when entering a resourcespace.
**Why bad:** Context window budget. Memory RS could have thousands of entries. Source RS has dozens of files. Eagerly loading defeats the pruning strategy.
**Instead:** Lazy -- resourcespace.context() returns a ~200 char summary. The AI uses glob/grep to discover, read to dive in. Same exploration pattern as filesystem.

### Anti-Pattern 4: Persistent Navigation State Across Sessions
**What:** Saving `registry.location` in SessionStore, restoring on next session start.
**Why bad:** AI has no memory of previous navigation. Starting a new session at "source/bae/repl/ai.py" with no context about why is confusing, not helpful.
**Instead:** Always start at homespace. AI navigates as needed per conversation.

### Anti-Pattern 5: Resourcespace as Graph Nodes
**What:** Modeling resourcespace operations as bae Graph nodes (Node subclasses for read, write, etc.).
**Why bad:** Resourcespaces are REPL-layer I/O concerns. Graphs are the computation framework. Coupling them adds complexity. RS operations are simple request/response, not multi-step agent workflows.
**Instead:** Resourcespaces are plain Protocol implementations with sync methods.

### Anti-Pattern 6: Deep Threading of Router Through AI Internals
**What:** Passing ToolRouter through `AI.__call__` -> `_send` -> everywhere.
**Why bad:** AI class already has many constructor params. The router is a tool-layer concern.
**Instead:** `run_tool_calls(text, router=self._router)` -- one param at the callsite where tools actually execute. Clean boundary.

## Build Order (Dependency-Driven)

```
Phase 1: ToolRouter + Protocol Foundation
    (pure additive, no existing file changes, zero behavior change)
    - bae/repl/resource.py: Resourcespace protocol, ResourceRegistry
    - bae/repl/tools.py: ToolRouter with homespace passthrough
    - Move _exec_* functions from ai.py to tools.py
    - Tests: ToolRouter at homespace behaves identically to direct calls

Phase 2: AI Integration + Navigation
    (modify ai.py -- the critical change)
    - ai.py: run_tool_calls accepts router param, dispatches through it
    - ai.py: add <nav:target> regex
    - ai.py: _build_context includes location state
    - ai_prompt.md: append navigation docs
    - shell.py: create registry + router, pass to AI, add toolbar widget
    - Tests: navigation + tool scoping end-to-end

Phase 3: Source Resourcespace
    (first concrete RS -- simplest, best for dogfooding)
    - bae/repl/resources/__init__.py
    - bae/repl/resources/source.py
    - shell.py: register source RS
    - Tests: navigate to source, read/write/glob/grep bae code

Phase 4: Memory Resourcespace
    (wraps existing SessionStore -- no new persistence)
    - bae/repl/resources/memory.py
    - shell.py: register memory RS
    - Tests: navigate to memory, search sessions, read entries

Phase 5: Task Resourcespace
    (needs new TaskStore schema + persistence)
    - bae/repl/resources/task_store.py: TaskStore with SQLite
    - bae/repl/resources/tasks.py: TaskResourcespace
    - shell.py: register task RS
    - Tests: CRUD lifecycle, cross-session persistence, FTS search

Phase 6: Cross-RS Search + Polish
    - Homespace grep that searches across all resourcespaces
    - Output pruning tuning
    - Toolbar location widget polish
```

**Phase ordering rationale:**
- Phase 1 is pure additive -- zero behavior change, safe foundation to test against
- Phase 2 is the riskiest change (modifying ai.py's tool dispatch), done early to surface integration issues before building any resourcespaces
- Phase 3 (Source) before Phase 4 (Memory) because Source is the simplest RS (just filesystem with a root) and the most useful for dogfooding the system during development
- Phase 5 (Tasks) last among RSes because it requires new persistence (TaskStore), more schema design
- Phase 6 (Search) depends on all individual resourcespaces existing

## Scalability Considerations

| Concern | At 1 RS | At 5 RS | At 20 RS |
|---------|---------|---------|----------|
| Navigation overhead | Negligible (dict lookup) | Negligible | Negligible |
| Context injection size | +50 chars | +200 chars | Risk: exceeds MAX_CONTEXT_CHARS -- need summary |
| Tool dispatch latency | 1 extra function call | Same | Same |
| AI prompt size | +100 tokens for nav docs | Same (docs are generic) | Same |
| Memory per RS | Depends on RS impl | Sum of RS state | Consider lazy init |
| Output pruning | 2000 char cap per call | Same | Same |

The architecture scales linearly with resourcespace count. The bottleneck is AI context window, not runtime.

## Sources

- Codebase analysis: `bae/repl/ai.py` lines 31-456 (tool call system), `bae/repl/channels.py` (Protocol+Registry pattern), `bae/repl/shell.py` (integration points), `bae/repl/store.py` (SessionStore API for Memory RS)
- v6.0 architecture patterns: dep_cache injection, ToolRouter follows same backward-compatible param addition
- Confidence: HIGH -- all recommendations derived from existing codebase patterns and the concrete v7 feature list

---
*Architecture research: 2026-02-16 -- Hypermedia resourcespace integration with cortex*
