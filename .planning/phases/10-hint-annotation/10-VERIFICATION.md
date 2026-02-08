---
phase: 10-hint-annotation
verified: 2026-02-08T19:20:39Z
status: gaps_found
score: 5/8 must-haves verified
gaps:
  - truth: "_build_instruction() returns class name only — __doc__ is NOT read"
    status: verified
    reason: "Correctly returns only target_type.__name__"
  - truth: "_node_to_prompt() on both backends does NOT read __doc__"
    status: verified
    reason: "PydanticAIBackend and ClaudeCLIBackend verified clean"
  - truth: "v1 make() on both backends does NOT read target.__doc__"
    status: failed
    reason: "DSPyBackend.make() calls node_to_signature() which READS __doc__"
    artifacts:
      - path: "bae/compiler.py"
        issue: "Lines 131-132: instruction += f': {node_cls.__doc__.strip()}'"
      - path: "bae/dspy_backend.py"
        issue: "Line 146: signature = node_to_signature(target) — calls compiler with docstring"
    missing:
      - "Remove __doc__ reading from node_to_signature in compiler.py"
      - "Update node_to_signature to return only class name as instruction"
  - truth: "v1 decide() on both backends does NOT read t.__doc__"
    status: verified
    reason: "PydanticAIBackend and ClaudeCLIBackend verified clean"
  - truth: "v1 choose_type() on both backends does NOT read t.__doc__"
    status: failed
    reason: "DSPyBackend.choose_type() appends docstrings to context"
    artifacts:
      - path: "bae/dspy_backend.py"
        issue: "Lines 323-324: if t.__doc__: context_str += f'\\n- {t.__name__}: {t.__doc__}'"
    missing:
      - "Remove docstring loop from DSPyBackend.choose_type()"
  - truth: "Docstrings on Node subclasses are NOT automatically included in LLM prompts"
    status: failed
    reason: "DSPyBackend (the DEFAULT backend) still reads docstrings in 2 locations"
    artifacts:
      - path: "bae/dspy_backend.py"
        issue: "choose_type() method reads __doc__"
      - path: "bae/compiler.py"
        issue: "node_to_signature() reads __doc__"
    missing:
      - "Complete docstring removal from DSPyBackend code path"
  - truth: "_build_plain_model() preserves Field(description=...) in the dynamic model"
    status: verified
    reason: "Passes (type, FieldInfo) tuples to create_model, preserving all metadata"
  - truth: "transform_schema() output from the plain model includes description strings"
    status: verified
    reason: "Verified programmatically — descriptions flow through correctly"
  - truth: "examples/ootd.py RecommendOOTD fields use Field(description=...) where helpful"
    status: verified
    reason: "All 6 plain fields have Field(description=...) annotations"
---

# Phase 10: Field Descriptions & Docstring Removal Verification Report

**Phase Goal:** Make docstrings inert and use Field(description=...) for explicit per-field LLM context
**Verified:** 2026-02-08T19:20:39Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                        | Status      | Evidence                                                                                      |
| --- | ---------------------------------------------------------------------------- | ----------- | --------------------------------------------------------------------------------------------- |
| 1   | `_build_instruction()` returns class name only — `__doc__` is NOT read      | ✓ VERIFIED  | Line 52: `return target_type.__name__`                                                        |
| 2   | `_node_to_prompt()` on both backends does NOT read `__doc__`                | ✓ VERIFIED  | PydanticAIBackend (line 262) and ClaudeCLIBackend (line 385) verified clean                  |
| 3   | v1 make() on both backends does NOT read target.`__doc__`                   | ✗ FAILED    | DSPyBackend.make() → node_to_signature() → reads `__doc__` at compiler.py:131-132            |
| 4   | v1 decide() on both backends does NOT read t.`__doc__`                      | ✓ VERIFIED  | PydanticAIBackend and ClaudeCLIBackend verified clean; DSPyBackend doesn't have decide()     |
| 5   | v1 choose_type() on both backends does NOT read t.`__doc__`                 | ✗ FAILED    | DSPyBackend.choose_type() reads `__doc__` at line 323-324                                    |
| 6   | Docstrings on Node subclasses are NOT automatically included in LLM prompts | ✗ FAILED    | DSPyBackend (the DEFAULT backend) still includes docstrings via compiler + choose_type paths |
| 7   | `_build_plain_model()` preserves `Field(description=...)` in dynamic model   | ✓ VERIFIED  | Line 61: `plain_fields[name] = (base_type, field_info)`                                      |
| 8   | `transform_schema()` output includes description strings                    | ✓ VERIFIED  | Programmatically verified: RecommendOOTD.top description flows through                       |

**Score:** 5/8 truths verified

### Required Artifacts

| Artifact                            | Expected                                      | Status       | Details                                                                                        |
| ----------------------------------- | --------------------------------------------- | ------------ | ---------------------------------------------------------------------------------------------- |
| `bae/graph.py`                      | _build_instruction returns class name only   | ✓ VERIFIED   | Line 52: Returns only `target_type.__name__`                                                   |
| `bae/lm.py` (PydanticAI)            | _node_to_prompt without docstring reading    | ✓ VERIFIED   | No `__doc__` references found                                                                  |
| `bae/lm.py` (ClaudeCLI)             | _node_to_prompt without docstring reading    | ✓ VERIFIED   | No `__doc__` references found                                                                  |
| `bae/dspy_backend.py`               | choose_type without docstring reading        | ✗ FAILED     | Lines 323-324 still read `t.__doc__`                                                           |
| `bae/compiler.py`                   | node_to_signature without docstring reading  | ✗ FAILED     | Lines 131-132 append `node_cls.__doc__` to instruction                                         |
| `bae/lm.py` (_build_plain_model)    | FieldInfo preservation                       | ✓ VERIFIED   | Line 61 passes FieldInfo to create_model                                                       |
| `examples/ootd.py` (RecommendOOTD)  | Field(description=...) annotations           | ✓ VERIFIED   | 6 fields with descriptions (top, bottom, footwear, accessories, final_response, inspo)        |
| `tests/test_fill_protocol.py`      | Updated tests for class name only            | ✓ VERIFIED   | test_instruction_is_class_name_only + TestBuildInstruction unit tests                         |
| `tests/test_fill_helpers.py`       | Tests for description preservation           | ✓ VERIFIED   | TestPlainModelDescriptions class with 4 tests                                                  |

### Key Link Verification

| From                                    | To                      | Via                                                  | Status      | Details                                                                               |
| --------------------------------------- | ----------------------- | ---------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------- |
| `bae/graph.py` (_build_instruction)     | `bae/lm.py`             | fill() instruction param                             | ✓ WIRED     | PydanticAI/ClaudeCLI backends use _build_instruction correctly                        |
| `bae/compiler.py` (node_to_signature)   | `bae/dspy_backend.py`   | DSPyBackend.make() calls node_to_signature           | ⚠️ BROKEN   | Wired but transmits docstrings — defeats phase goal                                   |
| `bae/lm.py` (_build_plain_model)        | `anthropic` package     | transform_schema(plain_model)                        | ✓ WIRED     | Verified: descriptions flow through to JSON schema                                    |
| `examples/ootd.py` (RecommendOOTD)      | `bae/lm.py`             | _build_plain_model preserves Field descriptions      | ✓ WIRED     | Field descriptions survive into JSON schema for constrained decoding                  |
| `bae/dspy_backend.py` (choose_type)     | LLM prompt              | Appends type.__doc__ to context_str                  | ⚠️ BROKEN   | Still transmits docstrings — defeats phase goal                                       |

### Requirements Coverage

N/A — No requirements explicitly mapped to Phase 10 in REQUIREMENTS.md.

### Anti-Patterns Found

| File                  | Line     | Pattern                                                    | Severity   | Impact                                                                        |
| --------------------- | -------- | ---------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------- |
| `bae/compiler.py`     | 131-132  | `if node_cls.__doc__ is not None: instruction += ...`     | 🛑 Blocker | DSPyBackend (default backend) still includes docstrings in LLM instructions   |
| `bae/dspy_backend.py` | 323-324  | `if t.__doc__: context_str += ...`                        | 🛑 Blocker | Type selection prompts still include docstrings                               |
| `bae/compiler.py`     | 103      | Comment: "Instruction is built from class name + optional docstring" | ⚠️ Warning | Documentation doesn't match phase goal (should be class name only)            |

### Human Verification Required

None — all verification items can be checked programmatically via grep and code inspection.

### Gaps Summary

**Critical Finding:** Plans 10-01 and 10-02 claimed to remove ALL `__doc__` reading from LLM-facing code, but they only addressed TWO of THREE backends:

**Backends in the codebase:**
1. ✓ **PydanticAIBackend** (bae/lm.py) — CLEAN (no `__doc__` references)
2. ✓ **ClaudeCLIBackend** (bae/lm.py) — CLEAN (no `__doc__` references)
3. ✗ **DSPyBackend** (bae/dspy_backend.py) — **STILL READS DOCSTRINGS**

**DSPyBackend is the DEFAULT backend** used when no LM is explicitly provided to Graph. It's also exported in `bae.__all__` and used by OptimizedLM.

**Two locations still reading `__doc__`:**

1. **`bae/compiler.py:131-132`** (in `node_to_signature`):
   ```python
   instruction = node_cls.__name__
   if node_cls.__doc__ is not None:
       instruction += f": {node_cls.__doc__.strip()}"
   ```
   - Used by: DSPyBackend.make(), DSPyBackend.decide(), OptimizedLM
   - Impact: Every DSPy Signature still includes class docstring in instruction

2. **`bae/dspy_backend.py:323-324`** (in `choose_type`):
   ```python
   for t in types:
       if t.__doc__:
           context_str += f"\n- {t.__name__}: {t.__doc__}"
   ```
   - Impact: Type selection prompts include docstrings for all candidate types

**Why this matters:**
- Phase goal: "Make docstrings inert" — docstrings should NOT be read by LLM-facing code
- Reality: DSPyBackend (the default) still reads docstrings in 2 places
- This defeats the phase goal of preventing LLMs from compulsively generating/augmenting docstrings

**What's working:**
- ✓ Plan 10-02 successfully implemented Field(description=...) preservation
- ✓ _build_plain_model correctly passes FieldInfo to create_model
- ✓ transform_schema output includes descriptions from Field annotations
- ✓ examples/ootd.py demonstrates the new pattern with 6 field descriptions
- ✓ All 323 tests pass (but tests don't exercise DSPyBackend docstring behavior)

**Root cause:**
Plans 10-01 and 10-02 focused on `bae/graph.py` and `bae/lm.py` but didn't audit the entire codebase for `__doc__` references. The DSPyBackend was introduced earlier in the project (Phase 2) and lives in a separate file (`bae/dspy_backend.py`) that wasn't included in the plan scope.

---

_Verified: 2026-02-08T19:20:39Z_
_Verifier: Claude (gsd-verifier)_
