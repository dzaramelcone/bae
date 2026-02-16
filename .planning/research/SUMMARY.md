# Project Research Summary

**Project:** Cortex v7.0 Hypermedia Resourcespace
**Domain:** Agent navigation with context-scoped tools over self-describing resource tree
**Researched:** 2026-02-16
**Confidence:** HIGH

## Executive Summary

The v7.0 hypermedia resourcespace is a navigation layer that transforms cortex's flat tool vocabulary into context-aware operations. The research reveals that this is fundamentally a **zero new dependency** milestone built entirely on Python 3.14 stdlib plus existing packages (Pydantic 2.12.5, Rich 14.3.2, SQLite FTS5). The core insight: resources are not new tools, they're contexts that redefine what existing tools (R/W/E/G/Grep) operate on. The AI navigates a tree of self-describing resources (source code, session memories, persistent tasks, cross-resourcespace search) using HATEOAS principles — each resource declares its own affordances, eliminating the need to enumerate all possibilities in the system prompt.

The recommended architecture follows cortex's established patterns: Protocol + Registry (like Channel/ChannelRouter), tool interception at dispatch layer (adding ToolRouter that wraps existing `_exec_*` functions), and navigation via new `<nav:target>` tags parsed alongside existing tool tags. The resource tree is a flat dict with path keys (no actual tree structure needed), navigation state lives in a ContextVar (async-safe, same as `_graph_ctx`), and each resourcespace implements a simple protocol (read/write/edit/glob/grep methods plus a context summary). The source resourcespace wraps filesystem tools with a project root, memory resourcespace wraps SessionStore with FTS5 search, task resourcespace adds a new SQLite table for persistent TODOs, and search federates across all three.

The critical risks center on **navigation state desync** (AI loses track of where it is), **tool scoping leaks** (operations escape resource boundaries), and **context pruning destroying critical information** (500 token cap removes data the AI needs). Prevention: inject current location into every AI invocation not just first, scope tools at dispatch layer before execution, and prune via summaries not truncation (keeping full outputs in SessionStore as externalized memory).

## Key Findings

### Recommended Stack

Zero new dependencies required. Everything maps to Python 3.14 stdlib + existing packages. The temptation to add tree libraries (`anytree`), routing frameworks (FastAPI Router), CST-preserving parsers (`libcst`), or external search engines (`whoosh`/`tantivy`) should be resisted — all are overkill for cortex's scale and architecture.

**Core technologies:**
- `dict[str, Resource]` with path keys — flat registry with O(1) lookup, implicit tree via path prefixes (no need for actual tree nodes)
- `Pydantic BaseModel` (2.12.5) — resource schemas and tool parameter models, JSON schema generation via `model_json_schema()` for AI tool awareness
- `typing.Protocol` (stdlib 3.14) — Resource and Tool protocols, same pattern as ViewFormatter in channels.py
- `contextvars.ContextVar` (stdlib 3.14) — current resource scope tracking, async-safe, proven in engine.py's `_graph_ctx`
- SQLite FTS5 (stdlib) — cross-resourcespace search, memory tagging, task search (already in production via SessionStore)
- `ast` (stdlib 3.14) — Python source structural queries for source resourcespace (list classes, show signatures)
- Rich Tree (14.3.2) — resource hierarchy rendering (only new Rich component, rest already used)

**Critical insight from STACK.md:** The resource tree is NOT a tree data structure. It's a flat dict where keys are paths (`/source/bae/repl/ai.py`, `/memory/recent`, `/tasks/active/42`). Subtree queries are prefix scans. This is the same pattern as Redis keys or ChannelRouter's `_channels` dict — simpler and faster than nested objects.

### Expected Features

**Must have (table stakes):**
- Resource tree with HATEOAS navigation — the core premise, without it we're back to flat namespace guessing
- Context-scoped tool execution — same `<R:>` tag means different operations in different resourcespaces
- Tool call output pruning (500 token cap) — project spec mandate, prevents context bloat
- Homespace (root resource) — AI's starting point, dynamic dashboard showing available resourcespaces
- Source resourcespace — project-rooted file operations with short relative paths
- Memory resourcespace — session history as navigable resources, FTS5 search, tagging
- Task resourcespace — persistent TODO CRUD across sessions (Dzara's core use case)
- Search resourcespace — federated search across source/memory/tasks with navigation hints

**Should have (differentiators):**
- HATEOAS affordance discovery — resources tell the AI what operations are available, reducing tool selection errors
- Dynamic context window — resource-aware prompt shows only current scope's state/tools, dramatically more token-efficient than flat namespace dump
- Resource-scoped tool summaries in views — `[source] read ai.py (527 lines)` vs `[memory] search "graph" (7 matches)`

**Defer (explicitly avoided):**
- MCP protocol compliance — client-server overhead for in-process resources
- Vector/semantic search — FTS5 keyword search sufficient for cortex's memory volume
- Resource permissions/ACLs — single-user REPL has no security boundary
- Persistent navigation across sessions — homespace re-orientation is fast enough
- Custom resourcespace plugins — Python IS the extension system

**Feature dependency insight from FEATURES.md:** Resource Protocol is the foundation (everything else composes on it). Tool scoping and output pruning modify the existing tool pipeline. Source resourcespace is simplest (proves the pattern). Tasks are highest priority (Dzara's vision: START_HERE with outstanding tasks). Memory builds on task's store patterns. Search federates across all.

### Architecture Approach

The resourcespace system is a navigation layer between AI tool calls and execution. It introduces "current location" that scopes tool behavior — ToolRouter intercepts tool tags, checks ResourceRegistry for current location, dispatches to resourcespace-specific handlers or falls through to homespace (filesystem). Navigation is mutable state (location string) on ResourceRegistry. AI navigates via new `<nav:target>` tag parsed alongside existing R/W/E/G/Grep tags.

**Major components:**
1. **ResourceRegistry** (`bae/repl/resource.py`) — flat dict of resourcespaces keyed by name, mutable location string (path in tree), navigation logic
2. **ToolRouter** (`bae/repl/tools.py`) — intercepts tool calls from `run_tool_calls()`, dispatches by location (None → homespace filesystem, else → resourcespace methods), applies 500 token output pruning
3. **Resourcespace Protocol** (`bae/repl/resource.py`) — read/write/edit/glob/grep methods + context() summary, implemented per resourcespace (Source/Memory/Task)
4. **Source Resourcespace** (`bae/repl/resources/source.py`) — wraps existing `_exec_*` functions with project root path resolution
5. **Memory Resourcespace** (`bae/repl/resources/memory.py`) — wraps SessionStore, FTS5 search via grep, session browsing, read-only initially
6. **Task Resourcespace** (`bae/repl/resources/tasks.py`) — new TaskStore with SQLite table, CRUD via read/write, FTS5 task search
7. **AI integration** (`bae/repl/ai.py`) — `run_tool_calls()` gains router param, `_build_context()` includes location state, `<nav:>` regex added

**Critical architecture insight from ARCHITECTURE.md:** This is tool interception, not new tools. The AI already has R/W/E/G/Grep. Resourcespaces redefine what these operate on based on navigation. Same 5-tool vocabulary, different targets. This prevents tool proliferation (which degrades agent performance per Manus research). Also: navigation state desync is the foundational risk — must inject current location into EVERY AI invocation, not just first.

### Critical Pitfalls

Research identified 14 pitfalls across critical/moderate/minor severity. Top 5 for roadmap planning:

1. **Navigation State Desync** — AI loses track of where it is when context drifts or gets pruned. Prevention: inject current location into every `_send()` not just first `_build_context()`, tool outputs must echo resource context (`[/source/bae] read ai.py`), prefer absolute paths over relative.

2. **Tool Scoping Leak** — operations escape resource boundary via absolute paths, `../` traversal, or unvalidated formats. Prevention: scope at dispatch layer in ToolRouter BEFORE calling tool functions, validate all path formats (absolute/relative/home-relative), reject out-of-scope paths with explicit errors.

3. **Context Pruning Destroys Critical Information** — 500 token cap removes data the AI needs (function at line 300 of 500-line file, grep match 95 of 100). Prevention: prune to SUMMARIES not truncated raw output, keep full outputs in SessionStore (externalized memory), never prune error outputs (Manus: "leaving wrong turns visible improves behavior").

4. **Context Poisoning from Stale Resource State** — AI reads resource, Dzara modifies it externally, AI's context contains old state that contradicts reality. Prevention: resources include version/timestamp, operations fail if version changed since read, regenerate affordances on each AI invocation not cached.

5. **Tool Proliferation Degrades Performance** — multiple resourcespaces with resource-specific tools (15-30 total) dilute AI's tool selection accuracy. Prevention: polymorphic tools (same read/write/grep verbs, different behavior per resource), scope what's VISIBLE in system prompt by current resource, keep tool count at 5-7 not 30.

**Pitfall insight from PITFALLS.md:** Phase 1 (resourcespace core + tool scoping + pruning) must address pitfalls #1, #2, #3, #5 or all subsequent resourcespace features are built on broken foundation. Pitfall #4 must be considered in EVERY resourcespace implementation (each needs its own staleness mechanism: mtime for source, version for tasks, session ID for memory).

## Implications for Roadmap

Based on research, suggested phase structure aligns with FEATURES.md dependency graph and PITFALLS.md phase warnings:

### Phase 1: Resource Protocol + Tool Scoping + Navigation + Output Pruning
**Rationale:** Foundation for all other features. Must solve navigation desync (#1), tool scoping leak (#2), pruning destroys info (#3), tool proliferation (#5) before building any concrete resourcespaces. Pure additive initially (new modules, zero behavior change), then critical ai.py modification (highest risk change done early to surface integration issues).

**Delivers:**
- Resourcespace Protocol with read/write/edit/glob/grep + context() methods
- ResourceRegistry with location state and navigation logic
- ToolRouter intercepting tool calls, dispatching by location, applying output pruning
- `<nav:target>` tag parsing in `run_tool_calls()`
- Location injection in every `_build_context()` / `_send()` call
- Homespace navigation (return to `/` aka filesystem)

**Addresses:** Table stakes items 1-3 from FEATURES.md (resource tree, context-scoped tools, output pruning)

**Avoids:** All critical pitfalls (#1-5) via architectural decisions before any resourcespace exists

**Research flag:** **SKIP** — well-understood patterns from existing codebase (Protocol+Registry from channels.py, tool tag parsing from ai.py, ContextVar from engine.py). No novel integration, just composition.

### Phase 2: Source Resourcespace
**Rationale:** Simplest concrete resourcespace (wraps existing filesystem tools with project root). Best for dogfooding the system during development. AI already uses file tools, making them context-scoped is lowest-risk proof of pattern. Every subsequent resourcespace follows same shape.

**Delivers:**
- Source resourcespace registered at `/source/`
- All 5 tools (R/W/E/G/Grep) scoped to project root
- File tree rendering via glob (budget-aware)
- Path resolution prepending project root
- AST-based structural queries (list classes, show function signatures)

**Uses:** `ast` for source analysis (list classes without regex), `pathlib` for file I/O (already used), Rich Syntax for file display (already used)

**Implements:** First concrete Resourcespace protocol implementation, proves end-to-end navigation → scoped tools → output pruning flow

**Addresses:** Table stakes item 5 from FEATURES.md (source resourcespace)

**Avoids:** Pitfall #2 (scoping leak) via path validation, Pitfall #4 (stale state) via mtime checks

**Research flag:** **SKIP** — wraps existing `_exec_*` functions, standard file operations, well-documented ast module for structural queries.

### Phase 3: Task Resourcespace
**Rationale:** Dzara's highest-priority use case (dzarasplans.md: "START_HERE containing outstanding tasks"). Tasks are the primary work unit. Drives homespace dashboard evolution. Requires new persistence (TaskStore schema) so tackled early while architecture is fresh.

**Delivers:**
- TaskStore with SQLite schema (new `tasks` + `tasks_fts` tables)
- Task resourcespace registered at `/tasks/`
- CRUD via read (list tasks) / write (create/update task) / grep (FTS5 search)
- Task schema: title, status (open/in_progress/done/blocked), priority, tags, timestamps
- Cross-session persistence
- Outstanding tasks query for homespace dashboard

**Uses:** SQLite FTS5 (already in SessionStore), Pydantic Task model (schema + validation), `uuid.uuid7()` for task IDs (already used for sessions), Rich Table for task list rendering (already used)

**Implements:** Architecture component #6 from ARCHITECTURE.md (Task resourcespace)

**Addresses:** Table stakes item 7 from FEATURES.md (task resourcespace), differentiator (homespace dynamic dashboard)

**Avoids:** Pitfall #10 (concurrent access corruption) via optimistic versioning (version number on tasks), Pitfall #4 (stale state) via version checks before updates

**Research flag:** **SKIP** — SessionStore patterns already proven, FTS5 already in production, task CRUD is standard persistence. Schema design is straightforward (title/status/priority/tags).

### Phase 4: Memory Resourcespace
**Rationale:** Builds on task's SessionStore patterns (both are persistence-backed resources). Memory resourcespace makes existing session history navigable — browse by session, search across sessions, tag important entries. Lower priority than tasks but completes the "core resourcespaces" trio before adding search federation.

**Delivers:**
- Memory resourcespace registered at `/memory/`
- Session browsing (children: sessions by date/ID)
- FTS5 search via grep tool (delegates to `store.search()`)
- Entry tagging via write tool (future — can be read-only initially)
- Recent entries view
- Session-scoped entry reading

**Uses:** SessionStore (existing), FTS5 (existing), JSON metadata for tags (existing pattern)

**Implements:** Architecture component #5 from ARCHITECTURE.md (Memory resourcespace)

**Addresses:** Table stakes item 6 from FEATURES.md (memory resourcespace)

**Avoids:** Pitfall #13 (raw store exposure) via semantic API (search/sessions/tag) not raw store methods, Pitfall #6 (stale summaries) via always-fresh affordances

**Research flag:** **SKIP** — wraps existing SessionStore, FTS5 search already working, tagging is simple metadata JSON writes.

### Phase 5: Search Resourcespace + Homespace Refinement
**Rationale:** Search federates across all resourcespaces (source/task/memory), so must come after those exist. Homespace dashboard queries tasks for outstanding count and memory for recent activity, so refine it once data sources are in place.

**Delivers:**
- Search resourcespace registered at `/search/`
- Federated grep dispatching to all resourcespaces
- Result merging with source attribution (`[source] bae/repl/ai.py:527`, `[task] fix login bug`, `[memory] session abc123`)
- Navigation hints in search results (navigable paths: `cd /source/bae/repl/ai.py`)
- Result capping per-resourcespace (5 results each to stay within token budget)
- Homespace dynamic dashboard (outstanding tasks count, recent activity, available resourcespaces)

**Uses:** FTS5 for search backends, Rich Table for result rendering (already used)

**Implements:** Architecture component #8 from ARCHITECTURE.md (Search resourcespace), completes Homespace as dynamic dashboard

**Addresses:** Table stakes item 8 from FEATURES.md (search resourcespace), table stakes item 4 (homespace as entry point)

**Avoids:** Pitfall #7 (unnavigable results) via navigation paths in every search result, Pitfall #6 (stale homespace) via always-fresh dashboard queries

**Research flag:** **SKIP** — search dispatch is straightforward fan-out, FTS5 backends already exist, result merging is simple list aggregation.

### Phase 6: System Prompt Update + Polish
**Rationale:** System prompt (`ai_prompt.md`) needs navigation instructions once the full resourcespace system exists. Toolbar location widget, view formatting polish, affordance format consistency checks.

**Delivers:**
- `ai_prompt.md` extended with navigation mechanics (5-10 lines, keep minimal per anti-pitfall #11)
- Toolbar location widget showing current resourcespace (only when not at homespace)
- Resource-scoped tool summaries in UserView (`[source] read ai.py (527 lines)`)
- Affordance format consistency across all resourcespaces
- Rich Tree rendering for resource hierarchy (new Rich component usage)

**Uses:** Rich Tree (14.3.2) for hierarchy display (only new Rich usage, rest already proven)

**Implements:** Differentiator features from FEATURES.md (HATEOAS affordance discovery, dynamic context window, resource-scoped summaries)

**Addresses:** Anti-pitfall #11 (system prompt bloat) by keeping prompt minimal and using inline affordances, anti-pitfall #12 (affordance inconsistency) by enforcing format protocol

**Research flag:** **SKIP** — UI polish, Rich Tree is documented, system prompt update is straightforward text append.

### Phase Ordering Rationale

**Dependency-driven:**
1. Protocol + ToolRouter is the skeleton (everything composes on it)
2. Source proves the pattern works end-to-end with lowest risk
3. Tasks are highest priority use case, need new persistence so tackled early
4. Memory builds on task's persistence patterns, less critical than tasks
5. Search requires all resourcespaces to exist for federation
6. Polish refines UX once all features are functional

**Risk mitigation:**
- Phase 1 addresses all critical pitfalls before any concrete resourcespace
- Phase 2 (highest risk change: ai.py modification) done early to surface integration issues
- Each phase is self-contained and testable (no "build 3 phases to get anything working")

**Incremental value:**
- Phase 1: navigation works, homespace accessible
- Phase 2: AI can navigate source, edit bae code in context
- Phase 3: START_HERE shows outstanding tasks (Dzara's core vision)
- Phase 4: session history explorable, searchable, taggable
- Phase 5: unified search across all domains
- Phase 6: polished UX, consistent affordances

### Research Flags

**Phases with standard patterns (skip research-phase):**
- **Phase 1:** Protocol+Registry from channels.py, ContextVar from engine.py, tool tag parsing from ai.py — all proven patterns, composition not invention
- **Phase 2:** File operations, ast module, path resolution — well-documented stdlib, wraps existing functions
- **Phase 3:** SQLite schema, FTS5 integration, task CRUD — SessionStore already proves this pattern
- **Phase 4:** Wraps SessionStore, FTS5 search exists, tagging is metadata writes — no novel integration
- **Phase 5:** Search fan-out, result merging, FTS5 backends exist — straightforward aggregation
- **Phase 6:** UI polish, system prompt update, Rich Tree is documented

**No phases require `/gsd:research-phase`** — all features map to established patterns in codebase or stdlib. Research was comprehensive upfront.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new dependencies verified against pyproject.toml, all features map to stdlib + existing deps (Pydantic 2.12.5, Rich 14.3.2, SQLite FTS5). Same conclusion as v6.0 (also zero new deps). |
| Features | HIGH | HATEOAS patterns well-documented, context engineering lessons from Manus/JetBrains/LangChain, MCP resources spec provides reference architecture (though we don't implement the protocol). Feature dependencies verified via codebase analysis. |
| Architecture | HIGH | All recommendations derived from existing codebase patterns (Protocol+Registry, tool interception, ContextVar, SessionStore). Integration points verified against ai.py, channels.py, engine.py, store.py source. |
| Pitfalls | HIGH | Grounded in direct codebase analysis (ai.py tool dispatch, store.py persistence, shell.py namespace sharing) plus authoritative research (Manus context engineering, JetBrains context management, LangChain docs). |

**Overall confidence:** HIGH

### Gaps to Address

**Minor uncertainties to validate during implementation:**

- **Rich Tree rendering pipeline** (MEDIUM confidence) — Rich Tree exists and is documented, but untested in bae's `_rich_to_ansi()` → `print_formatted_text(ANSI(...))` pipeline from views.py. Should work (same Console rendering path), but needs validation in Phase 6 polish.

- **500 token output cap tuning** — Research recommends summary-based pruning over truncation, but optimal summary length per resourcespace type needs empirical testing. Start with ~200 char summaries in Phase 1, adjust based on AI behavior.

- **Navigation iteration budget** (anti-pitfall #14) — whether navigation turns should count against `_max_eval_iters` or be tracked separately. Decision deferred to Phase 1 implementation based on actual navigation overhead observed.

- **Task schema evolution** — Phase 3 starts with simple schema (title/status/priority/tags). May need `description` field, `blocked_by` references, `session_id` linkage as usage evolves. SQLite schema is ALTER-friendly via CREATE IF NOT EXISTS, so low risk.

**How to handle:** Validate during implementation, not research. All are tuning concerns, not architectural risks.

## Sources

### Primary (HIGH confidence)

**Codebase analysis (all verified by reading source):**
- `bae/repl/ai.py` — AI class, `_build_context()`, `run_tool_calls()`, tool dispatch, eval loop, session management
- `bae/repl/store.py` — SessionStore schema, FTS5 integration, CRUD patterns
- `bae/repl/engine.py` — GraphRegistry, contextvars usage (`_graph_ctx`), lifecycle patterns
- `bae/repl/channels.py` — ChannelRouter, ViewFormatter Protocol, Channel dataclass (Protocol+Registry pattern)
- `bae/repl/views.py` — Rich rendering pipeline, `_rich_to_ansi()`, UserView
- `bae/repl/namespace.py` — NsInspector, `seed()`, namespace structure
- `bae/repl/shell.py` — Integration points, namespace sharing, mode dispatch
- `.planning/dzarasplans.md` — START_HERE vision, hypermedia objects, breadcrumb navigation

**Official documentation:**
- [Python 3.14 ast module](https://docs.python.org/3/library/ast.html) — parse, walk, NodeVisitor for source structural queries
- [Python 3.14 contextvars](https://docs.python.org/3/library/contextvars.html) — ContextVar async semantics
- [SQLite FTS5](https://www.sqlite.org/fts5.html) — MATCH syntax, BM25 ranking, content tables
- [Pydantic model_json_schema](https://docs.pydantic.dev/latest/concepts/json_schema/) — JSON Schema generation from models
- [Rich Tree](https://rich.readthedocs.io/en/stable/tree.html) — Tree rendering API
- [MCP Resources Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/resources) — URI schemes, resource templates, capability declarations (reference, not implementation)

### Secondary (MEDIUM-HIGH confidence)

**HATEOAS and hypermedia for AI agents:**
- [HATEOAS: The API Design Style That Was Waiting for AI](https://nordicapis.com/hateoas-the-api-design-style-that-was-waiting-for-ai/) — Hypermedia constrains tool selection per step, affordance discovery at runtime
- [AI-Driven HATEOAS](https://www.apiscene.io/dx/ai-driven-hateoas-hypermedia-restful-api-design/) — APIs as intelligent state machines guiding agents
- [REST Reborn: From Integration Layer to Decision Interface](https://seddryck.wordpress.com/2025/07/07/rest-reborn-from-integration-layer-to-decision-interface/) — Agents need introspectable, navigable, semantically rich APIs

**Context engineering and tool pruning:**
- [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) — State machine tool masking, filesystem as externalized context, "leaving wrong turns visible improves behavior"
- [Context Engineering Token Economics](https://www.getmaxim.ai/articles/context-engineering-for-ai-agents-production-optimization-strategies/) — Token budget allocation strategies
- [Context Window Management Strategies](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/) — Summarization vs truncation vs externalization
- [JetBrains Efficient Context Management Research](https://blog.jetbrains.com/research/2025/12/efficient-context-management/) — Agent context bloat does not improve performance proportionally, "lost in the middle" effect
- [Context Engineering for Coding Agents](https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html) — Scoped context prevents confusion

**Agent memory and task management:**
- [Cross-Session Agent Memory](https://mgx.dev/insights/cross-session-agent-memory-foundations-implementations-challenges-and-future-directions/d03dd30038514b75ad4cbbda2239c468) — Separation of transient from persistent stores
- [AI Agent Memory Architecture](https://redis.io/blog/ai-agent-memory-stateful-systems/) — Working memory vs long-term memory
- [Mem0: Production-Ready Agent Memory](https://arxiv.org/pdf/2504.19413) — Dynamic extraction, consolidation, retrieval

**Agent tool scoping:**
- [Claude Code Custom Subagents](https://code.claude.com/docs/en/sub-agents) — `--allowedTools` for tool restriction per subagent
- [Claude Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) — Progressive disclosure, filesystem as skill discovery
- [MCP Features Guide](https://workos.com/blog/mcp-features-guide) — Tools vs resources distinction: "know" vs "do"

---
*Research completed: 2026-02-16*
*Ready for roadmap: yes*
