---
status: diagnosed
trigger: "Diagnose this UAT issue for phase 32 (Source Resourcespace): homespace() should be renamed to home(). Home should be treated as a resource with its own tools, not just a function that clears everything."
created: 2026-02-16T00:00:00Z
updated: 2026-02-16T00:00:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: homespace() is a navigation function (not a resource) that clears the stack and removes all tools from namespace
test: complete codebase search for all "homespace" references
expecting: comprehensive list of artifacts requiring rename and conceptual shift from "clear stack function" to "home resource"
next_action: return structured diagnosis

## Symptoms

expected: home() should exist as a resource with its own applicable tools (not just clear everything)
actual: homespace() is a lambda that clears stack and removes all tool callables from namespace
errors: none (design issue, not runtime error)
reproduction: navigate to source(), then call homespace() — all tools cleared from namespace
started: since phase 31 implementation (homespace designed as navigation reset, not as a resource)

## Eliminated

None yet (diagnosis phase only)

## Evidence

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/resource.py lines 150-154
  found: ResourceRegistry.homespace() clears stack and calls _root_nav()
  implication: homespace is a registry method, not a Resourcespace protocol implementer

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/resource.py lines 163-171
  found: _put_tools() removes all tool callables when current is None (at root)
  implication: being at home/root means NO tools available, by design

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/shell.py line 233
  found: namespace["homespace"] = lambda wrapping registry.homespace()
  implication: homespace exposed as function, not ResourceHandle

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/resource.py lines 156-161
  found: breadcrumb() always starts with "home" string literal
  implication: "home" is already the conceptual name for root position

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/resource.py lines 173-199 (_root_nav)
  found: nav tree renders with "[bold]home[/bold]" as tree root label
  implication: "home" is already the display name, but function is called "homespace"

- timestamp: 2026-02-16T00:00:00Z
  checked: tests/test_resource.py
  found: test_homespace_clears_stack (127), test_homespace_returns_nav_result (390), test_homespace_removes_tools (438)
  implication: tests explicitly verify that homespace CLEARS tools from namespace

- timestamp: 2026-02-16T00:00:00Z
  checked: grep results for "homespace"
  found: 168 occurrences across 37 files (code, tests, planning docs, prompts)
  implication: extensive renaming required

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/ai_prompt.md line 41
  found: agent instructions use homespace() for navigation
  implication: agent prompt requires update

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/ai.py line 546
  found: "homespace" and "back" in _SKIP set for namespace context
  implication: excluded from namespace dumps

- timestamp: 2026-02-16T00:00:00Z
  checked: .planning/research/FEATURES.md and ARCHITECTURE.md
  found: homespace described as "root resource" and "dashboard" but implemented as navigation reset function
  implication: conceptual mismatch between design vision (home as resource with tools) and implementation (homespace as tool-clearing function)

- timestamp: 2026-02-16T00:00:00Z
  checked: bae/repl/tools.py lines 46-66 (_homespace_dispatch)
  found: ToolRouter has _homespace_dispatch that provides filesystem tools (read, glob, grep) when registry.current is None
  implication: home/root DOES have tools available (filesystem operations), but they're not surfaced as "home resource tools"

## Resolution

root_cause: homespace() is implemented as a navigation reset function (clear stack, remove tools) rather than as a Resourcespace that has its own applicable tools. The design vision was for "home" to be a resource (like source), but the implementation made it a special navigation command. The mismatch: calling homespace() removes tools from namespace, but user expects home to BE a resource with tools (just like source has read/glob/grep).

fix: not applicable (diagnosis only)

verification: not applicable (diagnosis only)

files_changed: []
