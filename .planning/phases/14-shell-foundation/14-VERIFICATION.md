---
phase: 14-shell-foundation
verified: 2026-02-13T21:22:00Z
status: passed
score: 12/12 must-haves verified
re_verification:
  previous_status: passed
  previous_verified: 2026-02-13T20:48:27Z
  previous_score: 7/7
  gap_closure_plan: 14-03
  gaps_closed:
    - "Expression result spurious output when user code sets _ as loop variable"
  gaps_remaining: []
  regressions: []
---

# Phase 14: Shell Foundation Verification Report

**Phase Goal:** User can launch cortex, switch between modes, write well-edited code, and exit cleanly
**Verified:** 2026-02-13T21:22:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (plan 14-03)

## Re-Verification Summary

**Previous verification:** 2026-02-13T20:48:27Z (status: passed, 7/7 must-haves)
**Gap discovered during UAT:** `for _ in range(20): print(_)` produced spurious output `19` at the end
**Gap closure plan:** 14-03 (TDD, sentinel-guarded expression capture)
**Gap closure verification:** All 7 regression tests pass, sentinel guard implemented correctly
**Regressions:** None detected — all previous must-haves still verified

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `bae` with no arguments launches cortex; user can type `await asyncio.sleep(1)` and it executes | ✓ VERIFIED | cli.py callback invokes launch() when no subcommand (line 56-57); exec.py compiles with PyCF_ALLOW_TOP_LEVEL_AWAIT (line 28), awaits coroutines (lines 31-32) |
| 2 | Shift+Tab cycles through NL / Py / Graph / Bash modes and the prompt visually indicates which mode is active | ✓ VERIFIED | Key binding `s-tab` cycles through MODE_CYCLE (shell.py lines 35-40); _prompt() returns colored prompt based on mode (lines 80-83); _toolbar() shows mode name (lines 97-104) |
| 3 | In Py mode, user gets syntax highlighting, multiline editing (Shift+Enter for newlines), and tab completion on namespace objects | ✓ VERIFIED | DynamicLexer returns PygmentsLexer(PythonLexer) in PY mode (shell.py lines 91-95); multiline=True (line 69); Shift+Enter binding (lines 47-50); NamespaceCompleter wraps rlcompleter (complete.py lines 15-28), wired via DynamicCompleter (shell.py lines 85-89, 68) |
| 4 | In Bash mode, shell commands execute and output appears | ✓ VERIFIED | dispatch_bash() creates subprocess_shell with stdout/stderr pipes (bash.py lines 28-38); called from bash mode handler (shell.py line 147) |
| 5 | Ctrl-C with no tasks exits; Ctrl-D exits with graceful shutdown (tasks cancelled, queues drained) | ✓ VERIFIED | KeyboardInterrupt from prompt_async returns (shell.py line 124); EOFError calls _shutdown() which cancels tasks and prints summary (lines 106-115, 125-127) |
| 6 | Expression result (e.g. `1 + 1`) is captured in _ and returned | ✓ VERIFIED | exec.py: last ast.Expr rewritten to assign to _ (lines 18-26), expr_captured flag set (line 25), returned when true (lines 34-35) |
| 7 | Statements with no expression tail (e.g. `for _ in range(20): print(_)`) return None | ✓ VERIFIED | exec.py: expr_captured remains False when last statement is not ast.Expr (lines 15, 36); test_for_loop_with_underscore_returns_none passes |
| 8 | Await expressions return their result | ✓ VERIFIED | exec.py: await expressions are ast.Expr nodes, captured via _ assignment (lines 18-26), awaited if coroutine (lines 31-32), returned (lines 34-35); test_await_expr_returns_value passes |
| 9 | Code that does not touch _ does not produce spurious output | ✓ VERIFIED | exec.py: sentinel guard prevents unconditional namespace.get('_') return (lines 34-36); shell.py: result printed only when not None (line 135-136); test_for_loop_with_print_returns_none passes |
| 10 | In Bash mode, `cd /tmp` changes the working directory (visible in status bar and affects all modes) | ✓ VERIFIED | dispatch_bash() special-cases cd with os.chdir() (bash.py lines 19-26); status bar shows cwd via _toolbar() (shell.py lines 97-104) |
| 11 | In Bash mode, stderr appears in red, stdout appears plain | ✓ VERIFIED | bash.py: stdout printed plain (line 36), stderr printed via FormattedText with "fg:red" (line 38) |
| 12 | Ctrl-C during Py mode code execution raises KeyboardInterrupt in code, returns to prompt (does not exit) | ✓ VERIFIED | KeyboardInterrupt in async_exec context caught with `pass`, continues loop (shell.py lines 137-138) |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bae/repl/__init__.py` | launch() entry point for cortex | ✓ VERIFIED | 16 lines; contains `def launch` calling `asyncio.run(CortexShell().run())` (lines 11-13) |
| `bae/repl/shell.py` | CortexShell class with async REPL loop | ✓ VERIFIED | 147 lines; contains `class CortexShell`; imports dispatch_bash, NamespaceCompleter, async_exec; mode dispatch, key bindings, lifecycle management |
| `bae/repl/modes.py` | Mode enum and per-mode config (color, lexer) | ✓ VERIFIED | 34 lines; contains `class Mode(Enum)` with NL/PY/GRAPH/BASH; MODE_COLORS, MODE_NAMES, MODE_CYCLE dicts |
| `bae/repl/exec.py` | async_exec with PyCF_ALLOW_TOP_LEVEL_AWAIT | ✓ VERIFIED | 36 lines; contains PyCF_ALLOW_TOP_LEVEL_AWAIT flag (line 28); sentinel-guarded expression capture (lines 15, 25, 34-36); _EXPR_CAPTURED sentinel (line 9) |
| `bae/repl/bash.py` | Bash subprocess dispatch with cd special-casing | ✓ VERIFIED | 38 lines; contains `async def dispatch_bash`; cd handled via os.chdir (lines 19-26); subprocess with stdout/stderr pipes (lines 28-38) |
| `bae/repl/complete.py` | NamespaceCompleter wrapping rlcompleter | ✓ VERIFIED | 28 lines; contains `class NamespaceCompleter(Completer)`; wraps rlcompleter.Completer on live namespace dict (lines 15-28) |
| `tests/repl/__init__.py` | Package init for repl test module | ✓ VERIFIED | Exists (empty file) |
| `tests/repl/test_exec.py` | Regression tests for async_exec expression capture | ✓ VERIFIED | 63 lines (>30 min); 7 pytest-asyncio tests covering expressions, assignments, loops, await, multiline cases |
| `bae/cli.py` | Typer callback invoking launch() | ✓ VERIFIED | 293 lines; contains `from bae.repl import launch` (line 56); callback invokes launch when no subcommand (lines 52-58) |

**Level 1 (Exists):** All 9 artifacts present
**Level 2 (Substantive):** All artifacts contain expected patterns and meet minimum line counts
**Level 3 (Wired):** All artifacts imported and used correctly

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| bae/cli.py | bae/repl/__init__.py | Typer callback invokes launch() | ✓ WIRED | Import on line 56, called in cortex() callback (line 57) |
| bae/repl/shell.py | bae/repl/exec.py | Py mode dispatches to async_exec() | ✓ WIRED | Import on line 21, called in py mode handler (line 134) with result handling (lines 135-136) |
| bae/repl/shell.py | bae/repl/modes.py | Shell uses Mode enum for prompt/toolbar | ✓ WIRED | Import on line 22, Mode used for self.mode (line 59), MODE_COLORS in _prompt() (line 82), MODE_NAMES in _toolbar() (line 99), MODE_CYCLE in key binding (line 38) |
| bae/repl/shell.py | bae/repl/bash.py | Bash mode dispatches to dispatch_bash() | ✓ WIRED | Import on line 19, called in bash mode handler (line 147) |
| bae/repl/shell.py | bae/repl/complete.py | DynamicCompleter returns NamespaceCompleter in PY mode | ✓ WIRED | Import on line 20, instance created (line 62), returned by _completer() when mode==PY (lines 85-89), wired to PromptSession via DynamicCompleter (line 68) |
| bae/repl/shell.py | bae/repl/exec.py | async_exec return value printed only when not None | ✓ WIRED | Result handling: `if result is not None: print(repr(result))` (lines 135-136); prevents spurious output from loop variables |

**All 6 key links verified as WIRED**

### Requirements Coverage

Phase 14 maps to 9 requirements from REQUIREMENTS.md:

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| REPL-01 | `bae` launches cortex | ✓ SATISFIED | cli.py callback invokes launch() when no subcommand (lines 52-58) |
| REPL-03 | Top-level await support | ✓ SATISFIED | exec.py compiles with PyCF_ALLOW_TOP_LEVEL_AWAIT (line 28), awaits coroutines (lines 31-32) |
| REPL-04 | Shift+Tab cycles modes | ✓ SATISFIED | Key binding on `s-tab` cycles through MODE_CYCLE (shell.py lines 35-40) |
| REPL-05 | Mode indicator in prompt | ✓ SATISFIED | _prompt() returns colored prompt based on mode (lines 80-83); _toolbar() shows mode name + cwd (lines 97-104) |
| REPL-07 | Syntax highlighting and multiline in Py mode | ✓ SATISFIED | DynamicLexer returns PygmentsLexer(PythonLexer) in PY mode (lines 91-95); multiline=True (line 69); Shift+Enter binding (lines 47-50) |
| REPL-08 | Tab completion on namespace objects | ✓ SATISFIED | NamespaceCompleter wraps rlcompleter on live namespace dict (complete.py lines 15-28); DynamicCompleter returns it in PY mode (shell.py lines 85-89, 68) |
| REPL-12 | Ctrl-C with no tasks exits | ✓ SATISFIED | KeyboardInterrupt from prompt_async returns (shell.py line 124) |
| REPL-13 | Ctrl-D graceful shutdown | ✓ SATISFIED | EOFError calls _shutdown() which cancels tasks and prints summary (shell.py lines 106-115, 125-127) |
| REPL-14 | Bash mode executes shell commands | ✓ SATISFIED | dispatch_bash() creates subprocess_shell with output handling (bash.py lines 28-38); called from bash mode handler (shell.py line 147) |

**9/9 requirements satisfied**

### Regression Tests

All 7 regression tests from plan 14-03 pass:

```
tests/repl/test_exec.py::test_expr_returns_value PASSED
tests/repl/test_exec.py::test_assignment_returns_none PASSED
tests/repl/test_exec.py::test_for_loop_with_underscore_returns_none PASSED
tests/repl/test_exec.py::test_for_loop_with_print_returns_none PASSED
tests/repl/test_exec.py::test_await_expr_returns_value PASSED
tests/repl/test_exec.py::test_multiline_last_expr PASSED
tests/repl/test_exec.py::test_multiline_last_statement PASSED
```

**Test suite:** 7/7 tests passing
**Coverage:** Expression capture, assignments, loops with underscore, await, multiline code

### Anti-Patterns Found

**None.** Files scanned: bash.py, complete.py, shell.py, modes.py, exec.py, __init__.py, cli.py, test_exec.py

- No TODO/FIXME/PLACEHOLDER comments
- No empty implementations (return null/{}/)
- No console.log-only handlers
- NL and Graph mode stubs are intentional placeholders for future phases (documented in ROADMAP.md)

### Human Verification Required

The following items cannot be verified programmatically and require human testing:

#### 1. Visual Mode Switching

**Test:** Run `bae`, press Shift+Tab repeatedly
**Expected:** 
- Prompt color changes: blue (NL) → green (PY) → orange (GRAPH) → purple (BASH) → blue
- Status bar shows mode name: NL → PY → GRAPH → BASH → NL
- Status bar shows current working directory with ~ shortening

**Why human:** Visual appearance requires actual terminal rendering

#### 2. Multiline Editing Experience

**Test:** In any mode, press Shift+Enter (or Escape+Enter on non-kitty terminals)
**Expected:** Cursor moves to new line without submitting; Enter submits the multi-line input

**Why human:** Terminal-specific behavior, requires manual key press testing

#### 3. Tab Completion UX

**Test:** In PY mode, type `as` then press Tab
**Expected:** Completion menu appears showing `asyncio`; selecting it completes the word

**Why human:** Requires interactive terminal session to verify completion menu rendering and selection

#### 4. Syntax Highlighting Rendering

**Test:** In PY mode, type `await asyncio.sleep(1)` and observe before pressing Enter
**Expected:** Python syntax highlighting visible (keywords, strings, functions colored differently)

**Why human:** Visual appearance of pygments highlighting in terminal

#### 5. Bash Command Execution and cd Persistence

**Test:** 
1. Run `bae`
2. Press Shift+Tab to BASH mode
3. Type `cd /tmp` and press Enter
4. Type `pwd` and press Enter — should show /tmp
5. Press Shift+Tab to PY mode
6. Type `import os; os.getcwd()` — should show /tmp

**Expected:** cd changes persist across modes (shared cwd)

**Why human:** Multi-step workflow requires sequential interaction

#### 6. Stderr Color Differentiation

**Test:** In BASH mode, type `ls /nonexistent` and press Enter
**Expected:** Error message appears in red

**Why human:** Color rendering verification

#### 7. Lifecycle: Ctrl-C and Ctrl-D with No Tasks

**Test:**
1. Run `bae`, wait at prompt
2. Press Ctrl-C — should exit immediately
3. Run `bae` again, press Ctrl-D — should exit silently

**Expected:** Both exit cleanly with no error messages

**Why human:** Interactive terminal signals

#### 8. Lifecycle: Ctrl-C During Execution

**Test:**
1. Run `bae`, switch to PY mode
2. Type `await asyncio.sleep(10)` and press Enter
3. Press Ctrl-C during the sleep

**Expected:** KeyboardInterrupt caught, execution stops, returns to prompt (does NOT exit cortex)

**Why human:** Timing-dependent interrupt behavior

#### 9. Gap Closure: No Spurious Output

**Test:**
1. Run `bae`, switch to PY mode
2. Type `for _ in range(20): print(_)` and press Enter
3. Observe output

**Expected:** Prints `0` through `19`, each on a new line, with NO trailing `19` repr line

**Why human:** Visual verification of output (requires comparing against expected behavior from UAT)

### Gap Closure Analysis

**Gap identified:** async_exec unconditionally returned `namespace.get('_')`, causing loop variables using `_` to produce spurious output.

**Root cause:** No distinction between expression-capture AST rewrites (which set `_`) and user code that happens to set `_` as a loop variable.

**Fix implemented:** Sentinel-guarded return in exec.py
- Local boolean flag `expr_captured` initialized to False (line 15)
- Set to True only when last statement is ast.Expr (line 25)
- Return `namespace.get('_')` only when flag is True (lines 34-35)
- Return None otherwise (line 36)

**Test coverage:** 7 regression tests added to tests/repl/test_exec.py
- test_expr_returns_value — `1 + 1` returns 2
- test_assignment_returns_none — `x = 42` returns None
- test_for_loop_with_underscore_returns_none — `for _ in range(20): pass` returns None (THE BUG)
- test_for_loop_with_print_returns_none — `for _ in range(5): print(_)` returns None with correct stdout (THE BUG)
- test_await_expr_returns_value — `await asyncio.sleep(0) or 'done'` returns 'done'
- test_multiline_last_expr — multiline code with last line expression returns result
- test_multiline_last_statement — multiline code with last line statement returns None

**Verification:** All 7 tests pass (pytest output captured above)

**Impact:** Gap fully closed. Expression capture works correctly, loop variables do not produce spurious output, no regressions in existing functionality.

## Overall Assessment

**Status:** passed
**Score:** 12/12 must-haves verified
**Phase goal:** ACHIEVED

### Summary

Phase 14 Shell Foundation is complete and verified after gap closure. All success criteria met:

1. ✓ `bae` launches cortex; top-level await works
2. ✓ Shift+Tab cycles modes with visual indicators
3. ✓ Py mode has syntax highlighting, multiline editing, tab completion
4. ✓ Bash mode executes shell commands
5. ✓ Ctrl-C/Ctrl-D lifecycle management works correctly

**Gap closure (plan 14-03) successful:**
- Spurious output from loop variables eliminated
- Sentinel guard implemented with test coverage
- No regressions detected

**Ready for Phase 15:** Session Store

---

_Verified: 2026-02-13T21:22:00Z_
_Verifier: Claude (gsd-verifier)_
