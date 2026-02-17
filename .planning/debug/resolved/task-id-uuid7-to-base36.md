---
status: resolved
trigger: "Diagnose root cause for this UAT gap: Task IDs use uuid7 (36 chars) which wastes tokens. Need short base36 encoded ints — short, url-friendly, token-friendly, database-friendly."
created: 2026-02-16T00:00:00Z
updated: 2026-02-16T00:00:05Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: TaskStore.create() at line 115 generates IDs using uuid.uuid7(), which produces 36-character strings
test: examining models.py to confirm ID generation and schema impact
expecting: find all places that generate/reference task IDs and determine if schema change needed
next_action: gather evidence on ID generation and schema constraints

## Symptoms

expected: Task IDs should be short base36 encoded ints (url-friendly, token-friendly, database-friendly)
actual: Task IDs are uuid7 strings (36 characters long)
errors: none (performance/efficiency issue)
reproduction: any task creation generates uuid7 ID
started: always been this way (design issue)

## Eliminated

## Evidence

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/spaces/tasks/models.py line 115
  found: `task_id = str(uuid.uuid7())` in TaskStore.create()
  implication: this is the single point of ID generation

- timestamp: 2026-02-16T00:00:00Z
  checked: schema definition lines 11-28
  found: `id TEXT PRIMARY KEY` - uses TEXT column type
  implication: schema supports variable-length strings, would need migration to use INTEGER for base36 ints

- timestamp: 2026-02-16T00:00:01Z
  checked: grepped for all task_id/parent_id/blocked_by references
  found: service.py, view.py only READ task IDs (get, update, done), never generate them
  implication: TaskStore.create() line 115 is the ONLY ID generation point

- timestamp: 2026-02-16T00:00:02Z
  checked: schema for existing AUTOINCREMENT usage
  found: task_audit table (line 43) uses `id INTEGER PRIMARY KEY AUTOINCREMENT`
  implication: infrastructure for auto-incrementing integer IDs already exists in same schema

- timestamp: 2026-02-16T00:00:03Z
  checked: actual UUID7 string length
  found: 36 characters (verified with uuid.uuid7())
  implication: switching to base36 encoded ints would save significant tokens (estimated 8-10 chars vs 36)

- timestamp: 2026-02-16T00:00:04Z
  checked: foreign key references in schema
  found: parent_id (line 21), task_tags.task_id (line 31), task_dependencies (lines 37-38), task_audit.task_id (line 44)
  implication: all FK references use TEXT type, would need schema changes for INTEGER PKs

## Resolution

root_cause: TaskStore.create() at line 115 generates task IDs using `str(uuid.uuid7())`, producing 36-character string IDs. The schema uses TEXT PRIMARY KEY for tasks.id (line 13), with TEXT foreign keys throughout (parent_id, task_tags.task_id, task_dependencies, task_audit.task_id).

fix: N/A (diagnosis only)
verification: N/A (diagnosis only)
files_changed: []
