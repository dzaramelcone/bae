---
phase: 14-shell-foundation
plan: 01
subsystem: repl
tags: [prompt-toolkit, pygments, async-repl, mode-switching, top-level-await]

# Dependency graph
requires: []
provides:
  - "bae/repl/ package with CortexShell, Mode enum, async_exec"
  - "bae CLI launches cortex REPL with no arguments"
  - "Mode switching via Shift+Tab (NL/PY/GRAPH/BASH)"
  - "Python execution with top-level await (PyCF_ALLOW_TOP_LEVEL_AWAIT)"
affects: [14-02-PLAN, phase-15, phase-18]

# Tech tracking
tech-stack:
  added: [prompt-toolkit 3.0.50+, pygments 2.19+]
  patterns: [async-repl-loop, mode-dispatch, ast-exec-with-await, kitty-shift-enter-registration]

key-files:
  created:
    - bae/repl/__init__.py
    - bae/repl/shell.py
    - bae/repl/modes.py
    - bae/repl/exec.py
  modified:
    - bae/cli.py
    - pyproject.toml

key-decisions:
  - "Kitty Shift+Enter mapped to (Escape, ControlM) tuple in ANSI_SEQUENCES -- triggers same handler as Escape+Enter"
  - "F-key remapping avoided; kitty CSI u sequence routes through existing Escape+Enter binding path"
  - "Namespace seeded with asyncio, os, and __builtins__ for immediate utility in PY mode"

patterns-established:
  - "async_exec pattern: ast.parse + expression capture in _ + PyCF_ALLOW_TOP_LEVEL_AWAIT + types.FunctionType"
  - "Mode dispatch in CortexShell.run() -- if/elif chain on self.mode"
  - "DynamicLexer/toolbar callables for per-mode visual switching"
  - "ANSI_SEQUENCES registration for terminal-specific key support"

# Metrics
duration: 7min
completed: 2026-02-13
---

# Phase 14 Plan 01: Cortex REPL Skeleton Summary

**Async REPL shell with four modes (NL/PY/GRAPH/BASH), prompt_toolkit mode switching via Shift+Tab, Python execution with top-level await, and bae CLI integration**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-13T20:33:31Z
- **Completed:** 2026-02-13T20:40:47Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Four-module REPL package: shell.py (CortexShell), modes.py (Mode enum + colors), exec.py (async_exec), __init__.py (launch entry)
- Python execution engine using PyCF_ALLOW_TOP_LEVEL_AWAIT -- sync code, await expressions, and variable persistence all verified
- Mode switching via Shift+Tab with colored prompt, Python syntax highlighting in PY mode, bottom toolbar showing mode + cwd
- Enter submits, Escape+Enter inserts newline, kitty Shift+Enter registered for kitty-protocol terminals
- `bae` with no arguments launches cortex REPL; existing subcommands (graph, run) unchanged

## Task Commits

Each task was committed atomically:

1. **Task 1: Create REPL package with modes, shell, and Python execution** - `ef14ea0` (feat)
2. **Task 2: Wire cortex launch into bae CLI entry point** - `0cb5cf0` (feat)

## Files Created/Modified
- `bae/repl/__init__.py` - Entry point: launch() calls asyncio.run(CortexShell().run())
- `bae/repl/shell.py` - CortexShell: PromptSession with mode dispatch, key bindings, toolbar
- `bae/repl/modes.py` - Mode enum (NL/PY/GRAPH/BASH), colors, names, cycle order
- `bae/repl/exec.py` - async_exec: compile with PyCF_ALLOW_TOP_LEVEL_AWAIT, capture last expression in _
- `bae/cli.py` - Changed to invoke_without_command, added cortex callback
- `pyproject.toml` - Added prompt-toolkit and pygments dependencies

## Decisions Made
- Kitty Shift+Enter (`\x1b[13;2u`) mapped to `(Keys.Escape, Keys.ControlM)` in ANSI_SEQUENCES rather than creating a custom Keys enum member (which is not supported by prompt_toolkit's _parse_key). This routes kitty Shift+Enter through the existing Escape+Enter newline binding.
- Namespace seeded with asyncio, os, and __builtins__ so PY mode is immediately useful without imports.
- NL mode stub echoes input and shows "NL mode coming in Phase 18" rather than falling back to Python execution.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Kitty Shift+Enter Keys enum incompatibility**
- **Found during:** Task 1 (shell.py key bindings)
- **Issue:** Plan specified `Keys("s-enter")` but prompt_toolkit's Keys enum has no `s-enter` member. `_parse_key` rejects non-enum multi-char strings.
- **Fix:** Mapped `"\x1b[13;2u"` to `(Keys.Escape, Keys.ControlM)` tuple instead. The Vt100Parser decomposes tuples into sequential key events, triggering the existing `escape`, `enter` binding which inserts newline. Same user-visible behavior.
- **Files modified:** bae/repl/shell.py
- **Verification:** Binding chain verified: ANSI_SEQUENCES -> tuple -> Escape+Enter handler -> insert_text("\n")
- **Committed in:** ef14ea0 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal -- same user-visible behavior, cleaner implementation that avoids monkeypatching the Keys enum.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- REPL skeleton complete, ready for Plan 02 (bash mode wiring with subprocess dispatch)
- NL and Graph modes are stubs awaiting Phase 18 and future phases
- Namespace is shared across modes as designed -- future phases add to it

## Self-Check: PASSED

All 7 files verified present. Both task commits (ef14ea0, 0cb5cf0) verified in git log.

---
*Phase: 14-shell-foundation*
*Completed: 2026-02-13*
