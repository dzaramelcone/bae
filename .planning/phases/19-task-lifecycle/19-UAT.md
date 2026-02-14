---
status: complete
phase: 19-task-lifecycle
source: [19-01-SUMMARY.md, 19-02-SUMMARY.md]
started: 2026-02-14T03:15:00Z
updated: 2026-02-14T06:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Toolbar shows mode indicator
expected: Launch cortex. Bottom toolbar shows current mode name. Switch mode with Shift+Tab — toolbar updates to show new mode.
result: pass

### 2. Toolbar shows running task count
expected: Run a long AI or bash task. While it runs, toolbar shows task count (e.g., "1 task"). When task completes, count disappears.
result: issue
reported: "Ctrl-C still doesn't work in AI mode. Python tasks (await asyncio.sleep(25)) don't add to tracker — no way to cancel. Bash kill menu opens full screen dialog — jarring theme change, too many button presses. Needs inline multiselect like GSD install, Esc to cancel, Enter on line to toggle/cancel."
severity: major

### 3. Toolbar shows cwd
expected: Bottom toolbar shows current working directory as a home-relative path (e.g., "~/lab/bae").
result: pass

### 4. Ctrl-C exits when idle
expected: With no tasks running, pressing Ctrl-C at the bare prompt exits cortex cleanly (same as before — REPL-12 preserved).
result: pass

### 5. Ctrl-C opens kill menu with running tasks
expected: While a long-running task is active, pressing Ctrl-C once opens a dialog listing active tasks with checkboxes. Selecting a task and confirming cancels it.
result: issue
reported: "Ctrl-C still doesn't work in AI mode. Bash kill menu opens full-screen dialog — wrong theme, jarring, too many presses. Needs inline multiselect: arrow keys to move, Enter to cancel a task, Esc to dismiss. PY mode async tasks (await asyncio.sleep(25)) not tracked either."
severity: major

### 6. Double Ctrl-C kills all tasks
expected: While tasks are running, pressing Ctrl-C twice rapidly (within ~0.4s) cancels all running tasks and returns to the bare cortex prompt. No orphan processes remain.
result: issue
reported: "does not cancel all"
severity: major

### 7. Custom toolbar widget from PY mode
expected: In PY mode, run `toolbar.add("hello", lambda: [("", " hello ")])`. The word "hello" appears in the bottom toolbar. Run `toolbar.remove("hello")` to remove it.
result: pass

## Summary

total: 7
passed: 4
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "Kill menu appears inline on Ctrl-C, Enter cancels selected task, Esc dismisses"
  status: failed
  reason: "User reported: kill menu opens full-screen dialog with wrong theme, too many keypresses. AI mode Ctrl-C doesn't work. PY await tasks not tracked."
  severity: major
  test: 5
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "Double Ctrl-C cancels all running tasks"
  status: failed
  reason: "User reported: does not cancel all"
  severity: major
  test: 6
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "Toolbar shows running task count while task executes"
  status: failed
  reason: "User reported: toolbar disappears while process blocks for both AI and bash"
  severity: major
  test: 2
  root_cause: "prompt_toolkit bottom_toolbar only renders during active prompt_async() session. After user submits input, prompt_async() returns and toolbar is erased. During await _dispatch(text), no prompt session is active so no toolbar renders. This is documented prompt_toolkit behavior."
  artifacts:
    - path: "bae/repl/shell.py"
      issue: "run() loop awaits _dispatch() after prompt_async() returns — toolbar not visible during task execution"
  missing:
    - "Run _dispatch() as background task and keep prompt_async() active so toolbar stays visible"
  debug_session: ".planning/debug/toolbar-disappears.md"

- truth: "Ctrl-C opens kill menu listing active tasks; AI tasks can be cancelled"
  status: failed
  reason: "User reported: only bash cancels, AI does not. Kill menu never appears — prompt_toolkit key binding only fires at idle prompt, but architecture awaits each dispatch so prompt is never active during task execution"
  severity: major
  test: 5
  root_cause: "Two issues: (1) Kill menu key binding only fires during prompt_async() input loop, never during _dispatch() execution — Ctrl-C becomes SIGINT/KeyboardInterrupt instead. (2) AI cancellation race: task.cancel() is async, but claude subprocess may complete and process.communicate() returns before CancelledError is delivered, so response still prints."
  artifacts:
    - path: "bae/repl/shell.py"
      issue: "Key binding registered in prompt_toolkit only fires during input, not during task execution. KeyboardInterrupt handler at run() level bypasses kill menu."
    - path: "bae/repl/ai.py"
      issue: "Race between subprocess completion and CancelledError delivery — response writes before cancellation arrives"
  missing:
    - "Move kill menu logic into KeyboardInterrupt handler in run() loop (works in async context)"
    - "Add CancelledError guard around response write in AI.__call__"
  debug_session: ".planning/debug/kill-menu-and-ai-cancel.md"
