---
phase: 20-ai-eval-loop
plan: 01
subsystem: ui
tags: [rich, markdown, ansi, prompt-toolkit, terminal-rendering]

# Dependency graph
requires:
  - phase: 16-channels
    provides: "Channel and ChannelRouter output multiplexing"
  - phase: 19-task-lifecycle
    provides: "TaskManager, inline task menu, key bindings"
provides:
  - "render_markdown() -- Rich Markdown to ANSI string conversion"
  - "Markdown-aware Channel._display for AI output"
  - "Task menu scrollback printing via _print_task_menu()"
affects: [ai-eval-loop, ai-streaming]

# Tech tracking
tech-stack:
  added: [rich>=14.3]
  patterns: [rich-console-to-ansi, prompt-toolkit-ansi-bridge]

key-files:
  created: []
  modified:
    - pyproject.toml
    - bae/repl/channels.py
    - bae/repl/shell.py
    - tests/repl/test_channels.py
    - tests/repl/test_task_lifecycle.py

key-decisions:
  - "Rich Console with force_terminal=True and StringIO for ANSI capture (no terminal required)"
  - "Channel.markdown flag with CHANNEL_DEFAULTS propagation (only AI channel enabled)"
  - "Task menu prints to scrollback, toolbar always renders normal widgets"
  - "render_markdown detects terminal width per-render via os.get_terminal_size()"

patterns-established:
  - "Rich-to-ANSI bridge: Console(file=StringIO, force_terminal=True) -> print_formatted_text(ANSI(...))"
  - "Scrollback printing: _print_task_menu uses print_formatted_text with FormattedText tuples"

# Metrics
duration: 4min
completed: 2026-02-14
---

# Phase 20 Plan 01: Display Layer Summary

**Rich markdown rendering for AI channel output and Ctrl-C task menu moved to scrollback**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-14T12:40:12Z
- **Completed:** 2026-02-14T12:44:43Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- AI channel output renders markdown formatting (headers, bold, code blocks, lists) via Rich Markdown -> ANSI -> prompt_toolkit bridge
- Ctrl-C task menu prints numbered task list to scrollback instead of hijacking the toolbar
- Toolbar always renders normal widgets regardless of task menu state

## Task Commits

Each task was committed atomically:

1. **Task 1: Rich markdown rendering for AI channel output** - `3b63b65` (feat)
2. **Task 2: Task menu in scrollback instead of toolbar** - `7b9757c` (feat)

## Files Created/Modified
- `pyproject.toml` - Added rich>=14.3 dependency
- `bae/repl/channels.py` - render_markdown(), Channel.markdown flag, CHANNEL_DEFAULTS["ai"]["markdown"], markdown-aware _display()
- `bae/repl/shell.py` - _print_task_menu() helper, Ctrl-C prints to scrollback, digit cancel reprints, toolbar always normal
- `tests/repl/test_channels.py` - 6 new tests for markdown rendering and channel flag behavior
- `tests/repl/test_task_lifecycle.py` - 2 new tests for scrollback printing, updated toolbar test

## Decisions Made
- Rich Console with force_terminal=True writes to StringIO -- captures ANSI escape sequences even without a real terminal
- Channel.markdown flag defaults to False; only AI channel sets True via CHANNEL_DEFAULTS
- render_markdown() detects terminal width per-render via os.get_terminal_size() for resize handling
- Task menu prints to scrollback using FormattedText tuples, same visual as render_task_menu but permanent in scroll history

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Markdown rendering ready for AI eval loop (plan 03) to use when displaying AI responses
- Task menu scrollback printing complete, no further UX changes needed
- render_task_menu() still available in toolbar.py for reference or reuse

## Self-Check: PASSED

All files found. All commits found. Summary verified.

---
*Phase: 20-ai-eval-loop*
*Completed: 2026-02-14*
