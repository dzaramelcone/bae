---
status: complete
phase: 33-task-resourcespace
source: 33-01-SUMMARY.md, 33-02-SUMMARY.md, 33-03-SUMMARY.md
started: 2026-02-17T00:15:00Z
updated: 2026-02-17T02:30:00Z
---

## Tests

### 1. Navigate into task room
expected: Calling `tasks()` enters task room showing status counts and functions table with read, write, edit, glob, grep tools
result: pass

### 2. Create a task with write()
expected: `write("My test task")` creates a task and returns confirmation with an integer ID. Default status is open, default priority is 0.0.0.
result: pass

### 3. List tasks with read()
expected: `read()` shows active tasks with ID as the first column, followed by status, priority, title, and tags. IDs are plain integers.
result: pass

### 4. Read a specific task by ID
expected: `read(1)` shows full task detail including title, status, priority, creator, timestamps, and body. Int args coerced to str.
result: pass

### 5. Edit with positional ID and keyword fields
expected: `edit(1, status="in_progress")` transitions the task to in_progress and returns full task detail.
result: pass

### 6. Mark a task done with edit()
expected: `edit(1, status="done")` marks the task as done via lifecycle and returns full task detail.
result: pass

### 7. Search tasks with grep()
expected: `grep("keyword")` performs full-text search with LIKE fallback for short terms.
result: pass

### 8. Uniform tool interface and cleanup
expected: Tools are read/write/edit/glob/grep matching other rooms. Navigating away removes them. Python call signatures in functions table.
result: pass
notes: Major refactor during UAT — renamed add/update/search/done to standard verbs, added glob, extracted shared _functions_table, renamed Resourcespace→Room

### 9. Homespace shows inline status counts
expected: Rooms listing shows `tasks() -- Manage todo lists | Start here. | open: 1 ...` with "Start here." only when open > 0.
result: pass

## Summary

total: 9
passed: 9
issues: 0
pending: 0
skipped: 0

## Gaps

None — all issues resolved during UAT session.

## UAT-driven changes

- Renamed tool verbs: add→write, update→edit, search→grep, done→edit(status="done")
- Added glob tool with auto-wrap for bare strings
- Renamed Resourcespace→Room across entire codebase
- Extracted shared `_functions_table()` for uniform display
- Python call signatures instead of XML tags
- Moved fewshot examples to system prompt template
- Slimmed home() to compact rooms + tools only
- Replaced base36 IDs with plain integers
- Fixed source grep package detection (__init__.py)
- Int→str coercion in dispatch wrapper
- LIKE fallback for short FTS terms
