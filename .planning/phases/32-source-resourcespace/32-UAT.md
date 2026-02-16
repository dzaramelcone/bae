---
status: diagnosed
phase: 32-source-resourcespace
source: [32-01-SUMMARY.md, 32-02-SUMMARY.md, 32-03-SUMMARY.md, 32-04-SUMMARY.md]
started: 2026-02-16T17:00:00Z
updated: 2026-02-16T17:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Enter source resourcespace
expected: `source()` returns entry display listing subresources (deps, config, tests, meta) and top-level packages with docstring summaries
result: issue
reported: "error messages are confusing. source.config.read() says 'No resource source.config.read'. @source() hyperlinks cause SyntaxError. Navigation path extends indefinitely (home > source > config > source > deps > source > meta) instead of minimum path relative to root (home > source > meta). Each subresource navigation appends to path instead of replacing."
severity: major

### 2. Read package listing at root
expected: `read("")` on SourceResourcespace shows top-level packages (at minimum "bae") with docstring first line and class/function counts
result: issue
reported: "read() not available as bare function in namespace. Entry display shows tools table with read(), glob(), etc. but those are AI tool verbs dispatched through ToolRouter, not callable from REPL. NameError: name 'read' is not defined."
severity: major

### 3. Read module summary
expected: `read("bae.repl.resource")` shows module path, docstring first line, class count, and function count — no raw filesystem paths in output
result: skipped
reason: Blocked by test 2 — read() not in namespace

### 4. Read symbol source via AST
expected: `read("bae.repl.resource.ResourceError")` shows only that class's source code (not the whole file), extracted via AST line ranges
result: skipped
reason: Blocked by test 2 — read() not in namespace

### 5. Path safety rejects traversal
expected: `read("../etc/passwd")` raises ResourceError with clear message. Same for absolute paths like `/etc/passwd` and empty segments like `bae..ai`
result: skipped
reason: Blocked by test 2 — read() not in namespace

### 6. Glob finds modules by pattern
expected: `glob("bae.repl.*")` returns a list of matching module paths in dotted notation (e.g., bae.repl.ai, bae.repl.shell). No filesystem paths (`/`) in output
result: skipped
reason: Blocked by test 2 — glob() not in namespace

### 7. Grep searches source content
expected: `grep("ResourceError", "bae.repl.resource")` returns matches in `bae.repl.resource:NN: line content` format. No filesystem paths in output
result: skipped
reason: Blocked by test 2 — grep() not in namespace

### 8. Navigate to subresource
expected: `source.meta()` via ResourceHandle navigates into the meta subresource. Entry display shows it's scoped to the source resourcespace's own code
result: skipped
reason: Blocked by test 1 — navigation path accumulates

### 9. Deps subresource reads dependencies
expected: Deps subresource `read()` returns project dependencies parsed from pyproject.toml
result: skipped
reason: Blocked by test 2 — read() not in namespace

### 10. Config subresource reads pyproject.toml
expected: Config subresource `read()` lists top-level TOML sections. `read("project")` returns the [project] section content
result: skipped
reason: Blocked by test 2 — read() not in namespace

## Summary

total: 10
passed: 0
issues: 2
pending: 0
skipped: 8

## Gaps

- truth: "source() enters resourcespace; subresource navigation and tool dispatch work correctly"
  status: failed
  reason: "User reported: source.config.read() says 'No resource source.config.read'. @source() hyperlinks cause SyntaxError. Navigation path extends indefinitely (home > source > config > source > deps) instead of minimum path (home > source > deps). Each subresource navigation appends to path instead of replacing."
  severity: major
  test: 1
  root_cause: "ResourceRegistry.navigate() always appends to self._stack. Navigating source.deps after source.config pushes [source, deps] on top of [source, config] making [source, config, source, deps]. Should replace stack from divergence point. Also @resource() hyperlinks aren't valid Python — error messages mislead."
  artifacts:
    - path: "bae/repl/resource.py"
      issue: "navigate() lines 116-138 always append to stack; breadcrumb() just concatenates all stack names"
  missing:
    - "Navigate should replace stack from the common ancestor, not append"
    - "Error messages should use source() not @source() syntax"
  debug_session: ""
- truth: "read() callable from REPL when inside a resourcespace"
  status: failed
  reason: "User reported: read() not available as bare function in namespace. Entry display shows tools table suggesting read(), glob() etc. but NameError: name 'read' is not defined. Tools are AI-only via ToolRouter, not human-usable."
  severity: major
  test: 2
  root_cause: "navigate() returns display string but never injects tool callables into namespace. ResourceRegistry has no reference to namespace. Need: on navigate, assign namespace['read'] = resource.read for each supported tool, remove unsupported ones."
  artifacts:
    - path: "bae/repl/resource.py"
      issue: "ResourceRegistry.navigate() doesn't inject tool functions into namespace"
    - path: "bae/repl/shell.py"
      issue: "CortexShell sets up registry but doesn't pass namespace reference for tool injection"
  missing:
    - "Registry needs namespace reference to inject/remove tool functions on navigation"
    - "On navigate: inject supported tools as bare callables, wrap in NavResult for output"
    - "On homespace/back: remove tool callables or rebind to new current resource"
  debug_session: ""
