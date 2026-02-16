# Project Milestones: Bae

## v5.0 Stream Views (Shipped: 2026-02-14)

**Delivered:** Multi-view stream framework with tool call translation and execution display overhaul -- `<run>` convention for executable code, native tool call interception, three pluggable view formatters with runtime cycling.

**Phases completed:** 21-25 (5 phases, 9 plans)

**Key accomplishments:**
- `<run>` execution convention with 100% compliance across all Claude tiers -- clean separation of executable from illustrative code
- Tool call translation pipeline: 5 tool types (R, W, E, G, Grep) detected, executed natively, with concise display summaries
- ViewFormatter protocol enabling pluggable channel display via strategy pattern
- UserView with Rich Panel execution display -- buffered code+output grouping, syntax highlighting, deduplication
- Three-view system (UserView, DebugView, AISelfView) with Ctrl+V runtime cycling and toolbar indicator
- Response display stripping of executable markup -- no `<run>` block or tool tag duplication

**Stats:**
- 44 files modified
- 6,436 lines of Python (bae/repl/ + tests/repl/)
- 5 phases, 9 plans, ~50 commits
- 1 day (2026-02-14)

**Git range:** `feat(21-01)` -> `fix(25)`

**Tech debt accepted:**
- AIHR-01 deferred (no-tools constraint fewshot -- tool interception approach proved more effective)
- tests/traces/json_structured_fill_reference.py drift

---

## v3.0 Async Graphs (Shipped: 2026-02-13)

**Delivered:** Full async interface with parallel dep resolution — all three LM backends native async, asyncio.gather() for independent deps, sync/async callable mixing, nested model preservation in fill().

**Phases completed:** 11-13 (9 plans total)

**Key accomplishments:**
- All three LM backends (PydanticAI, ClaudeCLI, DSPy) converted to native async
- Graph run/arun split with asyncio.run() CLI boundary
- Parallel dep resolution via asyncio.gather() with topological ordering
- Sync/async Dep(callable) mixing with runtime inspect.iscoroutinefunction detection
- Nested model preservation in fill() — getattr extraction over model_dump() across all backends
- 346 tests (336 pass, 10 skip, 0 fail), 5/5 E2E

**Stats:**
- 49 files modified
- 10,412 lines of Python
- 3 phases, 9 plans, 37 commits
- 5 days (2026-02-04 → 2026-02-09)

**Git range:** `feat: convert LM Protocol and backends to async` → `feat: fix nested model preservation in all three fill() backends`

**What's next:** OTel observability, structured logging, PydanticAI backend evaluation

---

## v2.0 Context Frames (Shipped: 2026-02-08)

**Delivered:** Redesigned the node API around "nodes as context frames" — Dep/Recall field annotations, implicit LM, JSON structured fill with constrained decoding, and explicit Field(description=...) hints.

**Phases completed:** 5-10 (21 plans total)

**Key accomplishments:**
- Dep(callable) field annotation with topological DAG resolution, dep chaining, per-run caching
- Recall() trace search for graph state — backward type-matching with MRO support
- Graph.run() v2: resolve deps → resolve recalls → LM fill, with implicit graph-level LM
- Removed v1 markers (Context, Bind), incant dependency, and all legacy patterns
- JSON structured fill via Claude CLI constrained decoding (--json-schema), replacing XML prompts
- Docstrings made inert — class name is the instruction, Field(description=...) for explicit LLM hints

**Stats:**
- 92 files created/modified
- 9,297 lines of Python (2,718 source + 6,298 test)
- 6 phases, 21 plans, 106 commits
- 2 days (2026-02-07 → 2026-02-08)

**Git range:** `docs(05): research` → `docs: track v4.0 todos`

**What's next:** System prompt for LLM backends, OTel observability with Jaeger, structured logging, PydanticAI backend consistency

---

## v1.0 DSPy Compilation (Shipped: 2026-02-05)

**Delivered:** DSPy compiles agent graphs from type hints and class names — node_to_signature, auto-routing, BootstrapFewShot optimization, compiled prompt loading.

**Phases completed:** 1-4 (13 plans total)

**Key accomplishments:**
- node_to_signature() converts Node subclasses to dspy.Signature automatically
- Graph.run() auto-routes via return type introspection (union → decide, single → make)
- BootstrapFewShot optimization with trace-to-Example conversion
- OptimizedLM with compiled prompt registry and naive fallback

**Stats:**
- 4 phases, 13 plans
- 1 day (2026-02-04 → 2026-02-05)

**Git range:** `docs: initialize project` → `docs(phase-4): complete Production Runtime phase`

**What's next:** v2.0 Context Frames — Dep/Recall field annotations, implicit LM

---

## v4.0 Cortex (Shipped: 2026-02-14)

**Delivered:** NL-first augmented REPL where human and AI collaborate in a shared namespace — async shell with 4 modes, session store for cross-session memory, channel-based labeled I/O, AI agent with eval loop, and task lifecycle management.

**Phases completed:** 14-20 (7 phases, 24 plans)

**Key accomplishments:**
- Async REPL shell with 4 modes (NL/PY/GRAPH/BASH), syntax highlighting, multiline editing, tab completion
- RAG-friendly session store — SQLite + FTS5, all I/O labeled and indexed, cross-session persistence
- Channel-based labeled output — color-coded prefixes, visibility toggle, graph wrapper (no bae source mods)
- Reflective namespace — bae objects seeded, ns() introspection, REPL annotation resolution via sys.modules
- AI agent in namespace — Claude CLI backend, eval loop (extract-execute-feedback), multi-session routing
- Task lifecycle — TaskManager with process group kill, inline Ctrl-C menu, customizable toolbar widgets

**Stats:**
- 57 commits, 26 files changed, 4,951 lines (source + tests + prompt)
- 245 tests passing
- 2 days (2026-02-13 → 2026-02-14)

**Tech debt accepted:**
- AI hallucinates tool calls (prompt engineering iteration needed)
- Eval output redundant display (GWT stream UX design deferred)
- AI bash dispatch, streaming, GWT stream UX deferred to v5.0

**What's next:** v5.0 — GWT-inspired stream UX, OTel observability, advanced features

---


## v6.0 Graph Runtime (Shipped: 2026-02-16)

**Delivered:** Async graph execution engine inside cortex with concurrent lifecycle management, human-in-the-loop gates via asyncio.Future, full observability through the channel/view system, and agent core extraction. GRAPH mode command interface built then deliberately removed -- all capabilities accessible programmatically.

**Phases completed:** 26-30 (5 phases, 18 plans)

**Key accomplishments:**
- GraphRegistry engine with concurrent lifecycle tracking, per-node timing, and TaskManager integration
- asyncio.Future-based input gates with toolbar badge and cross-mode @g resolution from any REPL mode
- Full observability: OutputPolicy, dep timing hooks, RSS measurement, lifecycle events through [graph] channel
- graph() factory with flattened params API and _graph_ctx auto-registration inside cortex
- Agent core extraction: extract_executable and agent_loop decoupled from REPL to bae/agent.py
- Post-milestone cleanup: GRAPH mode removal (7 commands deleted, infrastructure preserved), 8-priority codebase refactor

**Stats:**
- 27 commits, 6,130 lines Python (bae/), 10,368 lines tests
- 647 tests passing
- 1 day (2026-02-15)

**Git range:** `feat(26-01)` -> `refactor(quick-2)`

**Tech debt accepted:**
- 7 requirements no longer satisfied after deliberate GRAPH mode removal (infrastructure survives programmatically)
- AgenticBackend removed post-verification (agentic fill will use model config on nodes)
- Phase 30 VERIFICATION.md stale
- tests/traces/json_structured_fill_reference.py drift (carried from v5.0)

---

