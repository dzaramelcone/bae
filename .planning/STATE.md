# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v5.0 Stream Views — Phase 25

## Current Position

Phase: 25 of 25
Plan: 3 of 3 in Phase 25 (complete)
Status: Phase 25 complete (views + tool call display gap closure)
Last activity: 2026-02-14 — Plan 25-03 complete (tool call display summarization)

Progress: v1.0 done | v2.0 done | v3.0 done | v4.0 done | v5.0 [██████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 75 (13 v1.0 + 21 v2.0 + 9 v3.0 + 24 v4.0 + 9 v5.0)
- v1.0 duration: 1 day (2026-02-04 -> 2026-02-05)
- v2.0 duration: 2 days (2026-02-07 -> 2026-02-08)
- v3.0 duration: 5 days (2026-02-04 -> 2026-02-09)
- v4.0 duration: 2 days (2026-02-13 -> 2026-02-14)

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

Recent context for v5.0:
- Research recommends zero new dependencies -- all v5.0 built on Rich, prompt_toolkit, stdlib
- All Rich rendering MUST use Console(file=StringIO()) then print_formatted_text(ANSI()) -- direct print corrupts REPL
- Tool call regex must exclude code fences to avoid false positives on legitimate XML in Python
- **Execution convention: xml_tag** -- `<run>code</run>` for executable, regular fences for illustrative. 100% convention compliance across all models. Selected over fence_annotation (97.2%) for clean separation.
- **xml_tag implemented** -- extract_executable() with `<run>` regex replaces extract_code(). Eval loop executes only first block. No backward compat (bare fences no longer execute).
- **translate_tool_calls() implemented** -- Pure function: text -> list[str] of Python code. All 5 tool types (R, W, E, G, Grep). Fence/run exclusion. ALL tags translated (list return). Output truncation to 4000 chars.
- **Tool call translation wired into eval loop** -- translate_tool_calls() checked before extract_executable() on each iteration. Tool tags take precedence over `<run>` blocks. All tool calls executed independently, outputs combined with --- separator into single [Tool output] feedback. System prompt teaches AI all 5 tag formats with reference table and fewshot examples.
- **ViewFormatter protocol** -- Strategy pattern via @runtime_checkable Protocol in channels.py. Channel._formatter field (default None) with _display() delegation. Enables pluggable display without modifying Channel identity. Zero new dependencies.
- **UserView execution display** -- Concrete ViewFormatter in views.py. Buffers ai_exec, flushes grouped Rich Panel (Syntax + Rule + Text) on ai_exec_result. Fallback prefix display for all other py writes. Wired to py channel only. Zero new dependencies.
- **DebugView + AISelfView** -- Two additional stateless ViewFormatters. DebugView: raw `[channel] key=value` metadata headers + indented content. AISelfView: AI-perspective tag mapping (ai-output, exec-code, exec-result, tool-call, tool-output). ViewMode enum + VIEW_CYCLE + VIEW_FORMATTERS routing infrastructure for shell wiring.
- **View toggling wired** -- Ctrl+V keybinding cycles ViewMode (USER->DEBUG->AI_SELF). _set_view creates fresh formatter instance and swaps all channel formatters. make_view_widget toolbar indicator hidden in USER, shows mode name otherwise. toolbar.view style class.
- **Tool call display summarization** -- _tool_summary() generates concise one-liners per tool type (read/glob/grep get counts, write/edit passthrough). tool_translated metadata carries tool_summary field. UserView renders single gray italic line. Raw tool_result write removed -- AI feedback still gets full output via all_outputs.

### Pending Todos

- Update `tests/traces/json_structured_fill_reference.py` -- drifted from real backend
- Bump Python requirement to 3.14 stable
- AI streaming/progressive display for NL responses
- Session store: conversation indexing agent — partitions large contexts by topic with short summaries + tags, organized as a B-tree (recursive if needed). Prior session info no longer auto-included; replaced by a labeled REMEMBER object showing recent summaries with tags and partition references.
- AI agent doesn't see user's REPL I/O (typed commands, stdout) -- needs feedback channel from eval loop to AI context
- AI self-view: bash tags not mapped to [tool-call], Read tag duplicated across [ai-output] and [tool-call], tool output echoed in AI response
- UserView execution display: raw [ai:1] lines leak <run> block before Rich panel, execution output above panel not grouped below, code duplicated

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-14
Stopped at: Completed 25-03-PLAN.md (tool call display summarization, UAT gap closure)
Branch: main
Resume file: None
