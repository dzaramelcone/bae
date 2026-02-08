---
phase: 06-node-lm-protocol
plan: 04
subsystem: core
tags: [lm-protocol, choose-type, fill, dspy-backend, pydantic-ai, claude-cli]

# Dependency graph
requires:
  - phase: 06-02
    provides: node_to_signature with is_start parameter and classify_fields
provides:
  - LM Protocol with choose_type() and fill() methods
  - All three backends implement choose_type and fill
  - Clean separation of "pick successor type" from "populate fields"
affects: [07-graph-run-redesign, 08-cleanup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "context-dict-centric LM methods (v2) alongside node-centric (v1)"
    - "model_construct for combined InputField + OutputField instance creation"
    - "Single-type optimization (skip LLM for 1-element candidate lists)"

key-files:
  created:
    - tests/test_lm_protocol.py
  modified:
    - bae/lm.py
    - bae/dspy_backend.py

key-decisions:
  - "choose_type/fill take context dict, not node instance -- decoupled from v1 node-centric pattern"
  - "Single-type lists skip LLM call entirely (optimization on all backends)"
  - "DSPyBackend.fill uses model_construct to merge context + LM output fields"
  - "PydanticAIBackend.fill delegates to pydantic-ai agent with target output type"
  - "ClaudeCLIBackend.fill uses _run_cli with target's model_json_schema"
  - "Kept _predict_choice separate from choose_type -- different semantics (v1 vs v2)"

metrics:
  duration: ~8min
  completed: 2026-02-08
---

# Phase 6 Plan 4: LM Protocol choose_type/fill Summary

Added choose_type() and fill() to the LM Protocol and implemented them on DSPyBackend, PydanticAIBackend, and ClaudeCLIBackend, with model_construct-based instance creation for the DSPy path.

## What Was Done

### LM Protocol (bae/lm.py)
- Added `choose_type(types, context) -> type[Node]` to Protocol
- Added `fill(target, context, instruction) -> T` to Protocol
- Existing `make` and `decide` preserved for backward compatibility

### DSPyBackend (bae/dspy_backend.py)
- `choose_type`: Single-type optimization (returns directly), multi-type uses dspy.Predict with choice signature, format_as_xml context, partial/case-insensitive fallback matching
- `fill`: Uses `node_to_signature(target, is_start=False)` for signature, passes context as InputField values, extracts OutputField values from prediction, merges both via `model_construct`

### PydanticAIBackend (bae/lm.py)
- `choose_type`: Single-type optimization, multi-type asks string-output agent to pick type name, maps back with fallbacks
- `fill`: Uses pydantic-ai agent with target as output type, returns agent output directly

### ClaudeCLIBackend (bae/lm.py)
- `choose_type`: Single-type optimization, multi-type uses CLI with choice enum schema, maps name back to type
- `fill`: Formats context as XML, passes target's JSON schema to CLI, returns model_validate result

### Tests (tests/test_lm_protocol.py)
- 18 tests total: protocol shape (4), DSPyBackend choose_type (3), DSPyBackend fill (4), PydanticAIBackend choose_type (2), PydanticAIBackend fill (1), ClaudeCLIBackend choose_type (2), ClaudeCLIBackend fill (2)
- All mock-based (no real LLM calls)

## Decisions Made

1. **Context dict over node instance**: choose_type/fill take `dict[str, object]` not `Node`. This cleanly separates the v2 runtime (which resolves deps/recalls into a dict) from the v1 pattern (which passes the node itself).

2. **Single-type optimization on all backends**: When `types` has exactly one element, return it immediately without any LLM call. Terminal detection is the graph's job, not the LM's.

3. **model_construct for DSPyBackend.fill**: Merges context dict (InputField values) with LM prediction (OutputField values) into a single instance. Uses `model_construct` to bypass validation since the values come from trusted sources (resolver + LLM).

4. **No shared helper between _predict_choice and choose_type**: Despite similar logic, they serve different purposes (v1 node-centric with is_terminal vs v2 context-dict without terminal handling). Extracting a shared helper would create an awkward abstraction that Phase 8 cleanup would need to undo.

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- `tests/test_lm_protocol.py`: 18 passed
- `tests/test_dspy_backend.py`: 15 passed (existing, unchanged)
- Full suite: 291 passed, 5 skipped

## Commits

| Hash | Message |
|------|---------|
| fd30b64 | test(06-04): add failing tests for LM Protocol choose_type and fill |
| d998c81 | feat(06-04): implement choose_type and fill on all LM backends |

## Next Phase Readiness

Phase 6 Plan 5 (06-05) can proceed. All v2 LM Protocol methods are in place. The graph run redesign (Phase 7) can now use `choose_type` + `fill` in its runtime loop.
