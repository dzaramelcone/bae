---
phase: 10
plan: 03
subsystem: compiler
tags: [dspy, docstring, instruction, compiler, backend]
dependency-graph:
  requires: [10-01, 10-02]
  provides: ["Zero __doc__ references across all LLM-facing source files"]
  affects: []
tech-stack:
  added: []
  patterns: ["Class name only as DSPy Signature instruction", "No __doc__ in LLM context paths"]
key-files:
  created: []
  modified:
    - bae/compiler.py
    - bae/dspy_backend.py
    - tests/test_signature_v2.py
    - tests/test_optimizer.py
decisions:
  - node_to_signature returns class name only (docstring not appended)
  - choose_type does not include type docstrings in LLM context
metrics:
  duration: ~4min
  completed: 2026-02-08
---

# Phase 10 Plan 03: DSPyBackend __doc__ Removal Summary

**Gap closure plan removing all remaining __doc__ references from DSPyBackend code paths (compiler.py and dspy_backend.py), completing the Phase 10 goal of making docstrings inert across ALL backends.**

## What Was Done

### Task 1: node_to_signature returns class name only (compiler.py)

TDD approach:

- **RED**: Updated `test_docstring_appended_to_instruction` to `test_docstring_ignored_in_instruction`, asserting that a node WITH a docstring still produces `instruction == "AnalyzeUserIntent"` (class name only). Test failed as expected.
- **GREEN**: Removed the 3-line `__doc__` block from `node_to_signature()` (lines 129-132). Instruction is now always `node_cls.__name__` only. Updated comments and docstrings to reflect Phase 10 policy.
- All 3 `TestInstructionFromClassName` tests pass. All 13 `test_compiler.py` tests pass.

**Commit:** `1a77232`

### Task 2: Remove __doc__ from DSPyBackend.choose_type

- Deleted the 4-line docstring loop in `choose_type()` that appended `t.__doc__` to the context string sent to the LLM.
- Updated `fill()` method docstring: `instruction` param described as "Class name for the LLM" instead of "Class name + optional docstring for the LLM."
- Fixed cascading test failure in `test_optimizer.py::test_round_trip_uses_correct_signature_per_node` which asserted old docstring-appended instruction format.

**Commit:** `58fa14b`

## Verification Results

1. `grep -rn '__doc__' bae/compiler.py bae/dspy_backend.py bae/graph.py bae/lm.py` -- zero matches across all 4 LLM-facing files
2. `python -m pytest tests/ -v` -- 323 passed, 5 skipped, 0 failures
3. `python -c "..."` inline test prints "N" (not "N: A docstring") -- confirmed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed stale assertion in test_optimizer.py**

- **Found during:** Task 2
- **Issue:** `test_round_trip_uses_correct_signature_per_node` asserted `expected_sig.__doc__ == "StartNode: A starting node."` which is the old pre-Phase-10 behavior.
- **Fix:** Updated assertion to `"StartNode"` (class name only).
- **Files modified:** `tests/test_optimizer.py`
- **Commit:** `58fa14b`

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Instruction is class name only | Docstrings are developer documentation, not LLM prompts. Users use `Field(description=...)` for per-field hints. |
| Type docstrings not included in choose_type context | Type names are already listed in the choice field desc. If users want type descriptions in LLM context, they should use Field annotations on the type's fields. |

## Phase 10 Completion Status

With this gap closure plan, all three Phase 10 verification gaps are now closed:

- [x] `grep -rn '__doc__' bae/compiler.py` -- zero matches
- [x] `grep -rn '__doc__' bae/dspy_backend.py` -- zero matches
- [x] `node_to_signature()` returns class name only as instruction

All backends (PydanticAI, ClaudeCLI, DSPy) now treat docstrings as inert developer documentation. The explicit `Field(description=...)` pattern is the sole mechanism for per-field LLM hints.
