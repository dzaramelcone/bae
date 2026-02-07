# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-07)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v2.0 Context Frames — redesigning node API around context frame paradigm

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-02-07 — Milestone v2.0 started

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
v2 design decisions documented in PROJECT.md v2 Design Decisions section.

Key v2 decisions:
- Nodes are context frames (fields = prompt context, class name = instruction)
- Dep(callable) for external data with chaining
- Recall() replaces Bind (searches trace by type)
- Context marker eliminated (redundant)
- LM is implicit (graph-level, not in __call__)
- Start node fields are caller-provided
- Terminal node fields ARE the output

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-07
Stopped at: Milestone v2.0 initialization
Resume file: None
