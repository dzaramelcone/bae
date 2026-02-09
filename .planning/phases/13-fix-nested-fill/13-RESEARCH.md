# Phase 13: Fix Nested Model Construction in Fill - Research

**Researched:** 2026-02-08
**Domain:** Pydantic model_construct vs model_validate for nested BaseModel fields in LLM output
**Confidence:** HIGH

## Summary

The bug is a data flow issue across all three LLM backends (ClaudeCLI, PydanticAI, DSPy). When `fill()` constructs a node instance, nested Pydantic BaseModel fields (e.g., `vibe: VibeCheck`) arrive as raw dicts from the LLM but are never converted to their target model instances. The root cause is `model_construct()` -- which explicitly skips all validation including nested dict-to-model conversion.

The fix involves two changes: (1) stop converting validated nested models back to dicts via `model_dump()`, and (2) use `model_validate()` instead of `model_construct()` for the final node assembly -- or pre-construct nested models before calling `model_construct()`. The official Pydantic docs confirm: "When we say 'no validation is performed' -- this includes converting dictionaries to model instances. So if you have a field referring to a model type, you will need to convert the inner dictionary to a model yourself."

This is a narrow, surgical fix. Three `fill()` methods, one `validate_plain_fields()` helper, and corresponding test updates. No architectural changes needed.

**Primary recommendation:** Change `validate_plain_fields()` to return validated model instances (not `model_dump()` dicts), then use `target.model_validate()` instead of `target.model_construct()` for the final merge in each backend's `fill()`, OR keep `model_construct` but pre-validate nested plain fields so they arrive as model instances.

## Standard Stack

No new libraries needed. This is a fix within the existing stack.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 (>=2.0) | BaseModel, model_validate, model_construct | Already the foundation; the bug is about choosing the right API |

### Key APIs
| API | What It Does | Nested Model Behavior |
|-----|-------------|----------------------|
| `model_construct(**kwargs)` | Creates model without validation | **Does NOT convert nested dicts to models** |
| `model_validate(data)` | Creates model with full validation | **Recursively constructs nested models from dicts** |
| `model_dump()` | Converts model to dict | **Converts nested models back to plain dicts** |

## Architecture Patterns

### Bug Flow (Current - Broken)

All three backends follow the same broken pattern:

```
LLM JSON -> parse to dict -> validate_plain_fields() -> model_dump() -> model_construct()
                                  |                         |                |
                                  v                         v                v
                           VibeCheck instance       back to dict!      stays as dict!
```

**ClaudeCLIBackend.fill()** (lm.py lines 499-530):
```python
# 1. LLM returns: {"vibe": {"mood": "...", "communication_style": "...", "context_cues": "..."}}
data = await self._run_cli_json(prompt, schema)

# 2. validate_plain_fields builds PlainModel, validates (creates VibeCheck), then model_dump() -> dict again!
validated = validate_plain_fields(data, target)
# validated = {"vibe": {"mood": "...", ...}}  <-- DICT, not VibeCheck instance

# 3. model_construct does NOT convert nested dicts to models
all_fields = dict(resolved)
all_fields.update(validated)
return target.model_construct(**all_fields)
# result.vibe is a dict, not VibeCheck
```

**PydanticAIBackend.fill()** (lm.py lines 333-352):
```python
# plain_output is a Pydantic model instance (correct types inside)
# BUT model_dump() converts nested models back to dicts
all_fields.update(plain_output.model_dump())  # <-- converts VibeCheck back to dict
return target.model_construct(**all_fields)   # <-- stays as dict
```

**DSPyBackend.fill()** (dspy_backend.py lines 335-374):
```python
# DSPy returns raw string values, not validated models
for key in result.keys():
    if key not in resolved:
        all_fields[key] = getattr(result, key)  # raw string/dict from DSPy
return target.model_construct(**all_fields)     # <-- never validated as VibeCheck
```

### Fix Pattern: Validate Before Construct

The fix has two independent parts:

#### Part 1: Fix validate_plain_fields() return value

```python
# CURRENT (broken):
def validate_plain_fields(raw, target_cls):
    PlainModel = _build_plain_model(target_cls)
    validated = PlainModel.model_validate(raw)
    return validated.model_dump()  # <-- DESTROYS nested model instances

# FIXED:
def validate_plain_fields(raw, target_cls):
    PlainModel = _build_plain_model(target_cls)
    validated = PlainModel.model_validate(raw)
    # Return dict with model instances preserved, not model_dump()
    return {name: getattr(validated, name) for name in validated.model_fields}
```

#### Part 2: Each backend's fill() final assembly

**Option A: Use model_validate() for final assembly** (simplest, but validates ALL fields including already-validated deps)

```python
all_fields = dict(resolved)
all_fields.update(validated)
return target.model_validate(all_fields)  # recursively constructs nested models
```

**Option B: Keep model_construct() but ensure nested models are already instances** (more surgical)

```python
all_fields = dict(resolved)
all_fields.update(validated)  # validated dict now has VibeCheck instances, not dicts
return target.model_construct(**all_fields)  # safe because nested fields are already models
```

**Recommended: Option B** -- it's consistent with the existing design decision to use `model_construct()` for internal node creation (from STATE.md/ROADMAP.md), and avoids re-validating already-trusted dep values. The fix is in `validate_plain_fields()` which needs to stop calling `model_dump()`.

### Anti-Patterns to Avoid

- **Using model_dump() then model_construct() for nested models:** This is the exact bug. `model_dump()` strips type info; `model_construct()` doesn't restore it.
- **Using model_validate() everywhere:** Would re-validate dep fields that are already resolved. Wastes cycles and could introduce validation errors on fields that should be trusted.
- **Only fixing one backend:** All three backends (ClaudeCLI, PydanticAI, DSPy) have the same bug pattern. Fix all three.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Nested dict-to-model conversion | Manual recursive type walking | `model_validate()` on the PlainModel | Pydantic already handles arbitrary nesting depth, generics, lists of models, etc. |
| Detecting which fields are BaseModel subclasses | `isinstance` checks on field types | Fix the data flow so validated instances aren't destroyed | The bug is in `model_dump()` destroying what `model_validate()` already built correctly |

**Key insight:** Pydantic's `model_validate()` already correctly constructs nested models. The bug is that `validate_plain_fields()` immediately undoes this by calling `model_dump()`. Stop destroying validated instances.

## Common Pitfalls

### Pitfall 1: model_dump() Destroys Nested Model Instances
**What goes wrong:** After `PlainModel.model_validate(raw)` correctly constructs a `VibeCheck` instance, calling `.model_dump()` converts it back to `{"mood": "...", "style": "..."}`.
**Why it happens:** `model_dump()` is designed to produce serializable dicts, not preserve type information.
**How to avoid:** Extract field values with `getattr()` instead of `model_dump()`.
**Warning signs:** Any code path that does `model_validate()` followed by `model_dump()` followed by `model_construct()` has this bug.

### Pitfall 2: DSPy Backend Returns Raw Strings for Nested Fields
**What goes wrong:** DSPy's `Prediction` returns raw strings for output fields. For a nested model field like `vibe`, it returns a JSON string, not a dict or model.
**Why it happens:** DSPy doesn't understand Pydantic model types natively in its output fields.
**How to avoid:** DSPy backend's `fill()` needs to parse and validate the raw values through the PlainModel before constructing the target node.
**Warning signs:** The DSPy backend's `fill()` currently does no validation at all -- it just copies raw prediction values into `model_construct()`.

### Pitfall 3: Forgetting to Update the Existing Test
**What goes wrong:** `test_fill_helpers.py::TestValidatePlainFields::test_nested_model_validated` (line 182) currently asserts `result["vibe"]["mood"] == "happy"` -- i.e., it expects a dict. After the fix, this should assert `isinstance(result["vibe"], VibeCheck)`.
**Why it happens:** The test was written to match the broken behavior.
**How to avoid:** Update the test assertion to match the fixed behavior.

### Pitfall 4: PydanticAI Backend Uses Different Pattern
**What goes wrong:** PydanticAI backend calls `plain_output.model_dump()` directly (not through `validate_plain_fields`), so fixing `validate_plain_fields` alone won't fix PydanticAI.
**Why it happens:** PydanticAI returns a model instance directly (not raw JSON), so it uses a different code path.
**How to avoid:** Fix PydanticAI's `fill()` to use `plain_output.model_fields` iteration or a dict comprehension with `getattr()` instead of `model_dump()`.

### Pitfall 5: test_returns_validated_model_dump Test Name
**What goes wrong:** `test_fill_helpers.py::TestValidatePlainFields::test_returns_validated_model_dump` (line 171) tests that `validate_plain_fields` returns a dict. This test will need updating since the function will still return a dict, but nested values will be model instances rather than sub-dicts.
**How to avoid:** The function still returns a `dict[str, Any]`, just with model instances as values where appropriate. The test for `isinstance(result, dict)` still passes; only nested model assertions change.

## Code Examples

### Fix for validate_plain_fields (lm.py)
```python
# Source: Pydantic docs - model_validate constructs nested models
def validate_plain_fields(raw, target_cls):
    PlainModel = _build_plain_model(target_cls)
    try:
        validated = PlainModel.model_validate(raw)
        # Preserve model instances -- don't model_dump() them back to dicts
        return {name: getattr(validated, name) for name in validated.model_fields}
    except Exception as e:
        raise FillError(...) from e
```

### Fix for ClaudeCLIBackend.fill() (lm.py)
```python
# No change needed IF validate_plain_fields is fixed.
# model_construct now receives VibeCheck instances, not dicts.
validated = validate_plain_fields(data, target)
all_fields = dict(resolved)
all_fields.update(validated)
return target.model_construct(**all_fields)
```

### Fix for PydanticAIBackend.fill() (lm.py)
```python
# Replace model_dump() with getattr-based extraction
all_fields = dict(resolved)
if isinstance(plain_output, BaseModel):
    for name in plain_output.model_fields:
        all_fields[name] = getattr(plain_output, name)
return target.model_construct(**all_fields)
```

### Fix for DSPyBackend.fill() (dspy_backend.py)
```python
# DSPy returns raw strings -- need to validate through PlainModel
from bae.lm import validate_plain_fields

raw_fields = {}
for key in result.keys():
    if key not in resolved:
        raw_fields[key] = getattr(result, key)

validated = validate_plain_fields(raw_fields, target)
all_fields = dict(resolved)
all_fields.update(validated)
return target.model_construct(**all_fields)
```

### Updated Test Assertion
```python
# test_fill_helpers.py - test_nested_model_validated
def test_nested_model_validated(self):
    """Nested BaseModel plain fields are preserved as model instances."""
    from bae.lm import validate_plain_fields

    raw = {"vibe": {"mood": "happy", "style": "casual"}}
    result = validate_plain_fields(raw, MixedNode)

    assert isinstance(result["vibe"], VibeCheck)
    assert result["vibe"].mood == "happy"
    assert result["vibe"].style == "casual"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `model_dump()` then `model_construct()` | Keep validated instances, use `model_construct()` with them | This fix | Nested models preserved correctly |

**The design decision to use model_construct() is still correct.** The issue is that validated data was being destructured back to dicts before being passed to model_construct(). The fix preserves the model instances so model_construct() receives them as-is.

## Scope and Affected Files

| File | Change | Scope |
|------|--------|-------|
| `bae/lm.py` | Fix `validate_plain_fields()`: replace `model_dump()` with `getattr`-based extraction | 1 line |
| `bae/lm.py` | Fix `PydanticAIBackend.fill()`: replace `model_dump()` with `getattr`-based extraction | ~3 lines |
| `bae/dspy_backend.py` | Fix `DSPyBackend.fill()`: add validation through `validate_plain_fields` | ~5 lines |
| `tests/test_fill_helpers.py` | Update `test_nested_model_validated` assertion | ~3 lines |
| `tests/test_fill_helpers.py` | Add new test: nested model instances preserved in validate_plain_fields | new test |
| `tests/test_fill_protocol.py` | Add test: fill() returns nested model instances, not dicts | new test |
| `tests/test_ootd_e2e.py` | Already exists -- `test_anticipate_has_llm_filled_vibe` is the success criterion | no change |

## Open Questions

1. **DSPy output format for nested models**
   - What we know: DSPy `Prediction` returns raw strings for output fields, not structured dicts.
   - What's unclear: Whether DSPy returns valid JSON strings for complex nested fields, or something less structured.
   - Recommendation: Parse through `validate_plain_fields` which calls `model_validate` -- this handles JSON strings, dicts, and nested structures. If DSPy returns a string like `'{"mood": "happy", "style": "casual"}'`, we may need `json.loads()` first. Test with a unit test that simulates DSPy-format output.

2. **Interaction with validate_plain_fields callers**
   - What we know: Only ClaudeCLIBackend calls `validate_plain_fields` directly. PydanticAI and DSPy have their own paths.
   - What's unclear: Whether any other code paths rely on `validate_plain_fields` returning plain dicts.
   - Recommendation: Grep for all callers. The existing tests will catch any regression.

## Sources

### Primary (HIGH confidence)
- Pydantic official docs: https://docs.pydantic.dev/latest/concepts/models/#creating-models-without-validation -- confirms model_construct does NOT convert nested dicts to models
- Pydantic official docs: https://docs.pydantic.dev/latest/concepts/models/#model-methods-and-properties -- confirms model_validate recursively constructs nested models
- Direct codebase analysis: `bae/lm.py`, `bae/dspy_backend.py`, `bae/graph.py` -- traced the exact data flow
- Test analysis: `tests/test_fill_helpers.py`, `tests/test_fill_protocol.py`, `tests/test_ootd_e2e.py`

### Secondary (MEDIUM confidence)
- Pydantic GitHub discussions on model_construct and nested models: https://github.com/pydantic/pydantic/discussions/6536

## Metadata

**Confidence breakdown:**
- Bug root cause: HIGH -- confirmed by Pydantic docs and code trace
- Fix pattern: HIGH -- standard Pydantic usage, no novel approach needed
- Scope: HIGH -- all affected code paths identified through grep + code reading
- DSPy interaction: MEDIUM -- need to verify DSPy output format for nested fields in unit test

**Research date:** 2026-02-08
**Valid until:** indefinite (Pydantic 2.x model_construct behavior is stable and documented)
