# Phase 33: Task Resourcespace - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Persistent task CRUD with FTS search and cross-session persistence, navigable as a resourcespace. Tasks are structured documents with assumptions, research, acceptance criteria, and retrospectives. SQLite-backed with heap-ordered priority.

</domain>

<decisions>
## Implementation Decisions

### Task structure
- Fields: title, frontmatter (metadata), status, priority, tags, markdown body
- Priority uses semver-style tuple (major.minor.patch) for heapq ordering
- Tags are free-form strings with light friction for new tag creation; support AND/OR filtering semantics
- Track creator attribution (agent vs user)
- Created/updated timestamps

### Major/minor task hierarchy
- Major versions (e.g., 1.0.0): full structured form, all sections enforced on creation
- Minor versions (e.g., 1.1.0): subtasks pointing to parent major, just title + own acceptance criteria
- Minor tasks complete independently; major task requires its own verification step even when all minors are done
- Priority IS the hierarchy — semver encodes parent-child relationship

### Structured sections (major tasks)
- On creation (enforced):
  - `<assumptions>` with `<claim risk="low|med|high">explanation</claim>`
  - `<reasoning/>` — rationale for the task
  - `<background_research>` with `<finding claim=".." source=".." verified="true|false"/>`
  - `<acceptance_criteria/>` — what must be true for completion
- On completion:
  - `<outcome/>` — what actually happened
  - `<confidence/>` — how confident in the result
  - `<retrospective/>` — what was learned

### Task lifecycle
- Five states: Open / In Progress / Blocked / Done / Cancelled
- Completion is final — done tasks cannot be reopened (create new task instead)
- Done and Cancelled are both soft-delete (hidden from default view, never hard-deleted)
- Dependencies supported — task B can be blocked by task A, entering Blocked state
- Status transitions logged (audit trail: when changed, by whom)
- No resolution note required on completion

### Verification
- Default: agent self-checks acceptance criteria before marking done
- Optional user gate: if user marks a task as user-gated, agent self-checks then asks user to confirm
- Major tasks always require verification even when all minor subtasks are complete

### Listing & display
- Default view: In Progress + Blocked at top, then Open tasks ordered by priority heap
- Done/Cancelled hidden from default view
- Each row shows: status, priority, title, tags (one line per task)
- Filtering supported via tool params: filter by tag, status, priority
- FTS search via .search()

### Session surfacing
- Tasks do NOT surface on session start — only visible when navigating to tasks()
- No auto-resume of in-progress tasks
- Stale task detection is time-based (no activity for N days)

### Claude's Discretion
- SQLite schema design
- FTS5 configuration
- Exact display formatting and truncation
- How tag friction works (e.g., confirm new tag, suggest existing)
- Staleness threshold (N days)

</decisions>

<specifics>
## Specific Ideas

- Priority as semver enables heapq: `(1, 0, 0)` sorts naturally, hierarchy is encoded in the version scheme
- Resource errors should include few-shot examples to guide correct usage (general pattern, not task-specific)
- The structured sections (assumptions, research, criteria) are inspired by rigorous task management — each task is a mini research document

</specifics>

<deferred>
## Deferred Ideas

- Alarming/scheduling as a separate resource — stale task alarms, periodic checks, timer-based triggers
- Remove namespace object (`ns`) entirely — everything becomes a resource. Impacts Phase 34+ (memory, search, discovery)
- Memory resourcespace (store/session as navigable resource) — stays as Phase 34
- Background process for proactive stale task notification — discuss when alarm resource is scoped

</deferred>

---

*Phase: 33-task-resourcespace*
*Context gathered: 2026-02-16*
