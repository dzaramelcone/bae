---
phase: 32-source-resourcespace
plan: 03
subsystem: repl
tags: [resourcespace, ast, source-editing, hot-reload, symbol-replacement]

# Dependency graph
requires:
  - phase: 32-source-resourcespace
    plan: 01
    provides: "SourceResourcespace foundation, path resolution, AST symbol extraction"
provides:
  - "write() for creating new modules with syntax validation and __init__.py update"
  - "edit() for AST-based symbol replacement by dotted name"
  - "undo() via git checkout for reverting uncommitted changes"
  - "_hot_reload() with automatic rollback on reload failure"
affects: [32-04]

# Tech tracking
tech-stack:
  added: []
  patterns: [symbol-level-editing, hot-reload-with-rollback, ast-indent-adjustment]

key-files:
  created: []
  modified:
    - bae/repl/source.py
    - tests/test_source.py

key-decisions:
  - "_replace_symbol auto-adjusts indentation via textwrap.dedent + col_offset re-indent"
  - "Hot-reload failure is non-fatal for write() (new module) but fatal for edit() (triggers rollback)"
  - "undo() uses git checkout -- . scoped to project root, reverting all uncommitted changes"
  - "_find_symbol walks AST iter_child_nodes for ClassDef/FunctionDef/AsyncFunctionDef by name"

patterns-established:
  - "_replace_symbol validates both standalone new_source and full resulting module via ast.parse"
  - "_hot_reload writes old_source back on any import/reload exception"
  - "write() appends 'from pkg.mod import *' to parent __init__.py"

# Metrics
duration: 4min
completed: 2026-02-16
---

# Phase 32 Plan 03: Write/Edit/Undo with Hot-Reload Summary

**AST-based symbol editing with indentation adjustment, syntax validation before disk write, importlib hot-reload with automatic rollback, and git-based undo**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-16T16:33:41Z
- **Completed:** 2026-02-16T16:37:56Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- write() creates modules with ast.parse validation and auto-updates parent __init__.py
- edit() replaces symbols by dotted name via AST line ranges with automatic indentation adjustment
- Hot-reload via importlib.reload() after every write/edit; failed reload triggers automatic rollback
- undo() reverts all uncommitted changes via git checkout
- 11 new tests covering write/edit/undo/reload/rollback operations

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Tests for write, edit, hot-reload, rollback, and undo** - `3aa2dbe` (test)
2. **Task 2: GREEN -- Implement write, edit, undo, and hot-reload** - `bec7520` (feat, co-committed with 32-02 by parallel agent)

## Files Created/Modified
- `bae/repl/source.py` - Added _find_symbol, _replace_symbol, _hot_reload helpers; write(), edit(), undo() methods
- `tests/test_source.py` - 11 new tests: 3 write, 4 edit, 2 hot-reload/rollback, 2 undo

## Decisions Made
- _replace_symbol auto-adjusts indentation: dedents new_source to 0 then re-indents to target's col_offset
- Hot-reload failure is non-fatal for write() (new files may not be importable yet) but fatal for edit() (existing code must stay valid)
- undo() uses `git checkout -- .` scoped to project root -- simple and covers all file changes
- _find_symbol reuses the same AST walking pattern as _read_symbol for consistency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Adjusted rollback test for reload semantics**
- **Found during:** Task 2
- **Issue:** Original test plan had edit introducing `import nonexistent_module` inside a function body, which doesn't fail on reload (only on call)
- **Fix:** Changed test to use _hot_reload helper directly with a top-level bad import that fails on module reload
- **Files modified:** tests/test_source.py
- **Verification:** Test correctly validates rollback behavior
- **Committed in:** 3aa2dbe (adjusted during RED phase)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test accurately validates reload/rollback semantics. No scope creep.

## Issues Encountered
- Task 2 implementation was co-committed with plan 32-02 by a parallel agent (both modified same files). Implementation is correct and committed, just under a combined commit hash.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SourceResourcespace now has full CRUD: read (32-01), glob/grep (32-02), write/edit/undo (32-03)
- Ready for Plan 04: subresource implementations (meta, deps, config, tests)
- Full test suite passes: 748 passed, 5 skipped

---
*Phase: 32-source-resourcespace*
*Completed: 2026-02-16*
