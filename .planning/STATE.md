# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-13)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v4.0 Cortex — Phase 18 AI Agent

## Current Position

Phase: 17 of 19 (Namespace)
Plan: 3 of 3 complete
Status: Phase complete
Last activity: 2026-02-14 -- Gap closure: <cortex> sys.modules registration for REPL annotation resolution

Progress: v1.0 done | v2.0 done | v3.0 done | v4.0 [######--] 58%

## Performance Metrics

**Velocity:**
- Total plans completed: 54 (13 v1.0 + 21 v2.0 + 9 v3.0 + 11 v4.0)
- v1.0 duration: 1 day (2026-02-04 -> 2026-02-05)
- v2.0 duration: 2 days (2026-02-07 -> 2026-02-08)
- v3.0 duration: 5 days (2026-02-04 -> 2026-02-09)

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 14-01 | Cortex REPL skeleton | 7min | 2 | 6 |
| 14-02 | Bash dispatch & completion | 2min | 2 | 3 |
| 14-03 | Expression capture fix | 2min | 2 | 3 |
| 15-01 | SessionStore class | 2min | 2 | 2 |
| 15-02 | Store REPL integration | 3min | 2 | 4 |
| 15-03 | Gap closure: stdout + callable store | 2min | 2 | 5 |
| 15-04 | Gap closure: formatting + dict returns | 2min | 2 | 3 |
| 16-01 | Channel & ChannelRouter (TDD) | 3min | 2 | 2 |
| 16-02 | Shell channel integration | 3min | 2 | 3 |
| 17-01 | Namespace seeding & NsInspector (TDD) | 3min | 2 | 2 |
| 17-02 | Shell namespace wiring | 2min | 2 | 2 |
| 17-03 | Gap closure: REPL annotation resolution | 2min | 2 | 2 |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.
v4.0 architectural decisions:
- NL is the primary mode; Py REPL is POC-level, not polished
- Session Store is foundational -- all I/O labeled, indexed, RAG-friendly, comes early
- Channel I/O wraps graph.arun() -- no bae source modifications (wrapper pattern)
- Cortex owns the event loop; graph execution uses arun() only, never run()
- prompt_toolkit 3.0 for REPL foundation (not IPython)
- Explicit mode switching via Shift+Tab (not auto-detect)
- Kitty Shift+Enter mapped to (Escape, ControlM) tuple -- avoids Keys enum extension
- Shared namespace across all modes (asyncio, os, __builtins__ seeded)
- rlcompleter wraps live namespace dict for PY mode tab completion (Completer ABC = future LSP interface)
- DynamicCompleter returns None in non-PY modes (matches DynamicLexer pattern)
- Local boolean flag for expression-capture tracking (simpler than namespace injection)
- Synchronous record() for SessionStore -- microsecond INSERTs, no async wrapper needed
- FTS5 external content table with triggers for automatic index sync
- Content truncation at 10,000 chars with metadata.truncated flag
- dispatch_bash returns (stdout, stderr) tuple -- pure data function, caller routes through channels
- NL/GRAPH stubs record output for future session continuity
- SessionStore.__call__ replaces make_store_inspector closure (callable class, returns None for clean display)
- sys.stdout swap in async_exec for print() capture (try/finally, StringIO buffer)
- Canonical tag format [mode:channel:direction] -- always 3 fields, single _format_entry method
- Public SessionStore API returns plain dicts; sqlite3.Row used only internally
- Channel.write() always records + buffers regardless of visibility; display is the only conditional
- ChannelRouter.write() to unknown channel is silent no-op (defensive dispatch)
- All mode output routes through router.write() -- no bare print() for channel-routed output
- Input recording stays as direct store.record() -- channels are output-only
- channel_arun wraps graph.arun() with temporary logging handler -- no bae/graph.py modifications
- Plain print() for all ns() output -- flows through async_exec stdout capture and [py] channel
- NsInspector callable class with __repr__ -- typing 'ns' shows usage hint, not function address
- classify_fields() reused from bae.resolver for ns(Node) field introspection
- GRAPH mode error handler captures _trace then routes traceback through [graph] channel (matches PY mode pattern)
- Trace capture pattern: store trace in namespace on success, extract from exception.trace on error
- Register <cortex> in sys.modules rather than threading globalns through resolver/lm/compiler (zero production changes)
- namespace.__name__ = '<cortex>' via setdefault so REPL-defined classes get correct __module__

### Pending Todos

- Update `tests/traces/json_structured_fill_reference.py` -- drifted from real backend
- Bump Python requirement to 3.14 stable

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-14
Stopped at: Completed 17-03-PLAN.md (Gap closure: <cortex> sys.modules registration -- phase 17 complete, 3 of 3 plans done)
Branch: main
Resume file: None
