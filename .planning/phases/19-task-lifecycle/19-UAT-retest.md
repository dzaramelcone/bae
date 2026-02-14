---
status: complete
phase: 19-task-lifecycle
source: [19-03-SUMMARY.md, 19-04-SUMMARY.md, 19-05-SUMMARY.md]
started: 2026-02-14T12:00:00Z
updated: 2026-02-14T12:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Toolbar stays visible during task execution
expected: Launch cortex. Run a long bash command (e.g., `sleep 10`). While it runs, the bottom toolbar remains visible showing mode, cwd, and task count ("1 task"). Toolbar does NOT disappear.
result: pass

### 2. Ctrl-C opens inline task menu
expected: While a task is running (bash `sleep 30` or NL query), press Ctrl-C once. The bottom toolbar switches to a numbered task list showing the running task(s). No full-screen dialog appears.
result: pass

### 3. Digit key cancels task from menu
expected: With the task menu open (from test 2), press "1" to cancel the first task. The task is cancelled and if no tasks remain, the menu auto-closes back to normal toolbar.
result: pass

### 4. Ctrl-C in menu kills all tasks
expected: Start 2+ tasks (e.g., two NL queries or bash commands). Open task menu with Ctrl-C. Press Ctrl-C again while menu is open. All tasks are killed, menu closes, returns to bare prompt.
result: pass
flag: "Process stuttering/lagging and dropping/ignoring inputs while NL task is active"

### 5. Esc dismisses task menu
expected: With task menu open, press Esc. Menu closes, normal toolbar returns. Tasks continue running in background.
result: pass
flag: "Toolbar doesn't update for ~1s so it feels unresponsive"

### 6. PY async expression tracked in task menu
expected: In PY mode, run `await asyncio.sleep(30)`. The toolbar shows "1 task". Press Ctrl-C to open task menu — the sleep task appears as a numbered entry with mode "py". Press "1" to cancel it.
result: pass

### 7. AI mode Ctrl-C cancels query
expected: In NL mode, send a query to the AI. While waiting for response, press Ctrl-C to open task menu. The AI task appears. Cancel it with "1" — no AI output appears after cancellation.
result: issue
reported: "AI tasks cause stuttering/ignoring inputs so ctrl+c is ignored"
severity: major

## Summary

total: 7
passed: 6
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "AI task cancellable via Ctrl-C task menu during NL query"
  status: fixed
  reason: "User reported: AI tasks cause stuttering/ignoring inputs so ctrl+c is ignored"
  severity: major
  test: 7
  root_cause: "AI subprocess inherits parent stdin fd -- Claude CLI and prompt_toolkit compete for same stdin, causing dropped keystrokes and input lag. Missing stdin=asyncio.subprocess.DEVNULL in create_subprocess_exec call."
  artifacts:
    - path: "bae/repl/ai.py"
      issue: "create_subprocess_exec missing stdin=DEVNULL -- subprocess inherits terminal stdin"
  fix_applied:
    - "stdin=asyncio.subprocess.DEVNULL added to ai.py and bash.py (cd66894)"
    - "Session reset after CancelledError to prevent lock errors (28ea212)"
  debug_session: ".planning/debug/ai-input-stutter.md"
