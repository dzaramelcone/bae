# Phase 8: Cleanup & Migration - Context

**Gathered:** 2026-02-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove v1 markers (Context, Bind) from source and exports, migrate all tests to v2 patterns, and validate ootd.py runs end-to-end with a real LLM. After this phase, no v1 marker code remains anywhere in the codebase.

</domain>

<decisions>
## Implementation Decisions

### v1 Test Handling
- **test_bind_validation.py**: Delete entirely. Bind is dead in v2, no point keeping tests for removed functionality.
- **test_compiler.py**: Rewrite v1 Context-specific test sections to assert v2 behavior (classify_fields, plain fields as output). Keep infrastructure tests, update their fixtures.
- **test_dspy_backend.py, test_optimized_lm.py, test_optimizer.py, test_auto_routing.py**: Rewrite fixtures to use v2 patterns (replace Context() field annotations with plain fields or Dep/Recall as appropriate). Keep all test assertions.
- **test_signature_v2.py**: Delete the backward-compat section that verifies Context still works. Context is being removed.

### Import Behavior After Removal
- Clean break: `from bae import Context` produces standard Python `AttributeError`. No custom error, no deprecation shim.
- Delete Context and Bind class definitions from `bae/markers.py` entirely. Dead code = delete it.
- Remove Context and Bind from `bae/__init__.py` exports.

### ootd.py Validation
- "Runs end-to-end" means a real LLM call. Actually invoke an LLM, get a real outfit recommendation, verify the output structure.
- ootd.py already uses v2 patterns and does not need changes. Validation = prove it actually executes successfully against the v2 runtime.

### Claude's Discretion
- Order of operations for the migration (which files to update first)
- Whether any helper code in markers.py becomes orphaned after Context/Bind removal and should be cleaned up
- How to structure the real LLM test for ootd.py (inline script, pytest marker, etc.)

</decisions>

<specifics>
## Specific Ideas

No specific requirements — decisions are clear-cut. This is a clean removal with test migration.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 08-cleanup-migration*
*Context gathered: 2026-02-08*
