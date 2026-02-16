---
status: diagnosed
phase: 32-source-resourcespace
source: [32-01-SUMMARY.md, 32-02-SUMMARY.md, 32-03-SUMMARY.md, 32-04-SUMMARY.md, 32-05-SUMMARY.md]
started: 2026-02-16T23:10:00Z
updated: 2026-02-16T23:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Enter source resourcespace
expected: `source()` returns entry display listing subresources (deps, config, tests, meta) and top-level packages with docstring summaries. Uses callable syntax (source.meta() not @source.meta()).
result: pass

### 2. Tool callables available after navigate
expected: After `source()`, `read` is a callable in the namespace. Typing `read` shows it's a bound method, not NameError.
result: pass

### 3. Read package listing at root
expected: `read()` (bare callable) on SourceResourcespace shows top-level packages (at minimum "bae") with docstring first line and class/function counts
result: issue
reported: "0 classes, 0 functions for all packages including bae. Counts only reflect __init__.py, not submodules."
severity: minor

### 4. Read module summary
expected: `read("bae.repl.resource")` shows module path, docstring first line, class count, and function count — no raw filesystem paths in output
result: pass

### 5. Read symbol source via AST
expected: `read("bae.repl.resource.ResourceError")` shows only that class's source code (not the whole file), extracted via AST line ranges
result: pass

### 6. Path safety rejects traversal
expected: `read("../etc/passwd")` raises ResourceError with clear message. Same for absolute paths like `/etc/passwd` and empty segments like `bae..ai`
result: pass

### 7. Glob finds modules by pattern
expected: `glob("bae.repl.*")` returns a list of matching module paths in dotted notation (e.g., bae.repl.ai, bae.repl.shell). No filesystem paths (`/`) in output
result: pass

### 8. Grep searches source content
expected: `grep("ResourceError", "bae.repl.resource")` returns matches in `bae.repl.resource:NN: line content` format. No filesystem paths in output
result: pass

### 9. Navigate to subresource
expected: `source.meta()` navigates into meta subresource. Entry display shows it's scoped to source resourcespace's own code
result: pass

### 10. Sibling navigation breadcrumb
expected: Navigate `source.config()` then `source.deps()` — breadcrumb shows "home > source > deps", NOT "home > source > config > source > deps"
result: pass

### 11. Homespace removes tool callables
expected: After `homespace()`, typing `read` produces NameError — tool callables removed from namespace
result: issue
reported: "homespace() should be home(). Home is a resource — it should have its own tools, not just clear everything."
severity: major

## Summary

total: 11
passed: 9
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "Package listing shows accurate class/function counts reflecting submodule contents"
  status: failed
  reason: "User reported: 0 classes, 0 functions for all packages including bae. Counts only reflect __init__.py, not submodules."
  severity: minor
  test: 3
  root_cause: "_module_summary() (source.py:59-76) parses only __init__.py AST, not submodule contents. Packages have 0 classes/functions in __init__.py despite having many in submodules."
  artifacts:
    - path: "bae/repl/source.py"
      issue: "_module_summary() counts only __init__.py top-level nodes, not package contents"
  missing:
    - "Detect package vs module in _module_summary and show submodule count instead of class/function count"
    - "e.g., 'bae -- Bae: Type-driven agent graphs. (2 subpackages, 14 modules)'"
  debug_session: ".planning/debug/package-counts-zero.md"
- truth: "home() is a resource with its own tools; homespace() renamed to home()"
  status: failed
  reason: "User reported: homespace() should be home(). Home is a resource — it should have its own tools, not just clear everything."
  severity: major
  test: 11
  root_cause: "homespace() is a navigation reset (clear stack + remove tools), not a Resourcespace. registry.current is None at root, so _put_tools clears everything. Rename to home() and make it a resource."
  artifacts:
    - path: "bae/repl/resource.py"
      issue: "homespace() clears stack; _put_tools removes all tools when current is None"
    - path: "bae/repl/shell.py"
      issue: "namespace['homespace'] is a lambda, not a ResourceHandle"
    - path: "bae/repl/tools.py"
      issue: "_homespace_dispatch needs renaming"
    - path: "bae/repl/ai.py"
      issue: "'homespace' in _SKIP set"
    - path: "bae/repl/ai_prompt.md"
      issue: "Agent instructions reference homespace()"
  missing:
    - "Rename homespace() to home() across all code, tests, and docs"
    - "Make home a resource (HomeResourcespace or treat root as current resource)"
    - "namespace['home'] as ResourceHandle, not lambda"
    - "At home, registry.current should not be None — home has tools (nav, read for dashboard)"
  debug_session: ".planning/debug/homespace-rename-to-home.md"
