# Phase 10 Plan 02: Field Description Preservation Summary

**One-liner:** _build_plain_model preserves FieldInfo so Field(description=...) flows into JSON schemas for constrained decoding

## What Was Done

### Task 1: TDD - _build_plain_model preserves Field descriptions (RED/GREEN)

**RED:** Added `TestPlainModelDescriptions` test class with 4 tests:
- `test_plain_model_preserves_field_description` — description survives dynamic model
- `test_plain_model_description_in_json_schema` — transform_schema includes descriptions
- `test_plain_model_no_description_field_works` — None description preserved
- `test_plain_model_default_preserved_with_description` — default_factory survives

3 of 4 tests failed (as expected — current code lost descriptions).

**GREEN:** Changed `_build_plain_model` to pass `(type, FieldInfo)` tuples to `create_model()` instead of `(type, default)`. This one-line change preserves description, default, default_factory, json_schema_extra, and all other field metadata through the dynamic model.

Old code:
```python
if field_info.default is not None:
    plain_fields[name] = (base_type, field_info.default)
else:
    plain_fields[name] = (base_type, ...)
```

New code:
```python
plain_fields[name] = (base_type, field_info)
```

All 323 tests pass. Zero regressions.

### Task 2: Add Field(description=...) to RecommendOOTD

Updated all 6 plain fields on RecommendOOTD with `Field(description=...)`:
- `top`: "a specific garment for the upper body"
- `bottom`: "a specific garment for the lower body"
- `footwear`: "specific shoes or boots"
- `accessories`: "jewelry, bags, hats, scarves, etc."
- `final_response`: "casual message to the user with the recommendation"
- `inspo`: "outfit inspiration image URLs"

Added `Field` to pydantic import line.

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| 289faf3 | test | add failing tests for Field description preservation in _build_plain_model |
| bd9c3b5 | feat | _build_plain_model preserves FieldInfo — descriptions survive into JSON schema |
| 66d8c5c | feat | add Field(description=...) to RecommendOOTD — explicit per-field LLM context |

## Files Modified

| File | Changes |
|------|---------|
| `bae/lm.py` | _build_plain_model passes (type, FieldInfo) to create_model |
| `examples/ootd.py` | RecommendOOTD: 6 fields with Field(description=...), added Field import |
| `tests/test_fill_helpers.py` | Added TestPlainModelDescriptions (4 tests), added Field import |

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Pass FieldInfo object directly to create_model | Simplest approach — Pydantic natively accepts (type, FieldInfo) tuples, preserving all metadata. No need to manually copy individual fields. |
| Only add descriptions to RecommendOOTD | Start node fields are caller-provided (not LLM-filled), and AnticipateUsersDay fields are mostly deps. RecommendOOTD is the terminal LLM-filled node where descriptions matter most. |

## Deviations from Plan

None — plan executed exactly as written.

## Test Results

- **Before:** 319 passed, 5 skipped
- **After:** 323 passed, 5 skipped (+4 new tests)
- **No regressions** in existing TestBuildPlainModel or TestValidatePlainFields

## Verification

- `transform_schema(plain_model)` output includes `"description": "a specific garment for the upper body"` for described fields
- `grep 'Field(description=' examples/ootd.py` shows 6 matches
- Graph still parses: `Graph nodes: 3`
- Full test suite: 323 passed, 5 skipped

## Duration

~7 minutes
