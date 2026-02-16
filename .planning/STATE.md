# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v7.0 Hypermedia Resourcespace -- Phase 32.2: UserView Tool Call Stripping

## Current Position

Phase: 32.2 of 36 (UserView Tool Call Stripping)
Plan: 2 of 3 in current phase
Status: In Progress
Last activity: 2026-02-16 -- Completed 32.2-02 (typed XML signatures in functions table)

Progress: [█████████████████████████████████░░░░░░░░░░░░░░░░░] 67% of 32.2

## Performance Metrics

**Velocity:**
- Total plans completed: 111 (13 v1.0 + 21 v2.0 + 9 v3.0 + 24 v4.0 + 9 v5.0 + 23 v6.0 + 12 v7.0)
- v6.0 duration: 1 day (2026-02-15)
- v5.0 duration: 1 day (2026-02-14)

**Recent Trend:**
- Last 5 plans avg: ~3 min
- Trend: Stable

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

Recent:
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

### Pending Todos

- Session store: conversation indexing agent (deferred)

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
Stopped at: Completed 32.2-02-PLAN.md (typed XML signatures in resource entry functions table)
Branch: main
Resume file: .planning/phases/32.2-userview-tool-call-stripping/32.2-02-SUMMARY.md
