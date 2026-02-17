---
status: resolved
trigger: "Diagnose root cause for this UAT gap: read() task listing doesn't show task IDs"
created: 2026-02-16T00:00:00Z
updated: 2026-02-16T00:00:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: Task ID is simply omitted from format_task_row() output
test: Reading view.py to confirm format_task_row implementation
expecting: format_task_row builds output string without including task['id']
next_action: Confirm ID location and relationship to gap 1 (short IDs)

## Symptoms

expected: Task listing from read() should show task IDs so users can reference them in done(id), update(id), read(id)
actual: format_task_row only shows status | priority | title | tags — no ID field
errors: None (not an error, just missing information)
reproduction: Call read() to list tasks, observe no IDs in output
started: By design — format_task_row never included IDs

## Eliminated

## Evidence

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/spaces/tasks/view.py lines 21-32 (format_task_row)
  found: Function builds output from status, priority, title, tags only. No task['id'] referenced.
  implication: ID is intentionally omitted, not a bug in extraction

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/spaces/tasks/view.py lines 35-59 (format_task_detail)
  found: format_task_detail DOES show ID in line 38: "Task: {task['id']}"
  implication: ID is available in task dict and shown in detail view, just not in list view

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/spaces/tasks/view.py lines 62-72 (format_task_list)
  found: Calls format_task_row for each task (line 71), prepends with "  " only
  implication: No ID injection at list level either

- timestamp: 2026-02-16T00:00:00Z
  checked: format_search_results (lines 75-82)
  found: Uses f"  #{i} {format_task_row(task)}" — rank number, not task ID
  implication: Search results also don't show task IDs

## Resolution

root_cause: Task ID is intentionally omitted from format_task_row() implementation. The function only formats status, priority, title, and tags (line 22 comment confirms this design). Task IDs are shown in format_task_detail() but not in list views.

fix: Add task['id'] to the beginning of format_task_row() output string. Most sensible location is before status, formatted as "ID | status | priority | title | tags"

verification:

files_changed: []

## Relationship to Gap 1 (Short Base36 IDs)

**Independent but complementary:**
- Gap 1: UUIDs are too long for comfortable display/copying
- Gap 2: IDs aren't shown in list view at all

**Solution interaction:**
- If Gap 1 implements short base36 IDs (e.g., "a3k9f2"), those become display-friendly
- Gap 2 fix should use whatever ID format is available (will automatically benefit from Gap 1 if implemented first)
- If Gap 1 NOT implemented: format_task_row should still show full UUID (better than nothing)

**Recommendation:**
- Gap 2 fix is independent: add ID column regardless of ID format
- If short IDs exist in task dict (e.g., task['short_id']), prefer that
- Otherwise fall back to task['id']
- Format: `{id_to_show} | {status} | {priority} | {title} | {tags}`
