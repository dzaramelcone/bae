---
phase: 13-fix-nested-fill
plan: 01
subsystem: lm-fill
tags: [bugfix, pydantic, nested-models, model-construct, tdd]
depends_on:
  requires: ["06", "07", "12"]
  provides: ["nested-model-preservation-in-fill"]
  affects: []
tech-stack:
  added: []
  patterns: ["getattr extraction over model_dump for instance preservation"]
key-files:
  created: []
  modified: ["bae/lm.py", "bae/dspy_backend.py", "tests/test_fill_helpers.py", "tests/test_fill_protocol.py"]
decisions:
  - id: "13-01-01"
    choice: "getattr extraction instead of model_dump() in validate_plain_fields"
    why: "model_dump() recursively serializes nested BaseModel instances to dicts, destroying type information that model_construct needs"
  - id: "13-01-02"
    choice: "DSPy backend validates nested models inline instead of via validate_plain_fields"
    why: "DSPy's fill() has resolved dict containing plain fields (InputFields), so validate_plain_fields rejects partial plain field dicts with missing required fields"
  - id: "13-01-03"
    choice: "Access model_fields on class, not instance"
    why: "Pydantic V2.11 deprecated instance access to model_fields, will be removed in V3.0"
metrics:
  duration: "6m22s"
  completed: "2026-02-09"
  tests_before: 334
  tests_after: 336
  test_delta: +2
---

# Phase 13 Plan 01: Fix Nested Model Construction in Fill -- Summary

**One-liner:** Replace model_dump() with getattr extraction in validate_plain_fields and all three fill() backends to preserve nested BaseModel instances (e.g., VibeCheck) through model_construct.

## What Was Done

### Root Cause

`validate_plain_fields()` called `validated.model_dump()` which recursively serializes nested Pydantic models to plain dicts. When these dicts are passed to `target.model_construct(**all_fields)`, the nested fields become raw dicts instead of proper model instances. Same pattern existed in `PydanticAIBackend.fill()`.

### Fixes Applied

1. **`validate_plain_fields()` in `bae/lm.py`**: Changed `return validated.model_dump()` to `return {name: getattr(validated, name) for name in PlainModel.model_fields}`. This preserves nested BaseModel instances while still extracting validated values.

2. **`PydanticAIBackend.fill()` in `bae/lm.py`**: Changed `all_fields.update(plain_output.model_dump())` to iterate with `getattr()` per field. Same root cause -- model_dump destroying instances.

3. **`DSPyBackend.fill()` in `bae/dspy_backend.py`**: Instead of calling `validate_plain_fields` (which builds a model from ALL plain fields but DSPy only outputs a subset), validates nested BaseModel fields inline using `type.model_validate()` with type hints from the target class.

4. **Pydantic V2.11 deprecation fix**: Changed `validated.model_fields` (instance access) to `PlainModel.model_fields` (class access) to avoid deprecation warning.

## Tests

- Updated `test_nested_model_validated` to assert `isinstance(result["vibe"], VibeCheck)` instead of dict access
- Added `test_nested_model_preserves_instance_type` -- explicit not-dict + isinstance check
- Added `TestFillNestedModelPreservation::test_cli_fill_preserves_nested_model` -- integration test with real ootd models through ClaudeCLIBackend.fill()
- E2E: `test_anticipate_has_llm_filled_vibe` passes (5/5 E2E green)
- Full suite: 336 passed, 10 skipped, 0 failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pydantic V2.11 deprecation on instance model_fields access**

- **Found during:** Task 2
- **Issue:** `validated.model_fields` triggers DeprecationWarning in Pydantic V2.11, will be removed in V3.0
- **Fix:** Changed to `PlainModel.model_fields` (class-level access)
- **Files modified:** bae/lm.py
- **Commit:** 0500c67

**2. [Rule 3 - Blocking] DSPy backend incompatible with validate_plain_fields**

- **Found during:** Task 2
- **Issue:** `validate_plain_fields` builds PlainModel from ALL plain fields of target class, but DSPy's fill() only outputs a subset (OutputFields). Passing partial dict caused ValidationError for missing required fields.
- **Fix:** DSPy backend validates nested models inline using target class type hints and `model_validate()` instead of calling `validate_plain_fields`.
- **Files modified:** bae/dspy_backend.py
- **Commit:** 0500c67

## Commits

| Hash | Message |
|------|---------|
| 48f4d5d | test(13-01): add failing tests for nested model preservation |
| 0500c67 | feat(13-01): fix nested model preservation in all three fill() backends |

## MIG-03 Gap Status

**CLOSED.** The `test_anticipate_has_llm_filled_vibe` E2E test passes. `anticipate.vibe` is a proper `VibeCheck` instance with `mood`, `communication_style`, and `context_cues` attributes.
