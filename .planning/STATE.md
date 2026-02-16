# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v7.0 Hypermedia Resourcespace -- Phase 33: Task Resourcespace

## Current Position

Phase: 33 of 36 (Task Resourcespace)
Plan: 1 of 2 in current phase
Status: In Progress
Last activity: 2026-02-16 -- Completed 33-01 (TaskStore data layer, custom tool cleanup, unit tests)

Progress: [█████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░] 50% of 33

## Performance Metrics

**Velocity:**
- Total plans completed: 112 (13 v1.0 + 21 v2.0 + 9 v3.0 + 24 v4.0 + 9 v5.0 + 23 v6.0 + 13 v7.0)
- v6.0 duration: 1 day (2026-02-15)
- v5.0 duration: 1 day (2026-02-14)

**Recent Trend:**
- Last 5 plans avg: ~3 min
- Trend: Stable

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

Recent:
- v7.0 33-01: FTS5 content_rowid uses implicit SQLite rowid for TEXT PK; _prev_custom set tracks custom tool names for cleanup
- v7.0 32.2-04: Validation wrappers raise ResourceError; tool detection uses regex on stripped code, not AST
- v7.0 32.2-03: Validator cache keyed by id(method); unannotated params default to str in pydantic model
- v7.0 32.2-02: Body-content write format shows content param between open/close tags; fallback for missing tool callables renders plain <Tag>
- v7.0 32.1.1-04: Role grouping only for convention packages (with view.py); tstring Template.__str__ returns repr so use manual render
- v7.0 32.1.1-03: Include _LINE_RANGE_RE in home __init__.py exports (ai.py imports it)
- v7.0 32.1.1-02: Meta _module_path stays as service module (needs AST defs); enter() references package for orientation
- v7.0 32.1.1-02: Subresource packages follow {name}/{__init__.py, view.py, service.py}; view delegates to stateless service functions
- v7.0 32.1.1-01: Within spaces/ package, import from view.py directly to avoid __init__.py circular dependency
- v7.0 32.1.1-01: Protocol definition site is bae.repl.spaces.view; external code imports from bae.repl.spaces
- v7.0 32.1-02: Tests import from bae.repl.spaces (canonical); production infrastructure keeps importing from bae.repl.resource (definition site)
- v7.0 32.1-01: MetaSubresource._module_path points to bae.repl.spaces.source.service (canonical location after move)
- v7.0 32.1-01: spaces/ package layout: spaces/{name}/{__init__.py, service.py, models.py, schemas.py, view.py}; old modules become thin re-export shims
- v7.0 32-05: Stack replacement uses identity comparison for common-prefix divergence; tools() returns bound methods for namespace injection
- v7.0 32-04: Subresource classes are module-level; ConfigSubresource returns JSON; tomlkit added for TOML writes
- v7.0 32-03: _replace_symbol auto-adjusts indentation via textwrap.dedent + col_offset re-indent
- v7.0 32-03: Hot-reload non-fatal for write(), fatal for edit() (triggers rollback to old_source)
- v7.0 32-01: Module-level helpers for path resolution; _StubSubresource for not-yet-implemented children
- v7.0 32-01: CHAR_CAP=2000 with ResourceError narrowing guidance (no silent pruning)
- v7.0 31-04: NavResult str subclass with raw __repr__ preserves ANSI in navigation output
- v7.0 32-07: home() returns NavResult wrapping _build_orientation(); _with_location injects orientation at root for AI context
- v7.0 31-03: home/back are lambdas wrapping registry methods, not ResourceHandles
- v7.0 31-03: Resource location injected via _with_location into every AI _send call
- v7.0 31-02: ResourceError promoted from dataclass to Exception subclass for raise/except
- v7.0 31-02: Pruning keeps structural lines (headings, tables), trims content to ~2000 chars
- v7.0 31-02: read('') at root lists resourcespaces instead of filesystem read
- v7.0 31-01: Dotted navigation pushes full intermediate chain onto stack for correct breadcrumb
- v7.0 31-01: ResourceHandle guards __getattr__ against underscore-prefixed names
- v7.0: Navigation is a discoverable affordance -- calling a resource as a function navigates into it
- v7.0: Resources show functions table with procedural docstrings on entry
- v7.0: `.nav()` lists targets as `@resource()` hyperlinks; mentions are navigable
- v7.0: Subresourcespaces are nested resources (e.g., source.meta())
- v7.0: Resources provide Python hints on entry for advanced `<run>` operations
- v7.0 32-02: fnmatch on dotted module paths for glob; grep caps at 50 matches with overflow indicator
- [Phase 32]: Package detection uses filepath.name == '__init__.py' to branch summary format; packages show subpackage/module counts
- [Phase 32.2]: Error detection uses dual approach: structured is_error flag + _is_error_output heuristic fallback
- [Phase 32.2]: Intermediate response suppression by removing mid-loop writes, single write after loop

### Pending Todos

- Session store: conversation indexing agent (deferred)
- Source write/edit: auto-commit to VCS on successful write (undo yanks commits); consider jj if git is clunky for this
- Source write: takes two args (code + test) — both AST-parsed, unit test run immediately, if passes → save + commit + hot reload; full suite runs async in bg, alarm on failure → auto-dispatch subagent to research/diagnose/fix
- Source edit: same but unit test optional, allowed to fail
- Source write/edit: coverage check on the unit test if not too heavy/slow
- Functions table: sort order should match system tools display order; tags should use system tool names (R/W/E/G/Grep)
- Resource navigation: track which resources agent session has entered, show condensed re-entry info ("left a → reentered b") instead of full entry display on revisit
- Tool discoverability: entry banner should clarify tools are top-level functions (not methods on resource handle); `source.read("bae")` feels natural but fails — consider making ResourceHandle forward tool calls
- ns() should show tool functions (read, glob, grep, etc.) alongside namespace objects (engine, toolbar)
- grep overhaul: (1) exact module targeting — `grep("pat", "bae.foo.service")` should search that one file, not `bae.foo.service.*` children; (2) raise match cap or paginate — 50 is too tight for exploratory queries like `def \w+`; (3) error guidance suggests broader path instead of narrower pattern — invert; (4) verbose `module:line: content` prefix eats budget — consider hierarchical grouping by module; (5) overall needs more display space
- write() discoverability: no hint that bare name creates subresource vs dotted path creates module; consider `write --help` or better entry docs
- Navigation error consistency: sometimes "Try: source()", sometimes method suggestions; `source.read()` gives dead-end "No resource" error
- Error type in tool summary: show specific exception class name (ResourceError) not generic "Error" — use __class__.__name__
- Diamond bullet brightness: cosmetic — consider brighter color for tool summaries
- Navigation output verbosity: reduce re-entry display when revisiting resources
- AI `<tool_call>` JSON syntax: AI sometimes emits `{"name": "Read", "arguments": {...}}` instead of `<run>` blocks — not handled
- Session tag/indicator: disappeared at some point during testing — investigate
- REPL tracebacks: consider Rich traceback formatting for nicer error display
- Source read: add line-range support — when symbol exceeds CHAR_CAP, allow `read("module", lines="276-335")` or similar
- Hot-reload limitation: editing `bae.repl.spaces.source.service` doesn't take effect in running session (service module provides the tools — known limitation, document it)

### Roadmap Evolution

- Phase 32.1 inserted after Phase 32: Resourcespace Package Structure (URGENT) — restructure into spaces/ packages before adding more resourcespaces in 33+
- Phase 32.1.1 inserted after Phase 32.1: Subresource Packages + Shim Removal (URGENT) — break subresources into own packages, remove all backward-compat shims, enforce structure in source resourcespace
- Phase 32.2 inserted after Phase 32: UserView Tool Call Stripping (URGENT) — strip tool calls from AI output + context history, show only tool I/O and agent's last message

### Blockers/Concerns

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | remove graph mode and all associated tests | 2026-02-16 | ea7cc27 | [1-remove-graph-mode-and-all-associated-tes](./quick/1-remove-graph-mode-and-all-associated-tes/) |
| 2 | execute refactor in .planning/audit | 2026-02-16 | eb2714a | [2-execute-refactor-in-planning-audit](./quick/2-execute-refactor-in-planning-audit/) |

### Research Notes (v7.0)

- Zero new dependencies required for entire milestone
- Resource tree is a flat dict with path keys, not a tree data structure
- Navigation state in ContextVar (async-safe, same as _graph_ctx)
- Critical pitfalls: navigation state desync, tool scoping leaks, pruning destroying info
- All 6 phases flagged SKIP for research -- established patterns throughout

## Session Continuity

Last session: 2026-02-16
Stopped at: Completed 33-01-PLAN.md (TaskStore data layer, custom tool cleanup, unit tests)
Branch: main
Resume file: .planning/phases/33-task-resourcespace/33-01-SUMMARY.md
