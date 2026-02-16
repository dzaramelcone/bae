# Feature Landscape: Cortex v7.0 Hypermedia Resourcespace

**Domain:** Context-scoped agent navigation with self-describing resource tree, tool pruning, and resource-based task/memory management
**Researched:** 2026-02-16
**Overall confidence:** HIGH for resource tree and context-scoped tools (well-understood HATEOAS patterns applied to novel context); HIGH for tool call pruning (proven truncation/capping strategies); MEDIUM for cross-resourcespace search (FTS5 exists but federation logic is novel); MEDIUM for memory/task resourcespaces (novel composition over existing SessionStore)

---

## Existing Foundation (Already Built)

Every v7.0 feature layers over existing v4.0-v6.0 primitives. The hypermedia resourcespace is a navigation/scoping layer -- it does NOT replace the agent, tools, or store.

| Component | File | What It Does | v7.0 Hook Point |
|-----------|------|-------------|-----------------|
| `AI.__call__` | `repl/ai.py` | NL conversation with eval loop and tool call translation | Resource context injected into prompt; tool availability scoped by current resource |
| `_build_context()` | `repl/ai.py` | Flat namespace summary as REPL state | Replaced by resource-aware context: current resource + affordances + breadcrumb path |
| `run_tool_calls()` | `repl/ai.py` | Detect and execute R/W/E/G/Grep tool tags | Tool execution scoped to current resource context (paths, search scope) |
| `_MAX_TOOL_OUTPUT` | `repl/ai.py` | 4000 char cap on tool output | Reduced to 500 tokens per resourcespace (project spec) |
| `NsInspector` | `repl/namespace.py` | `ns()` for listing and `ns(obj)` for inspection | Resourcespace becomes the primary navigation; ns() still works for raw namespace |
| `SessionStore` | `repl/store.py` | SQLite+FTS5 persistence for all I/O | Memory resourcespace queries store; task resourcespace persists tasks here |
| `ChannelRouter` | `repl/channels.py` | Named output channels with write dispatch | Resource navigation events flow through channels |
| `ai_prompt.md` | `repl/ai_prompt.md` | System prompt for AI agent | Extended with resourcespace navigation instructions and affordance discovery |
| `GraphRegistry` | `repl/engine.py` | Concurrent graph lifecycle tracking | Task resourcespace wraps graph runs as managed tasks |
| `extract_executable` | `agent.py` | Extracts `<run>` blocks from LM responses | Unchanged -- code execution still works, just scoped differently |

---

## Table Stakes

Features the AI and user expect from a resourcespace. Missing any of these makes the navigation feel broken or the scoping feel arbitrary.

### 1. Resource Tree with HATEOAS Navigation

| Aspect | Detail |
|--------|--------|
| **Why expected** | The core v7.0 premise. Without a navigable tree that declares its own affordances, the AI is back to flat namespace guessing. HATEOAS means "the resource tells you what you can do next" -- this IS the feature. |
| **Complexity** | Med |
| **Depends on** | None (new module, foundation for everything else) |
| **What it is** | A tree of Resource objects. Each resource has: a name, a description (for the AI), a list of supported tool names, child resources, and a `read()` method that returns its representation. The AI sees the current resource's representation (including links to children) and knows what tools work here. Navigation: `cd <child>`, `cd ..`, `cd /` (homespace). The root is homespace. |
| **Ecosystem pattern** | MCP resources use URI schemes (`file://`, custom) with `resources/list` and `resources/read`. Our pattern is simpler: resources are Python objects in a tree, not a protocol. The AI navigates by calling `cd("source")` or using a shorthand tag, not by sending JSON-RPC. HATEOAS: each resource's read() output includes links (child resource names with descriptions). |
| **Key design** | Resources are a Protocol: `name`, `description`, `tools: list[str]`, `children: dict[str, Resource]`, `read() -> str`, `parent: Resource | None`. Homespace is the root. Navigation is a stack (current path). The `_build_context()` replacement emits: current resource repr + available tools + breadcrumb path. |

### 2. Context-Scoped Tool Execution

| Aspect | Detail |
|--------|--------|
| **Why expected** | The whole point of resourcespaces. `<R:file>` in the source resourcespace reads source files. `<R:file>` in the memory resourcespace reads session entries. Same tool tag, different context. Without scoping, the resource tree is just decoration. |
| **Complexity** | Med-High |
| **Depends on** | Resource tree (tool declarations per resource) |
| **What it is** | Each resource declares which tools it supports and provides context for tool execution. The source resourcespace's `R` reads files relative to the project root. The memory resourcespace's `R` reads session entries by ID or search term. The task resourcespace's `R` reads task details. Tool dispatch checks the current resource's tool list before executing. Unknown tools get a clear error: "Tool X not available in [resource name]. Available: [list]." |
| **Ecosystem pattern** | Manus uses a state machine with token logit masking to control tool availability per state. MCP servers declare tool capabilities. Claude Code subagents use `--allowedTools` to restrict which tools a subagent can call. Our approach: each resource declares its tool list, and the tool dispatch layer filters before execution. Simpler than logit masking (we control the tool execution layer, not the LM decoding). |
| **Key design** | The existing `run_tool_calls()` gains a `resource` parameter. Before executing a tool tag, it checks `resource.tools`. If the tool is not in the list, it returns an error string instead of executing. Each resource can also provide a `resolve_path(arg)` method that transforms tool arguments (e.g., making paths relative to the resource's root). This is the scoping mechanism. |

### 3. Tool Call Output Pruning (500 Token Cap)

| Aspect | Detail |
|--------|--------|
| **Why expected** | The project spec mandates 500 tokens per resourcespace output. The current `_MAX_TOOL_OUTPUT = 4000` chars is far too generous -- a single file read can consume the entire context budget. Agents that accumulate 20+ tool calls bloat to 40k+ tokens. Capping output is table stakes for production agents. |
| **Complexity** | Low |
| **Depends on** | Tool execution layer |
| **What it is** | Replace the 4000 char cap with a 500 token cap (approximately 2000 chars for English text, but token-accurate counting uses a simple heuristic: chars/4). Tool output exceeding the cap is truncated with a `... (truncated, {total} tokens)` suffix. For structured output (grep matches, glob results), truncation preserves the count: `"12 matches shown of 47 total"`. |
| **Ecosystem pattern** | Manus writes tool outputs to filesystem and keeps only references in context. Claude Code truncates long outputs and offers to write to file. The "write" strategy (externalize, keep reference) is the production pattern. Our approach: hard cap with smart truncation. The resource's `read()` already provides a summary; detailed exploration happens via scoped tools. |
| **Key design** | `_MAX_TOOL_OUTPUT` becomes resource-configurable. Default 500 tokens (~2000 chars). Resources that need more (e.g., source code reads) can override up to a global maximum. The truncation is at the tool execution layer, not the LM layer -- the AI sees the cap in the tool output, not a silent cutoff. |

### 4. Homespace (Root Resource)

| Aspect | Detail |
|--------|--------|
| **Why expected** | The AI needs a starting point. Without a defined home, the AI starts in limbo -- no tools, no context, no affordances. Homespace is the HATEOAS entry point. It answers "what can I do?" for a fresh session. |
| **Complexity** | Low |
| **Depends on** | Resource tree |
| **What it is** | The root resource. Its `read()` returns: outstanding tasks (if any), available resourcespaces (source, memory, tasks, search) with descriptions, and a brief orientation. Think of it as Dzara's `START_HERE` vision from dzarasplans.md. The AI reads homespace, sees what's available, and navigates to the appropriate resourcespace based on the user's request. |
| **Ecosystem pattern** | MCP's `resources/list` returns the top-level resource catalog. REST APIs have a root endpoint that links to all sub-resources. HATEOAS requires an entry point that bootstraps discovery. |
| **Key design** | Homespace is NOT a static string. It queries live state: pending tasks count from task resourcespace, recent memory tags from memory resourcespace, current project info. It is a dynamic dashboard resource. Tools available at homespace: just navigation (`cd`) and search. No R/W/E -- you must navigate into a resourcespace first. |

### 5. Source Resourcespace

| Aspect | Detail |
|--------|--------|
| **Why expected** | The AI already reads/writes/edits files. The source resourcespace scopes these operations to the project directory and provides project-aware context (file tree, recently modified files, relevant code). Without it, file tools remain flat and global. |
| **Complexity** | Low-Med |
| **Depends on** | Resource tree, context-scoped tools |
| **What it is** | A resource rooted at the project directory. `read()` shows the file tree (truncated to fit budget). Children are directories and files. Tools: R (read file), W (write file), E (edit file), G (glob), Grep (search). All paths resolved relative to project root. The AI navigates `cd source` then operates on files with short relative paths instead of absolute paths. |
| **Ecosystem pattern** | Claude Code's filesystem tools already work this way -- paths relative to project root. MCP's `file://` scheme. VS Code's workspace-relative paths. |
| **Key design** | Source resourcespace wraps the existing tool functions (`_exec_read`, `_exec_write`, etc.) with path resolution. `resolve_path("main.py")` -> `/abs/path/to/project/main.py`. The tree representation uses glob to show structure, not a full recursive listing. |

### 6. Memory Resourcespace

| Aspect | Detail |
|--------|--------|
| **Why expected** | SessionStore has FTS5 search and cross-session history. But the AI currently has no structured way to explore memories. The memory resourcespace makes session history navigable: browse by session, search across sessions, tag important entries. |
| **Complexity** | Med |
| **Depends on** | Resource tree, SessionStore |
| **What it is** | A resource backed by SessionStore. `read()` shows recent sessions with summaries. Children: individual sessions (by ID or date). Tools: R (read session entries), Grep (FTS5 search across sessions), W (tag/annotate entries). Navigation: `cd memory/2026-02-16` to browse a specific session's entries. |
| **Ecosystem pattern** | Mem0 provides memory CRUD with automatic extraction. AWS AgentCore separates working memory (session) from long-term memory (cross-session). A-Mem organizes memories as a Zettelkasten. Our approach: leverage existing FTS5 store, add tagging for retrieval. No vector store needed -- FTS5 is sufficient for keyword-based memory search. |
| **Key design** | Memory resourcespace does NOT duplicate the store. It provides a navigable view over it. The `read()` of a session shows its entries with timestamps and channels. Tagging is a new lightweight feature: `W` in memory context writes a tag to an entry's metadata JSON. Tags enable filtered retrieval: "find all entries tagged 'decision'." |

### 7. Task Resourcespace

| Aspect | Detail |
|--------|--------|
| **Why expected** | Dzara's vision (dzarasplans.md): "START_HERE containing a list of outstanding tasks." Tasks are the primary work unit. Without a task resourcespace, the AI cannot track, prioritize, or manage work items. |
| **Complexity** | Med |
| **Depends on** | Resource tree, SessionStore (persistence) |
| **What it is** | CRUD for tasks with cross-session persistence. `read()` shows outstanding tasks sorted by priority. Children: individual tasks by ID. Tools: R (read task details), W (create/update task), Grep (search tasks). Tasks are stored in SessionStore as entries with `channel="task"` and structured metadata (title, status, priority, tags). |
| **Ecosystem pattern** | GSD's add-todo/check-todos workflow. Jira/Linear for issue tracking. The key insight: tasks should be first-class objects the AI can reason about, not just text in a session log. |
| **Key design** | Tasks are JSON objects stored in SessionStore entries. Schema: `{title, status, priority, tags, created, updated, description}`. Status: `open`, `in_progress`, `done`, `blocked`. The task resourcespace provides the CRUD interface; persistence uses the existing store. No new database table -- tasks are entries with a specific channel and metadata structure. |

### 8. Search Resourcespace

| Aspect | Detail |
|--------|--------|
| **Why expected** | With multiple resourcespaces, the AI needs cross-cutting search. "Find all references to GraphRegistry" should search source code AND session memories AND task descriptions. Without unified search, the AI must manually navigate each resourcespace and search separately. |
| **Complexity** | Med |
| **Depends on** | Resource tree, all other resourcespaces |
| **What it is** | A resource that federates search across all resourcespaces. `read()` shows recent search results or search instructions. Tools: Grep (cross-resourcespace search). When the AI runs a search, results include the source resourcespace (file paths), links to matching resources so the AI can navigate to them. Results are grouped by resourcespace with navigation hints. |
| **Ecosystem pattern** | VS Code's global search across files and settings. Spotlight/Alfred for cross-domain search. MCP doesn't have a built-in federation pattern -- each server is independent. |
| **Key design** | Search dispatches to each resourcespace's search capability and merges results. Source uses grep. Memory uses FTS5. Tasks use metadata search. Results are capped per-resourcespace (e.g., 5 results each) to stay within token budget. Each result includes a navigation path so the AI can `cd` to the relevant resource. |

---

## Differentiators

Features that set cortex v7.0 apart. Not expected in a REPL agent, but transform the experience.

### 1. HATEOAS Affordance Discovery (Self-Describing Resources)

| Aspect | Detail |
|--------|--------|
| **Value proposition** | Most agent frameworks give the AI a flat list of all tools and hope it picks the right ones. HATEOAS inverts this: the resource tells the AI what it can do. The AI discovers capabilities by navigating, not by reading a 50-tool system prompt. This reduces tool selection errors, shrinks context, and makes the agent composable (new resourcespaces add new capabilities without modifying the system prompt). |
| **Complexity** | Low (it IS the resource tree design -- not a separate feature) |
| **Depends on** | Resource tree |
| **What it is** | Each resource's `read()` output includes: what this resource is, what tools work here (with brief descriptions), and what child resources exist (with descriptions). The AI's system prompt says "navigate resources to discover capabilities" instead of listing every tool. New resourcespaces are discovered by the AI at runtime when they appear as children of homespace. |
| **Ecosystem pattern** | MCP resources have `description` and `mimeType` fields. HATEOAS REST APIs embed `_links` with `rel` and `href`. GRAIL (Mike Amundsen) demonstrates agents discovering affordances without preexisting knowledge. Our approach: resources ARE the affordance declaration. No separate discovery protocol needed. |

### 2. Dynamic Context Window (Resource-Aware Prompt)

| Aspect | Detail |
|--------|--------|
| **Value proposition** | The current `_build_context()` dumps the entire namespace as flat text, capped at 2000 chars. Resource-aware context is surgical: it shows only the current resource's state, the breadcrumb path, and available affordances. This is dramatically more token-efficient and more useful -- the AI sees relevant context, not everything. |
| **Complexity** | Low-Med |
| **Depends on** | Resource tree, `_build_context()` replacement |
| **What it is** | The context injected before each AI prompt contains: (1) breadcrumb path (`home > source > bae/repl`), (2) current resource's `read()` output, (3) available tools with one-line descriptions, (4) sibling/parent resources for navigation. This replaces the flat namespace dump. The namespace still exists for PY mode -- resourcespace is the AI's view, not the user's constraint. |
| **Ecosystem pattern** | Manus treats the filesystem as externalized context. Claude Code skills use progressive disclosure. The pattern: show the AI what it needs for the current task, not everything that exists. |

### 3. Resource-Scoped Tool Summaries in Views

| Aspect | Detail |
|--------|--------|
| **Value proposition** | When the AI executes tools, the UserView shows what happened. With resourcespaces, summaries include the resource context: `[source] read bae/repl/ai.py (42 lines)` vs `[memory] search "graph" (7 matches across 3 sessions)`. This makes tool output meaningful in context. |
| **Complexity** | Low |
| **Depends on** | Context-scoped tools, view system |
| **What it is** | The `_tool_summary()` function gains awareness of the current resource. Summaries are prefixed with the resource name. The view system already handles metadata-driven rendering -- adding a `resource` field to tool call metadata is trivial. |

---

## Anti-Features

Features to explicitly NOT build for v7.0.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **MCP protocol compliance** | MCP is a client-server protocol with JSON-RPC transport. Our resources are in-process Python objects navigated by the AI agent. Adding MCP protocol compliance adds transport overhead, serialization requirements, and server lifecycle management for zero benefit in a single-process REPL. | Resources are Python Protocol objects. If MCP interop is needed later, write an MCP server that wraps our resources -- the interface is similar enough. |
| **Vector/semantic search for memories** | Requires an embedding model, a vector store (FAISS/ChromaDB), and embedding pipeline. FTS5 keyword search is already built and sufficient for the memory sizes cortex produces. YAGNI until memory volume exceeds FTS5's effectiveness. | Use FTS5 search in the memory resourcespace. Add semantic search as a future resourcespace if needed. |
| **Resource permissions/ACLs** | MCP specifies access controls for sensitive resources. In a single-user REPL where the user and AI share a namespace, access controls add complexity with no security benefit. The user already has full access to everything. | All resources are readable/writable. The tool declarations on each resource serve as capability scoping, not permission enforcement. |
| **Resource subscriptions/change notifications** | MCP supports subscribing to resource changes. Our resources are read on demand, not streamed. The AI reads a resource, acts on it, and moves on. Push notifications would require the AI to handle interrupts mid-conversation, which conflicts with the eval loop model. | Resources are read when navigated to. The `read()` always returns current state. No stale cache problem because there is no cache. |
| **Persistent navigation state across sessions** | Saving "the AI was in source/bae/repl when the session ended" and restoring it on resume. Session resumption already loads conversation history, which includes navigation commands. The AI can re-navigate from homespace in one step. | Homespace shows outstanding tasks and recent context. The AI re-orients quickly. |
| **Custom resourcespace plugin system** | A registration API for third-party resourcespaces. Python IS the extension system (PROJECT.md). New resourcespaces are Python classes added to the tree. No plugin registry, no discovery protocol, no dynamic loading. | Add a new Resource subclass. Register it as a child of homespace in the shell setup. |
| **Resource versioning/history** | Tracking changes to resources over time (git-like). Source files have git. Session entries have timestamps. Tasks have `updated` fields. Building a separate versioning layer is redundant. | Use git for source, timestamps for store entries. |
| **Automatic resource suggestion** | AI automatically navigates to the "right" resource based on user intent. This adds a heuristic layer that will be wrong often enough to be annoying. Let the AI discover affordances through HATEOAS -- that IS the design pattern. | Homespace shows what's available. The AI reads it and decides. If it picks wrong, HATEOAS means the wrong resource will tell it what IS available there. |

---

## Feature Dependencies

```
Resource Protocol + Tree                           [new module: bae/repl/resources.py]
    |
    +---> Homespace (root resource)                [dynamic dashboard, queries children]
    |
    +---> Navigation (cd, path stack)              [shell integration, AI prompt context]
    |
    +---> Context-Scoped Tool Execution            [run_tool_calls gains resource param]
    |         |
    |         +---> Tool filtering                 [check resource.tools before dispatch]
    |         |
    |         +---> Path resolution                [resource.resolve_path(arg)]
    |         |
    |         +---> Output cap (500 tokens)        [_MAX_TOOL_OUTPUT -> resource-configurable]
    |
    +---> Resource-Aware Prompt                    [replaces _build_context()]
              |
              +---> Breadcrumb path
              +---> Current resource read()
              +---> Available tools + descriptions
              +---> Navigation hints (children, parent)

Source Resourcespace                                [depends on Resource Protocol]
    |
    +---> Project-rooted file operations           [wraps existing _exec_* functions]
    +---> File tree representation                 [glob-based, truncated]
    +---> Relative path resolution                 [resolve_path prepends project root]

Memory Resourcespace                                [depends on Resource Protocol + SessionStore]
    |
    +---> Session browsing                         [children are sessions by date/ID]
    +---> FTS5 search via Grep tool                [delegates to store.search()]
    +---> Entry tagging via W tool                 [writes tag to entry metadata JSON]

Task Resourcespace                                  [depends on Resource Protocol + SessionStore]
    |
    +---> Task CRUD                                [entries with channel="task"]
    +---> Task schema in metadata                  [title, status, priority, tags]
    +---> Outstanding tasks query                  [used by homespace dashboard]

Search Resourcespace                                [depends on all other resourcespaces]
    |
    +---> Federated search dispatch                [queries each resourcespace]
    +---> Result merging + navigation hints        [grouped by resource, capped per-group]
    +---> Cross-resourcespace Grep                 [single tool, multiple backends]

System Prompt Update                                [depends on Resource Protocol]
    |
    +---> ai_prompt.md rewrite                     [navigation instructions, affordance discovery]
    +---> Tool documentation per resource          [embedded in resource read(), not system prompt]
```

**Critical ordering insight:** The Resource Protocol is the foundation -- everything composes on it. Tool scoping and output pruning are the next layer (they modify the existing tool pipeline). Source resourcespace is the simplest concrete resourcespace to build (wraps existing functions). Memory and task resourcespaces require more design (new data patterns over SessionStore). Search is last because it federates across all others. Homespace evolves as children are added -- it queries whatever resourcespaces exist.

**Build order by dependency:**
1. Resource Protocol + navigation + tool scoping + output pruning
2. Source resourcespace (proves the pattern works end-to-end)
3. Task resourcespace (Dzara's highest-priority use case: START_HERE with tasks)
4. Memory resourcespace (builds on task's store patterns)
5. Search resourcespace (federates across 2-4)
6. Homespace refinement (dynamic dashboard queries all children)

---

## MVP Recommendation

### Phase 1: Resource Protocol + Tool Scoping + Output Pruning

**Prioritize:**
1. `Resource` Protocol: name, description, tools, children, read(), resolve_path()
2. Navigation: cd/path stack, current resource tracking on AI or shell
3. Tool dispatch filtering: check `resource.tools` before executing
4. Path resolution: `resource.resolve_path(arg)` transforms tool arguments
5. Output cap: `_MAX_TOOL_OUTPUT` reduced to ~2000 chars (500 tokens), resource-configurable
6. Resource-aware `_build_context()` replacement: breadcrumb + read() + tools + nav hints

**Why first:** This is the skeleton. Without the protocol, there are no resources. Without tool scoping, resources are decorative. Without output pruning, context bloats. This phase produces a functional (if empty) resource tree with scoped tools.

### Phase 2: Source Resourcespace

**Prioritize:**
1. Source resource rooted at project directory
2. `read()` showing file tree (glob-based, budget-aware)
3. Path resolution prepending project root
4. All 5 tools (R, W, E, G, Grep) scoped to project

**Why second:** The AI already uses file tools. Making them context-scoped is the lowest-risk proof that the resource pattern works. Every subsequent resourcespace follows the same pattern.

### Phase 3: Task Resourcespace

**Prioritize:**
1. Task schema (title, status, priority, tags, timestamps)
2. Tasks as SessionStore entries (channel="task", metadata=task JSON)
3. CRUD via R/W tools in task context
4. Outstanding tasks query for homespace dashboard
5. Grep for task search

**Why third:** This is Dzara's core use case -- the AI should see outstanding work when it starts. Tasks drive the homespace dashboard.

### Phase 4: Memory Resourcespace + Search + Homespace

**Prioritize:**
1. Memory resource backed by SessionStore
2. Session browsing (children by date)
3. FTS5 search via Grep
4. Entry tagging
5. Search resourcespace federating across source/task/memory
6. Homespace dynamic dashboard (pending tasks, recent activity)

**Defer:**
- Memory tagging UX refinement (start with simple JSON metadata writes)
- Search ranking/relevance scoring (start with flat result lists)
- Rich resource tree visualization (start with plain text `read()` output)

---

## Sources

**HATEOAS and Hypermedia for AI Agents (MEDIUM confidence -- multiple sources agree):**
- [HATEOAS: The API Design Style That Was Waiting for AI](https://nordicapis.com/hateoas-the-api-design-style-that-was-waiting-for-ai/) -- Hypermedia constrains tool selection per step; affordance discovery at runtime
- [AI-Driven HATEOAS](https://www.apiscene.io/dx/ai-driven-hateoas-hypermedia-restful-api-design/) -- APIs as intelligent state machines guiding agents through workflows
- [REST Reborn: From Integration Layer to Decision Interface](https://seddryck.wordpress.com/2025/07/07/rest-reborn-from-integration-layer-to-decision-interface/) -- Agents need introspectable, navigable, semantically rich APIs

**Context Engineering and Tool Pruning (HIGH confidence -- verified across multiple authoritative sources):**
- [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) -- State machine tool masking, filesystem as externalized context, attention manipulation via todo.md recitation
- [Context Engineering Token Economics](https://www.getmaxim.ai/articles/context-engineering-for-ai-agents-production-optimization-strategies/) -- Token budget allocation: 15-20% tools, 30-40% knowledge, 10-15% buffer
- [Context Window Management Strategies](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/) -- Summarization, truncation, write-to-external patterns

**MCP Resources Specification (HIGH confidence -- official documentation):**
- [MCP Resources Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/resources) -- URI schemes, resource templates, capability declarations, annotations with priority
- [MCP Features Guide](https://workos.com/blog/mcp-features-guide) -- Tools vs resources distinction: "know" vs "do"

**Agent Memory and Task Management (MEDIUM confidence -- multiple sources):**
- [Cross-Session Agent Memory](https://mgx.dev/insights/cross-session-agent-memory-foundations-implementations-challenges-and-future-directions/d03dd30038514b75ad4cbbda2239c468) -- Separation of transient from persistent stores, dynamic organization
- [AI Agent Memory Architecture](https://redis.io/blog/ai-agent-memory-stateful-systems/) -- Working memory vs long-term memory, selective retrieval
- [Mem0: Production-Ready Agent Memory](https://arxiv.org/pdf/2504.19413) -- Dynamic extraction, consolidation, retrieval from conversations

**Agent Tool Scoping Patterns (MEDIUM confidence -- verified with official docs):**
- [Claude Code Custom Subagents](https://code.claude.com/docs/en/sub-agents) -- `--allowedTools` for tool restriction per subagent
- [Claude Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) -- Progressive disclosure, filesystem as skill discovery
- [Context Engineering for Coding Agents](https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html) -- Scoped context prevents confusion

**Codebase References (HIGH confidence):**
- `bae/repl/ai.py` -- AI class, _build_context(), run_tool_calls(), tool dispatch
- `bae/repl/namespace.py` -- NsInspector, seed(), namespace structure
- `bae/repl/store.py` -- SessionStore, FTS5 schema, entries table
- `bae/repl/ai_prompt.md` -- Current system prompt
- `bae/agent.py` -- extract_executable()
- `.planning/dzarasplans.md` -- START_HERE vision, hypermedia objects, breadcrumb navigation

---

*Research conducted: 2026-02-16*
*Focus: Feature landscape for cortex v7.0 Hypermedia Resourcespace milestone*
*Replaces: v6.0 Graph Runtime feature research*
