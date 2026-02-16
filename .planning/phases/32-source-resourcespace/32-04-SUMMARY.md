---
phase: 32-source-resourcespace
plan: 04
subsystem: repl
tags: [resourcespace, subresources, pyproject-toml, tomllib, tomlkit, test-discovery]

# Dependency graph
requires:
  - phase: 32-source-resourcespace
    plan: 01
    provides: "SourceResourcespace, _StubSubresource, path resolution, AST helpers"
  - phase: 32-source-resourcespace
    plan: 03
    provides: "write/edit/_hot_reload/_replace_symbol for MetaSubresource.edit"
provides:
  - "DepsSubresource: read/write project dependencies via tomllib + uv"
  - "ConfigSubresource: read pyproject.toml sections as JSON"
  - "TestsSubresource: discover and read test modules, grep test content"
  - "MetaSubresource: introspect/edit source.py via AST"
  - "SourceResourcespace registered in CortexShell with source() handle"
affects: []

# Tech tracking
tech-stack:
  added: [tomlkit]
  patterns: [subresource-per-domain, tomllib-read-tomlkit-write, test-module-discovery]

key-files:
  created: []
  modified:
    - bae/repl/source.py
    - bae/repl/shell.py
    - tests/test_source.py

key-decisions:
  - "Subresource classes are module-level (not inner classes) for importability and testability"
  - "ConfigSubresource.read() returns JSON serialization of TOML sections"
  - "TestsSubresource discovers test_*.py and conftest.py under tests/ directory"
  - "MetaSubresource scoped to bae.repl.source module for self-introspection"
  - "tomlkit added for future style-preserving TOML writes in DepsSubresource"

patterns-established:
  - "Each subresource owns a project_root Path and reads pyproject.toml or filesystem independently"
  - "DepsSubresource.write() delegates to uv add subprocess"
  - "MetaSubresource.edit() reuses _replace_symbol and _hot_reload from parent module"

# Metrics
duration: 2min
completed: 2026-02-16
---

# Phase 32 Plan 04: Subresources and Shell Registration Summary

**Four domain subresources (deps, config, tests, meta) replacing stubs, SourceResourcespace registered in CortexShell with source() namespace handle and tomlkit dependency**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-16T16:40:23Z
- **Completed:** 2026-02-16T16:43:09Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Four subresource classes replace stubs: DepsSubresource, ConfigSubresource, TestsSubresource, MetaSubresource
- SourceResourcespace registered in CortexShell; source() in namespace navigates to it
- source.meta() navigates to meta subresource via dotted ResourceHandle access
- tomlkit dependency added for style-preserving TOML writes
- 18 new tests covering all subresource operations and shell registration

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement four subresources replacing stubs** - `9de6b17` (feat)
2. **Task 2: Register SourceResourcespace in CortexShell** - `8e9399d` (feat)

## Files Created/Modified
- `bae/repl/source.py` - Four subresource classes (DepsSubresource, ConfigSubresource, TestsSubresource, MetaSubresource) replacing _StubSubresource; added tomllib import
- `bae/repl/shell.py` - Import SourceResourcespace, register in CortexShell.__init__, create source ResourceHandle
- `tests/test_source.py` - 18 new tests for subresource read/enter/nav/supported_tools and shell registration
- `pyproject.toml` - Added tomlkit dependency

## Decisions Made
- Subresource classes are module-level (not inner classes) for clean imports and testability
- ConfigSubresource serializes TOML sections to JSON for display (json.dumps with indent)
- TestsSubresource discovers test_*.py and conftest.py under tests/ (not all .py files)
- MetaSubresource hardcodes bae.repl.source as its module path for self-introspection
- Tests access subresources via src.children()["name"] to avoid pytest collection warnings from importing TestsSubresource

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MetaSubresource.read("SourceResourcespace") exceeds CHAR_CAP**
- **Found during:** Task 1
- **Issue:** Test for read("SourceResourcespace") failed because SourceResourcespace class is 9365 chars, exceeding 2000 CHAR_CAP
- **Fix:** Changed test to read("DepsSubresource") which fits within cap
- **Files modified:** tests/test_source.py
- **Verification:** All tests pass
- **Committed in:** 9de6b17 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test adjusted to use smaller symbol. No scope creep.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 32 (Source Resourcespace) is complete
- Full CRUD surface: read (32-01), glob/grep (32-02), write/edit/undo (32-03), subresources + registration (32-04)
- Agent can call source() in REPL and navigate the full source resource tree
- Full test suite passes: 767 passed, 5 skipped

---
*Phase: 32-source-resourcespace*
*Completed: 2026-02-16*
