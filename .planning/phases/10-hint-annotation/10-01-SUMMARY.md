---
phase: 10
plan: 01
subsystem: lm-protocol
tags: [docstring-removal, prompt-simplification, _build_instruction]
dependency-graph:
  requires: [phase-9]
  provides: [docstrings-inert, class-name-only-instruction]
  affects: [10-02]
tech-stack:
  added: []
  patterns: [class-name-only-instruction]
key-files:
  created: []
  modified: [bae/graph.py, bae/lm.py, tests/test_fill_protocol.py]
decisions:
  - id: "10-01-D1"
    summary: "_build_instruction returns class name only"
    rationale: "Docstrings become developer-only; explicit Field(description=...) replaces implicit docstring extraction"
metrics:
  duration: "~3min"
  completed: "2026-02-08"
---

# Phase 10 Plan 01: Remove Docstring Reading from LLM Prompts Summary

**One-liner:** All __doc__ references removed from LLM-facing code -- class name alone is the instruction, docstrings are inert developer docs.

## What Was Done

### Task 1: TDD - _build_instruction returns class name only (TDD)

**RED:** Updated `test_instruction_is_class_name_plus_docstring` -> `test_instruction_is_class_name_only` in `TestGraphFillIntegration`. Changed assertion from `"Final recommendation." in instruction` to `instruction == "EndNode"`. Added `TestBuildInstruction` class with direct unit tests for `_build_instruction`.

**GREEN:** Simplified `_build_instruction` in `bae/graph.py` from 5 lines (class name + optional docstring append) to a single `return target_type.__name__`. Updated docstrings on `_build_fill_prompt` and `fill()` Protocol to say "class name" instead of "class name + optional docstring".

### Task 2: Remove __doc__ from all LLM prompt builders

Removed 8 `__doc__` references from `bae/lm.py`:

| Backend | Method | What was removed |
|---------|--------|-----------------|
| PydanticAIBackend | `_node_to_prompt` | `if node.__class__.__doc__:` block appending "Context: {docstring}" |
| PydanticAIBackend | `make` | `if target.__doc__:` appending target docstring |
| PydanticAIBackend | `decide` | Loop adding `"- {name}: {docstring}"` for each successor |
| PydanticAIBackend | `choose_type` | Loop adding `"- {name}: {docstring}"` for each type |
| ClaudeCLIBackend | `_node_to_prompt` | `if node.__class__.__doc__:` block appending "Context: {docstring}" |
| ClaudeCLIBackend | `make` | `if target.__doc__:` appending target docstring |
| ClaudeCLIBackend | `decide` | Loop adding `"- {name}: {docstring}"` for each successor |
| ClaudeCLIBackend | `choose_type` | Loop adding `"- {name}: {docstring}"` for each type |

Net: -30 lines of docstring reading code.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `1830a88` | test | Update instruction tests -- expect class name only, no docstring |
| `12ffe45` | feat | _build_instruction returns class name only -- docstrings inert |
| `6f710be` | feat | Remove __doc__ from all LLM prompt builders -- docstrings fully inert |

## Verification

- `grep -rn '__doc__' bae/graph.py bae/lm.py` returns nothing
- `_build_instruction(EndNode)` returns `"EndNode"` (not `"EndNode: Final recommendation."`)
- 323 tests pass, 5 skipped (E2E gated behind --run-e2e)
- Zero regressions from docstring removal

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 10-01-D1 | _build_instruction returns class name only | Docstrings are developer documentation; explicit Field(description=...) (Plan 02) replaces implicit docstring extraction for LLM hints |

## Deviations from Plan

None -- plan executed exactly as written.

## Next Phase Readiness

Plan 10-02 (Field description flow-through) builds directly on this work. With docstrings inert, `Field(description=...)` becomes the only mechanism for per-field LLM hints.
