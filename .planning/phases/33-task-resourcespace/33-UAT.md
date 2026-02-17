---
status: resolved
phase: 33-task-resourcespace
source: 33-01-SUMMARY.md, 33-02-SUMMARY.md
started: 2026-02-16T23:45:00Z
updated: 2026-02-17T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Navigate into task resourcespace
expected: Calling `tasks()` enters task resourcespace showing status counts and functions table with read, add, done, update, search tools
result: pass

### 2. Create a task with add()
expected: `add("My test task")` creates a task and returns a confirmation with a UUID task ID. The task has status open and default 0.0.0 priority.
result: issue
reported: "uuid is too many tokens - ideally just do like base 36 encoded ints for them so theyre short, url friendly, token friendly and database friendly"
severity: major

### 3. List tasks with read()
expected: `read()` shows active tasks with status, priority, title, and tags in a formatted list
result: pass

### 4. Read a specific task by ID
expected: `read("task-id")` shows full task detail including title, status, priority, creator, timestamps, and body
result: pass

### 5. Update a task with update()
expected: `update("task-id", status="in_progress")` transitions the task to in_progress and confirms the change
result: issue
reported: "update('id', 'in_progress') fails with 'Cannot update field kwargs'; update('id', status='in_progress') fails with pydantic validation 'Field required'; only update(task_id='id', status='in_progress') works — positional task_id + keyword fields should work"
severity: major

### 6. Mark a task done with done()
expected: `done("task-id")` marks the task as done and returns confirmation
result: issue
reported: "read() listing doesn't show task IDs — no way to get the ID needed for done(), update(), read(id). format_task_row only shows status | priority | title | tags. Fundamental UX blocker."
severity: blocker

### 7. Search tasks with search()
expected: `search("keyword")` performs full-text search and returns matching tasks ranked by relevance
result: pass

### 8. Filter tasks by status or tag
expected: `read("status:blocked")` or `read("tag:urgent")` returns only matching tasks
result: pass

### 9. Custom tool names cleaned on navigation away
expected: After navigating into tasks() (tools add/done/update/search appear), navigating away (e.g., `home()` or `source()`) removes add/done/update/search from the namespace
result: pass

### 10. Homespace shows outstanding task count
expected: When tasks exist (open/in_progress/blocked), the homespace orientation includes "Tasks: N outstanding"
result: pass

### 11. Persistence across sessions
expected: Tasks created in one session survive — restarting the REPL and entering tasks() shows previously created tasks
result: pass

## Summary

total: 11
passed: 8
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "Task IDs should be short, token-friendly identifiers"
  status: resolved
  reason: "User reported: uuid is too many tokens - ideally just do like base 36 encoded ints for them so theyre short, url friendly, token friendly and database friendly"
  severity: major
  test: 2
  root_cause: "TaskStore.create() at models.py:115 generates IDs with str(uuid.uuid7()) producing 36-char strings. Schema uses TEXT PK. Change to INTEGER PRIMARY KEY AUTOINCREMENT + base36 encode for display."
  artifacts:
    - path: "bae/repl/spaces/tasks/models.py"
      issue: "uuid7 ID generation at line 115, TEXT PK schema at line 13, all FK references use TEXT"
  missing:
    - "Change schema from TEXT to INTEGER AUTOINCREMENT for task IDs"
    - "Add base36 encode/decode utility for external display"
    - "Update all FK references from TEXT to INTEGER"
  debug_session: ".planning/debug/task-id-uuid7-to-base36.md"
- truth: "update(task_id, status='in_progress') works with positional task_id and keyword fields"
  status: resolved
  reason: "User reported: update('id', 'in_progress') fails with 'Cannot update field kwargs'; update('id', status='in_progress') fails with pydantic validation 'Field required'; only update(task_id='id', status='in_progress') works"
  severity: major
  test: 5
  root_cause: "_build_validator() in bae/repl/tools.py doesn't handle VAR_KEYWORD parameters. Creates literal 'kwargs' pydantic field instead of allowing arbitrary extra fields. Need to skip VAR_KEYWORD params and set extra='allow' on model."
  artifacts:
    - path: "bae/repl/tools.py"
      issue: "_build_validator() lines 39-47 doesn't check param.kind, treats **kwargs as regular param"
    - path: "bae/repl/spaces/tasks/service.py"
      issue: "update() uses **kwargs signature"
  missing:
    - "Skip VAR_KEYWORD parameters in _build_validator() field dict"
    - "Set pydantic model extra='allow' when VAR_KEYWORD param exists"
  debug_session: ".planning/debug/update-kwargs-pydantic.md"
- truth: "Task listing shows IDs so users can reference tasks in done(), update(), read(id)"
  status: resolved
  reason: "User reported: read() listing doesn't show task IDs — no way to get the ID needed for done(), update(), read(id). format_task_row only shows status | priority | title | tags. Fundamental UX blocker."
  severity: blocker
  test: 6
  root_cause: "format_task_row() in view.py deliberately only formats status | priority | title | tags. ID is available in task dict but omitted from list output."
  artifacts:
    - path: "bae/repl/spaces/tasks/view.py"
      issue: "format_task_row() lines 21-32 omits task['id'] from output"
  missing:
    - "Add ID to beginning of format_task_row output"
  debug_session: ".planning/debug/task-ids-missing-in-list.md"
