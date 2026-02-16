---
status: resolved
trigger: "read() at the root of SourceResourcespace shows '0 classes, 0 functions' for all packages including 'bae'. The counts only reflect what's in `__init__.py`, not the package's submodules."
created: 2026-02-16T00:00:00Z
updated: 2026-02-16T00:00:00Z
---

## Current Focus

hypothesis: _module_summary() counts only classes/functions in the direct file (package's __init__.py), not submodules
test: examining _module_summary implementation and how read("") calls it
expecting: confirmation that AST parsing only looks at __init__.py content
next_action: trace through read("") -> _module_summary() call chain

## Symptoms

expected: Package listing via read() should show meaningful counts that reflect package contents (submodules)
actual: Shows "0 classes, 0 functions" for packages like "bae" whose __init__.py is mostly empty
errors: (none - wrong behavior, not an error)
reproduction: Call src.read("") at root - observe package summaries
started: Reported in UAT for phase 32

## Eliminated

(none yet)

## Evidence

- timestamp: 2026-02-16T00:00:00Z
  checked: source.py lines 553-563 - read("") implementation
  found: read("") iterates _discover_packages() and calls _module_summary() for each
  implication: Package counts come from _module_summary()

- timestamp: 2026-02-16T00:00:00Z
  checked: source.py lines 59-76 - _module_summary() implementation
  found: _module_summary() calls _module_to_path() which returns __init__.py for packages, then parses that single file's AST
  implication: Only counts classes/functions in __init__.py, doesn't recurse into submodules

- timestamp: 2026-02-16T00:00:00Z
  checked: source.py lines 68-74 - AST parsing logic
  found: Uses ast.iter_child_nodes(tree) which only iterates direct children, not descendants
  implication: Even if we wanted to count submodules, this wouldn't traverse deeper

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/__init__.py actual content
  found: Only imports and __all__, no classes or functions defined
  implication: Confirms why "bae" shows "0 classes, 0 functions"

- timestamp: 2026-02-16T00:00:00Z
  checked: tests/test_source.py line 104-107
  found: test_read_root_lists_packages only checks "bae" appears, doesn't validate counts
  implication: Test doesn't catch this issue - missing assertion on meaningful counts

## Resolution

root_cause: _module_summary() (lines 59-76) counts classes/functions only in the package's __init__.py file by parsing its AST. For packages like "bae" whose __init__.py contains only imports, this shows "0 classes, 0 functions" even though the package has many submodules with classes/functions.
fix: (diagnosis only - no fix applied)
verification: (diagnosis only)
files_changed: []
