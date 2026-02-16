---
status: complete
phase: 33-task-resourcespace
source: 33-01-SUMMARY.md, 33-02-SUMMARY.md
started: 2026-02-16T23:45:00Z
updated: 2026-02-16T23:45:00Z
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
  status: failed
  reason: "User reported: uuid is too many tokens - ideally just do like base 36 encoded ints for them so theyre short, url friendly, token friendly and database friendly"
  severity: major
  test: 2
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
- truth: "update(task_id, status='in_progress') works with positional task_id and keyword fields"
  status: failed
  reason: "User reported: update('id', 'in_progress') fails with 'Cannot update field kwargs'; update('id', status='in_progress') fails with pydantic validation 'Field required'; only update(task_id='id', status='in_progress') works"
  severity: major
  test: 5
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
- truth: "Task listing shows IDs so users can reference tasks in done(), update(), read(id)"
  status: failed
  reason: "User reported: read() listing doesn't show task IDs — no way to get the ID needed for done(), update(), read(id). format_task_row only shows status | priority | title | tags. Fundamental UX blocker."
  severity: blocker
  test: 6
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
