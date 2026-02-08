# Phase 8: Cleanup & Migration - Research

**Researched:** 2026-02-08
**Domain:** v1 marker removal, test migration, end-to-end validation
**Confidence:** HIGH

## Summary

Phase 8 is a surgical removal of v1 markers (Context, Bind) from source code, exports, and tests, followed by migrating all test fixtures to v2 patterns and validating the ootd.py example runs end-to-end with a real LLM.

The codebase has clean separation between v1 and v2 code paths. Context and Bind are only used in: `bae/markers.py` (definitions), `bae/__init__.py` (exports), `bae/compiler.py` (`_extract_context_fields` helper), `bae/dspy_backend.py` (`_extract_context_fields` method + `_build_inputs`), and `bae/graph.py` (`_validate_bind_uniqueness`). The v2 runtime (Graph.run) does NOT use Context or Bind -- it uses `classify_fields()` from `bae/resolver.py` which only recognizes Dep and Recall. This means the source-side removal is clean with no risk of breaking the runtime.

Tests are the larger task. Seven test files reference Context or Bind: `test_bind_validation.py` (delete entirely), `test_compiler.py` (rewrite Context fixtures to plain fields), `test_dspy_backend.py` (rewrite Context fixtures to plain fields), `test_optimized_lm.py` (rewrite Context fixtures), `test_optimizer.py` (rewrite Context fixtures), `test_auto_routing.py` (rewrite Context fixtures), `test_signature_v2.py` (delete backward-compat section), and `test_integration_dspy.py` (rewrite Context fixtures). Several other test files use `lm.make/lm.decide` in custom `__call__` nodes and MockLM stubs -- these are v1 LM methods that remain in the LM Protocol per the STATE.md note about MockLMs keeping v1 stubs.

**Primary recommendation:** Work inside-out: remove source definitions first (markers.py, compiler.py, dspy_backend.py, graph.py, __init__.py), then migrate tests file-by-file, then validate ootd.py. Run tests after each file change to catch cascading failures immediately.

## Standard Stack

No new libraries needed. This phase is pure deletion and rewriting.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | existing | Test runner | Already in use |
| pydantic-ai | existing | LM backend for ootd.py e2e | Already used by PydanticAIBackend |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest markers | builtin | Mark slow/e2e tests | For the real LLM test of ootd.py |

## Architecture Patterns

### Recommended Order of Operations

The migration should follow a dependency-aware order to minimize broken intermediate states:

```
1. Source removal (bae/ directory):
   a. bae/markers.py     -- delete Context and Bind classes
   b. bae/compiler.py    -- delete _extract_context_fields() function, remove Context import
   c. bae/dspy_backend.py -- rewrite _extract_context_fields/_build_inputs to use all fields, remove Context import
   d. bae/graph.py       -- delete _validate_bind_uniqueness(), remove Bind import, remove call in validate()
   e. bae/__init__.py    -- remove Context and Bind from imports and __all__

2. Test deletion:
   a. tests/test_bind_validation.py -- delete entire file

3. Test migration (each file independently):
   a. tests/test_compiler.py       -- rewrite fixtures, delete TestContextMarker, update TestDepMarker
   b. tests/test_dspy_backend.py   -- rewrite fixtures (Context -> plain fields)
   c. tests/test_optimized_lm.py   -- rewrite fixtures (Context -> plain fields)
   d. tests/test_optimizer.py      -- rewrite fixtures (Context -> plain fields)
   e. tests/test_auto_routing.py   -- rewrite fixtures (Context -> plain fields)
   f. tests/test_signature_v2.py   -- delete TestExistingTestsStillPass class
   g. tests/test_integration_dspy.py -- rewrite fixtures (Context -> plain fields)

4. Dep marker cleanup:
   a. bae/markers.py     -- remove deprecated v1 docstring, remove description field from Dep
   b. tests/test_resolver.py -- delete test_dep_backward_compat test
   c. tests/test_compiler.py -- delete TestDepMarker (tests Dep(description=...) which is v1)

5. Source cleanup:
   a. bae/lm.py          -- update LM Protocol docstring (remove "v1 methods will be removed in Phase 8")
   b. bae/markers.py     -- update Dep docstring (remove v1 deprecation notice)

6. ootd.py validation (last, after all source changes are stable)
```

### Pattern: Context-annotated Field -> Plain Field

The migration pattern for test fixtures is mechanical:

**Before (v1):**
```python
from bae.markers import Context

class SimpleNode(Node):
    content: Annotated[str, Context(description="The content to process")]
```

**After (v2):**
```python
class SimpleNode(Node):
    content: str
```

In v2, plain fields on non-start nodes become OutputFields (LLM fills them). The `Context(description=...)` annotation is ignored by `classify_fields()` -- it falls through to "plain" -- so functionally removing the annotation changes nothing about runtime behavior.

### Pattern: DSPyBackend._build_inputs Rewrite

The `_extract_context_fields` method on DSPyBackend currently filters for Context-annotated fields. After removing Context, `_build_inputs` should pass ALL node field values as inputs to the predictor, since the v2 `make()` path is only used by custom `__call__` escape-hatch nodes calling `lm.make()` directly.

**Before:**
```python
def _extract_context_fields(self, node: Node) -> dict[str, Any]:
    fields = {}
    hints = get_type_hints(node.__class__, include_extras=True)
    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            for meta in get_args(hint)[1:]:
                if isinstance(meta, Context):
                    fields[name] = getattr(node, name)
                    break
    return fields

def _build_inputs(self, node: Node, **deps: Any) -> dict[str, Any]:
    inputs = self._extract_context_fields(node)
    inputs.update(deps)
    return inputs
```

**After:**
```python
def _build_inputs(self, node: Node, **deps: Any) -> dict[str, Any]:
    inputs = {name: getattr(node, name) for name in node.model_fields}
    inputs.update(deps)
    return inputs
```

This mirrors what `_build_context` in graph.py already does. The `_extract_context_fields` method can be deleted entirely.

### Pattern: Bind Validation Removal

`graph.py` has `_validate_bind_uniqueness()` called from `validate()`. After removing Bind:

1. Delete the `_validate_bind_uniqueness` method entirely
2. Remove the `issues.extend(self._validate_bind_uniqueness())` call from `validate()`
3. Remove `from bae.markers import Bind` import

### Pattern: ootd.py E2E Test Structure

**Recommendation:** Use a pytest marker `@pytest.mark.e2e` with `conftest.py` configuration so the test is skipped by default (requires `--run-e2e` flag or `pytest -m e2e`). This prevents CI from making LLM calls on every push.

```python
# tests/conftest.py addition
def pytest_addoption(parser):
    parser.addoption("--run-e2e", action="store_true", default=False,
                     help="Run end-to-end tests requiring real LLM")

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-e2e"):
        skip = pytest.mark.skip(reason="need --run-e2e to run")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip)

# tests/test_ootd_e2e.py
import pytest
from examples.ootd import graph, IsTheUserGettingDressed
from bae import GraphResult, PydanticAIBackend

@pytest.mark.e2e
def test_ootd_runs_end_to_end():
    """ootd.py graph executes with a real LLM and produces valid output."""
    lm = PydanticAIBackend()
    result = graph.run(
        IsTheUserGettingDressed(user_message="ugh i just got up"),
        lm=lm,
    )
    assert isinstance(result, GraphResult)
    assert len(result.trace) >= 3  # At least 3 nodes in the chain
    final = result.trace[-1]
    assert hasattr(final, 'top')        # RecommendOOTD fields
    assert hasattr(final, 'bottom')
    assert hasattr(final, 'footwear')
    assert hasattr(final, 'final_response')
    assert final.final_response  # Non-empty response
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Deprecation warnings | Custom import hooks or shims | Standard Python AttributeError | Dzara's decision: clean break, no shims |
| E2E test gating | Environment variable checks | pytest markers + conftest addoption | Standard pytest pattern, composable with CI |
| Field-to-input mapping | New extraction function | `node.model_fields` iteration | Pydantic already tracks all fields |

## Common Pitfalls

### Pitfall 1: Dep.description Removal Breaking Tests
**What goes wrong:** Removing the `description` field from the Dep dataclass causes `Dep(description="...")` calls in tests to fail with TypeError.
**Why it happens:** `test_compiler.py` TestDepMarker and `test_dspy_backend.py` NodeWithDep both use `Dep(description="...")` v1 syntax. `test_resolver.py` has an explicit `test_dep_backward_compat` test.
**How to avoid:** Delete these tests as part of the migration. The v1 `Dep(description=...)` pattern is dead -- no production code uses it after Context removal.
**Warning signs:** TypeError on `Dep(description="...")` after removing the `description` field.

**Files using Dep(description=...):**
- `tests/test_compiler.py` lines 130, 136, 141-142 (TestDepMarker class)
- `tests/test_dspy_backend.py` line 48 (NodeWithDep class)
- `tests/test_resolver.py` line 108 (test_dep_backward_compat)
- `bae/markers.py` lines 30-45 (docstring only -- v1 usage examples in the doc)

### Pitfall 2: DSPyBackend._build_inputs Regression
**What goes wrong:** After removing `_extract_context_fields`, `_build_inputs` no longer passes node field values to the predictor, causing `make()` to call the LLM without context.
**Why it happens:** The old path relied on Context annotations to know which fields to pass. Removing Context without updating `_build_inputs` leaves it returning an empty dict.
**How to avoid:** Rewrite `_build_inputs` to use `node.model_fields` (pass all fields). This is the correct v2 behavior.
**Warning signs:** `make()` calls produce garbage output because no context was passed.

### Pitfall 3: Graph.validate() Calling Deleted Method
**What goes wrong:** `validate()` calls `self._validate_bind_uniqueness()` which was deleted.
**Why it happens:** Forgetting to remove the call site when deleting the method.
**How to avoid:** Remove both the method AND the call in `validate()`. Search for all references.

### Pitfall 4: Test Node Definitions at Module Level
**What goes wrong:** Test nodes with Context annotations are defined at module level (not inside test functions). They're used by multiple test classes in the same file.
**Why it happens:** Pydantic models can't be easily redefined inside functions (class name collisions in Pydantic's model registry).
**How to avoid:** Update the module-level node definitions, not just the test functions. Check that all test classes using a shared fixture node still work after the change.

### Pitfall 5: CompiledGraph.run(**deps) Latent Bug
**What goes wrong:** `CompiledGraph.run()` accepts `**deps` and passes them to `self.graph.run()`, but `Graph.run()` no longer accepts `**kwargs`.
**Why it happens:** The signature was left from v1. Currently harmless because no callers pass deps.
**How to avoid:** Fix the signature of `CompiledGraph.run()` to match `Graph.run()` -- remove `**deps` parameter.

### Pitfall 6: test_integration_dspy.py Fixture Coupling
**What goes wrong:** The test nodes in `test_integration_dspy.py` (AnalyzeQuery, ProcessSimple, ProcessComplex, Review) use Context annotations. Their `__call__` methods use ellipsis bodies (v2 auto-routing). Changing the annotations should be safe because the v2 runtime ignores Context (treats it as "plain").
**Why it happens:** These nodes were written during the v2 transition and still carry v1 Context annotations.
**How to avoid:** Verify after migration that the auto-routing still works correctly (ellipsis body detection, choose_type/fill calls). The auto-routing is independent of field annotations.

## Code Examples

### Removing Context and Bind from markers.py

After removal, markers.py should contain only:

```python
"""Annotation markers for bae Node fields."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Dep:
    """Marker for dependency-injected fields.

    Dep(callable) stores a callable whose return value
    populates the field before node execution.

    Usage:
        class MyNode(Node):
            data: Annotated[str, Dep(get_data)]
    """

    fn: Callable | None = None


@dataclass(frozen=True)
class Recall:
    """Marker for fields populated from the execution trace.

    Recall() searches backward through the execution trace for the most
    recent node whose type matches (via MRO) and copies the field value.

    Usage:
        class ReviewCode(Node):
            prev_analysis: Annotated[str, Recall()]
    """

    pass
```

Note: The `description` field on Dep is removed. It was v1 backward compat. After Context is gone, no code path uses `Dep(description=...)`.

### Removing __init__.py exports

```python
from bae.markers import Dep, Recall  # Context and Bind removed

__all__ = [
    # Core types
    "Node",
    "NodeConfig",
    "Graph",
    "GraphResult",
    # Markers
    "Dep",
    "Recall",
    # ... rest unchanged
]
```

### Rewriting test_compiler.py (TestNodeToSignature)

The key changes -- test nodes no longer import or use Context:

```python
# Before
from bae.markers import Context, Dep

class ProcessRequest(Node):
    request: Annotated[str, Context(description="The user's request")]

# After
from bae.markers import Dep

class ProcessRequest(Node):
    request: str  # plain field -- OutputField on non-start
```

Tests that verified Context-specific behavior should be rewritten to verify v2 behavior (plain fields as output, classify_fields integration).

### Rewriting test_dspy_backend.py fixture nodes

```python
# Before
class SimpleNode(Node):
    content: Annotated[str, Context(description="The content to process")]

# After
class SimpleNode(Node):
    content: str
```

The test `test_make_passes_context_fields_as_inputs` becomes `test_make_passes_node_fields_as_inputs` -- same assertion, just verifying all fields are passed (not just Context-annotated ones).

### Rewriting test_auto_routing.py fixture nodes

```python
# Before
class EllipsisUnionNode(Node):
    content: Annotated[str, Context(description="Content")]
    def __call__(self, lm: LM) -> TargetA | TargetB:
        ...

# After
class EllipsisUnionNode(Node):
    content: str
    def __call__(self, lm: LM) -> TargetA | TargetB:
        ...
```

Auto-routing tests don't depend on field annotations at all -- they test `_has_ellipsis_body` and `_get_routing_strategy`, which only look at the `__call__` method body and return types.

## Orphan Analysis

After removing Context and Bind, check for orphaned code:

| Code | File | Orphaned? | Action |
|------|------|-----------|--------|
| `_extract_context_fields()` function | compiler.py | YES | Delete |
| `_extract_context_fields()` method | dspy_backend.py | YES | Delete, rewrite `_build_inputs` |
| `_validate_bind_uniqueness()` | graph.py | YES | Delete |
| `Context` import in compiler.py | compiler.py | YES | Remove |
| `Context, Dep` import in dspy_backend.py | dspy_backend.py | Partial | Change to just `Dep` import (if Dep still needed), or remove entirely |
| `Bind` import in graph.py | graph.py | YES | Remove |
| `Dep.description` field | markers.py | YES after Context removal | Remove field |
| `_build_inputs` method | dspy_backend.py | NO, still used by `make()` | Rewrite to use model_fields |

Note: After removing Context, the `dspy_backend.py` import of `Context` from `bae.markers` is orphaned. But `Dep` is still imported there for the `_build_inputs` method. However, looking more carefully, `dspy_backend.py` only uses `Dep` in the import -- the `_build_inputs` method passes `**deps` kwargs but doesn't inspect Dep markers. The `Dep` import can be removed too.

Actually, checking more carefully: `dspy_backend.py` line 20 imports `Context, Dep`. The `Context` is used in `_extract_context_fields` (being deleted). The `Dep` import is... not used anywhere else in the file! So both imports can be removed from dspy_backend.py.

## LM Protocol Considerations

The LM Protocol in `bae/lm.py` currently documents:
```python
v1 methods (make/decide): node-centric, will be removed in Phase 8.
```

Per STATE.md: "MockLMs keep v1 make/decide as stubs for custom __call__ nodes that invoke them." This means `make()` and `decide()` are NOT being removed in this phase. They remain in the LM Protocol because custom `__call__` escape-hatch nodes still call `lm.make()` and `lm.decide()` directly. The docstring should be updated to remove the "will be removed in Phase 8" claim.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Context(description="...") on fields | Plain fields (no annotation needed) | Phase 6 | Context annotation was already a no-op in v2 runtime |
| Bind() for cross-node injection | Dep(callable) + Recall() | Phase 5 | Bind was superseded by explicit dep functions |
| _extract_context_fields() for input building | classify_fields() from resolver | Phase 6 | Signature generation uses resolver instead |
| Dep(description="...") for __call__ params | Dep(fn) on fields | Phase 5 | Description-only dep was v1 pattern |

## Open Questions

1. **Dep.description removal scope**
   - What we know: `Dep.description` is only used in v1 patterns. After Context removal, no production code uses it. Three test locations use `Dep(description=...)`.
   - What's unclear: Whether Dzara considers removing `Dep.description` in-scope for Phase 8 or wants it deferred. The CONTEXT.md says "Claude's Discretion: Whether any helper code in markers.py becomes orphaned after Context/Bind removal and should be cleaned up."
   - Recommendation: Remove `Dep.description` in this phase. It's orphaned v1 code. Clean break.

2. **make/decide on LM Protocol**
   - What we know: The docstring says "v1 methods, will be removed in Phase 8." But they're still used by custom __call__ nodes. STATE.md says MockLMs keep stubs for them.
   - What's unclear: Whether the docstring update ("not being removed") is in scope, or if this is a follow-up.
   - Recommendation: Update the docstring in this phase. It's a one-line change and prevents confusion.

3. **conftest.py for e2e marker**
   - What we know: No existing conftest.py handles e2e markers.
   - What's unclear: Whether the e2e test infrastructure should live in `tests/conftest.py` or be a standalone script.
   - Recommendation: `tests/conftest.py` with `--run-e2e` option. Standard pytest pattern. The test itself goes in `tests/test_ootd_e2e.py`.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all 14 files referencing Context/Bind
- `bae/markers.py` -- Context and Bind class definitions
- `bae/compiler.py` -- `_extract_context_fields()` and `node_to_signature()`
- `bae/dspy_backend.py` -- `_extract_context_fields()` method and `_build_inputs()`
- `bae/graph.py` -- `_validate_bind_uniqueness()` and `validate()`
- `bae/__init__.py` -- exports
- `bae/resolver.py` -- `classify_fields()` (v2 path, does NOT reference Context)
- `bae/lm.py` -- LM Protocol with make/decide/choose_type/fill
- All 7 test files with Context/Bind references
- `examples/ootd.py` -- already uses v2 patterns (no Context/Bind)
- `examples/fixtures/` -- geo, weather, cal fixture files exist

### Secondary (MEDIUM confidence)
- STATE.md notes about CompiledGraph.run(**deps) latent bug
- STATE.md notes about MockLMs keeping v1 make/decide stubs

## Metadata

**Confidence breakdown:**
- Source removal: HIGH -- complete codebase grep analysis, all references enumerated
- Test migration: HIGH -- every test file read in full, every Context/Bind usage identified
- Orphan analysis: HIGH -- traced all imports and usages
- ootd.py validation: HIGH -- read the example, verified fixtures exist, confirmed v2 patterns
- E2E test structure: MEDIUM -- pytest marker pattern is standard but exact API key/model availability not verified

**Research date:** 2026-02-08
**Valid until:** N/A (codebase-specific, valid as long as no new commits change the files)
