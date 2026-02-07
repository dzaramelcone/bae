# Pitfalls: v2.0 Context Frames

**Domain:** Adding dependency injection, trace-based recall, and context frame semantics to an existing agent graph framework
**Researched:** 2026-02-07
**Confidence:** HIGH (grounded in codebase analysis + verified patterns from FastAPI, pytest, Pydantic, incant, PEP 649/749)

---

## Critical Pitfalls

Mistakes that cause rewrites or block the milestone.

---

### Pitfall 1: Circular Dependencies in Dep Chains

**What goes wrong:**
Dep functions can declare params that are themselves Dep-annotated types (dep chaining). If `get_weather` depends on `LocationDep` and some future function depends on `WeatherDep`, you can build a cycle: `A -> B -> C -> A`. The DAG resolver loops forever or stack-overflows during resolution.

**Why it happens in bae specifically:**
The `ootd.py` example already demonstrates dep chaining (`get_weather` takes `LocationDep`). As graphs grow, transitive dep chains become harder to trace visually. Users define type aliases (`WeatherDep = Annotated[WeatherResult, Dep(get_weather)]`) in separate files, making the full graph invisible at definition time.

**Consequences:**
- Runtime hang or `RecursionError` during graph execution
- No error message pointing to which deps form the cycle
- If not caught at graph build time, only surfaces when a specific node is reached

**Prevention:**
1. Use `graphlib.TopologicalSorter` (stdlib) for dep resolution. It raises `graphlib.CycleError` with the exact cycle path in `args[1]`.
2. Build the dep DAG at `Graph.__init__()` time, not lazily at execution time. Fail fast.
3. Walk all node fields, extract `Dep(fn)` annotations, inspect `fn`'s parameters for further `Dep` types, and feed edges into `TopologicalSorter`.
4. The `CycleError` message should name the functions involved, not just types.

**Detection (warning signs):**
- Tests pass for simple graphs but new graphs cause hangs
- `RecursionError` in stack traces involving dep resolution
- Users defining type aliases that reference each other

**Phase to address:** Phase 1 (Dep implementation). Build cycle detection into the dep resolver from day one.

---

### Pitfall 2: Pydantic Validation Fires Before Dep/Recall Population

**What goes wrong:**
Pydantic validates all fields at `__init__` time. If a field is typed `weather: WeatherResult` (no default), Pydantic requires it at construction. But bae intends to populate it via `Dep(get_weather)` *after* construction. The model can't be instantiated without the value, yet the value doesn't exist until bae resolves deps.

**Why it happens in bae specifically:**
The v2 design says "fields without values = LLM fills them" and "Dep fields = bae fills them." Both cases assume fields can exist in an unpopulated state on a Pydantic model. But Pydantic v2 enforces required fields eagerly.

**Consequences:**
- `ValidationError` on node construction before bae gets a chance to populate deps
- Forces all Dep/Recall fields to have `default=None` or sentinels, polluting type signatures
- Users confused about which fields are "really required"

**Prevention:**
Three options, in order of preference:

1. **`model_construct()` for bae-internal construction.** Bae creates node instances using `model_construct()` which skips validation entirely, then populates dep/recall fields, then optionally runs `model_validate(node.model_dump())` to verify completeness. This keeps user-facing types clean (`weather: WeatherResult`, not `weather: WeatherResult | None`).

2. **Sentinel default via `MISSING`.** Pydantic v2.12+ has experimental `pydantic.experimental.missing_sentinel.MISSING`. Fields default to `MISSING`, bae replaces before LLM call. Risk: experimental API may change.

3. **`Optional` with convention.** Make all Dep/Recall fields `T | None = None`. Simple but ugly -- the type signature lies about the field's runtime guarantee.

**Detection (warning signs):**
- `ValidationError: field required` during graph execution
- All Dep fields ending up as `Optional` "just to make it work"
- `model_construct()` used everywhere without validation follow-up

**Phase to address:** Phase 1. This is the first thing that will break when implementing Dep fields. Decide the construction strategy before writing any Dep resolution code.

---

### Pitfall 3: `from __future__ import annotations` Breaks Runtime Annotation Extraction

**What goes wrong:**
The codebase already uses `from __future__ import annotations` in `node.py` and `graph.py`. This turns all annotations into strings. When bae inspects fields to find `Dep()` or `Recall()` metadata, `get_type_hints(cls, include_extras=True)` must be used instead of raw `__annotations__`. If any code path uses `cls.__annotations__` directly, it gets strings instead of resolved types.

**Why it happens in bae specifically:**
Python 3.14 introduces PEP 649 (deferred evaluation), but `from __future__ import annotations` is still present in the codebase. These are two different mechanisms:
- PEP 649: Annotations are lazily evaluated via `__annotate__` descriptors
- `from __future__ import annotations`: Annotations are stored as literal strings

If the codebase has `from __future__ import annotations`, PEP 649's deferred evaluation doesn't apply -- the future import takes precedence. This means `typing.get_type_hints()` is required for resolution, and it can fail if referenced types aren't importable in the module scope.

Furthermore, PEP 749 notes that `from __future__ import annotations` will eventually be deprecated post-3.13 EOL. The codebase should migrate away from it.

**Consequences:**
- `Annotated[WeatherResult, Dep(get_weather)]` becomes the string `"Annotated[WeatherResult, Dep(get_weather)]"` if accessed via `__annotations__`
- `get_type_hints()` can raise `NameError` if a referenced type isn't in scope
- Inconsistent behavior between modules with and without the future import

**Prevention:**
1. Audit every place that reads annotations. The existing code in `graph.py` (`_capture_bind_fields`, `_validate_bind_uniqueness`) correctly uses `get_type_hints(cls, include_extras=True)`. Maintain this discipline.
2. Consider removing `from __future__ import annotations` from the codebase entirely since Python 3.14 PEP 649 provides deferred evaluation natively. This eliminates the string-annotation footgun.
3. If keeping the future import, never access `__annotations__` directly -- always use `get_type_hints()`.
4. Watch for the FastAPI 3.14 issue: `inspect.signature()` on Python 3.14 may need `annotation_format=Format.FORWARDREF` to handle forward refs. If bae uses `inspect.signature()` (incant does internally), verify this works.

**Detection (warning signs):**
- `AttributeError` or `TypeError` when checking `isinstance(meta, Dep)` on string annotations
- Annotation introspection returning strings instead of type objects
- Tests passing on 3.13 but failing on 3.14

**Phase to address:** Phase 0 (before any feature work). Audit and standardize annotation access across the codebase.

---

### Pitfall 4: Type Collision in Recall (Multiple Fields with Same Type)

**What goes wrong:**
`Recall()` searches the execution trace backward for the nearest prior node with a matching field type. If two different nodes in the trace both have a `str` field, or both produce a `WeatherResult`, Recall finds the wrong one. The "nearest" heuristic silently returns stale or irrelevant data.

**Why it happens in bae specifically:**
The v2 design deliberately chose implicit trace search over explicit binding: "implicit writes via trace search are clean enough for now." This works when types are unique across the graph. It breaks when:
- Common types (`str`, `int`, `list[str]`) are used as Recall targets
- The same domain type appears in multiple nodes (e.g., two nodes both have a `Score` field)
- Graph topology changes and a different node now appears "nearest" in the trace

**Consequences:**
- Silent wrong data: Recall returns a value from the wrong node, no error raised
- Ordering-dependent bugs: Graph runs produce different results depending on path taken through branching
- Debugging nightmare: The bug manifests as "LLM gave a weird answer" because the context frame had wrong data

**Prevention:**
1. **Validate type uniqueness at graph build time.** When `Graph.__init__()` discovers nodes, check that for every `Recall()` field, the target type appears on exactly one upstream node. Warn (or error) on ambiguity.
2. **Discourage primitive types in Recall.** Document that `Recall()` with `str`, `int`, etc. is almost always wrong. Encourage wrapper types: `class UserQuery(BaseModel): text: str` instead of bare `str`.
3. **Consider `Recall(from_node=NodeClass)` as an escape hatch.** The YAGNI decision against `BindFor` is reasonable, but having `from_node` on the read side is cheap insurance against ambiguity. Don't build it now, but design the `Recall` dataclass to accept optional kwargs for future narrowing.
4. **Log Recall resolutions.** When Recall finds a match, log which node/field it matched. This makes debugging silent-wrong-data issues possible.

**Detection (warning signs):**
- LLM outputs that seem "off" despite correct prompting
- Tests that break when graph topology changes
- Multiple nodes with fields of the same Pydantic model type

**Phase to address:** Phase 2 (Recall implementation). Build uniqueness validation into the Recall resolver. Add logging.

---

### Pitfall 5: Removing Context/Bind Breaks Existing Tests and Examples

**What goes wrong:**
The v1 API exports `Context`, `Bind`, and `Dep` (current style) as public markers. Existing tests (`test_bind_validation.py`, `test_dep_injection.py`, `test_compiler.py`) use these markers extensively. The v2 removes `Context` entirely and replaces `Bind` with `Recall`. Removing them without a migration strategy means all existing tests break simultaneously, making it impossible to verify the new implementation against known-good behavior.

**Why it happens in bae specifically:**
Bae is a brownfield project with 396+ lines of passing tests. The markers are in `__init__.py`'s `__all__`. The compiler's `_extract_context_fields()` function is built around the `Context` marker. The graph's `_capture_bind_fields()` and `_validate_bind_uniqueness()` are built around `Bind`. Ripping these out is a big-bang change.

**Consequences:**
- All tests fail at once -- can't use existing tests to validate new code
- Can't do incremental development: every change requires updating everything
- Risk of regression: new code can't be compared against old behavior
- `__init__.py` exports change, breaking any downstream code

**Prevention:**
1. **Parallel implementation, not replacement.** Add `Recall` and new `Dep(callable)` alongside existing markers. Get the new system working and tested. Only then remove old markers.
2. **Deprecation phase.** Keep `Context` and `Bind` importable but mark with `@warnings.deprecated` (PEP 702, available via `typing_extensions`). Log a deprecation warning when they're used at runtime.
3. **Write new tests first.** Before touching old code, write tests for the new Dep/Recall behavior using the `ootd.py` example as a reference implementation. Old tests remain green throughout.
4. **Guard `__init__.py` exports.** Keep `Context` and `Bind` in `__all__` during the transition. Remove only after all internal usage is migrated.

**Detection (warning signs):**
- Large PRs that change marker definitions AND test files simultaneously
- Test suite goes from green to "everything fails"
- Temptation to delete old tests rather than migrating them

**Phase to address:** Spans all phases. Phase 1 adds new markers alongside old ones. Final phase removes old markers.

---

## Moderate Pitfalls

Mistakes that cause delays or technical debt.

---

### Pitfall 6: Error Propagation in Dep Chains

**What goes wrong:**
When a dep function raises an exception, the error propagates up through the dep chain. But the stack trace shows the internal resolver, not the user's dep function. Users see `TypeError: Missing dependency: GeoLocation` (from bae's `_create_dep_hook_factory`) instead of the actual error from `get_location()`.

**Why it happens in bae specifically:**
The current `_create_dep_hook_factory` in `graph.py` catches `TypeError` and re-raises as `BaeError`. This is fine for simple deps, but with chaining, errors can originate from any level of the chain. If `get_weather()` fails because `get_location()` returned invalid data, the user sees a generic error from the weather function, not the location function.

**Prevention:**
1. Wrap dep execution with context that tracks the chain: "Error in dep chain: get_weather -> get_location: ConnectionError(...)"
2. Catch and re-raise with the full chain path in the error message.
3. Distinguish between "dep function raised" (user error) and "dep not found" (framework error).
4. Test error scenarios explicitly: dep raises, dep returns wrong type, dep in chain raises.

**Phase to address:** Phase 1 (Dep implementation). Build error wrapping into the dep resolver.

---

### Pitfall 7: Incant Hook Factory Caching with Dynamic Dep Registries

**What goes wrong:**
The current code creates a new `Incanter` instance per `graph.run()` call and registers a hook factory that closes over the `dep_registry` dict. Incant caches composed functions for performance. If the dep registry changes between calls (different deps injected), cached functions may use stale deps.

**Why it happens in bae specifically:**
In the current code, `dep_registry` is mutated during execution (`_capture_bind_fields` adds to it). The hook factory closure captures the dict by reference, so mutations are visible. But if incant caches the *factory's output* (the lambda returning the value), the cached lambda captures the value at cache time, not at call time.

**Prevention:**
1. Verify incant's caching behavior with mutation tests. Create a dep, run, mutate dep registry, run again, verify the new value is used.
2. If incant caches aggressively, create a new Incanter per run (current behavior is correct for this).
3. When moving to the new Dep system, consider whether incant is still the right tool. The new Dep system with chaining may be better served by a custom resolver using `graphlib.TopologicalSorter`, since incant doesn't know about dep chaining natively.

**Phase to address:** Phase 1. Decide early whether to keep incant or build a custom dep resolver.

---

### Pitfall 8: Implicit LM Configuration Untestable Without Real LLM

**What goes wrong:**
v2 makes the LM implicit (graph-level config, removed from `__call__`). This means nodes can't receive a mock LM as a parameter -- bae owns the LM. Testing individual nodes in isolation requires configuring the graph's LM, which couples unit tests to graph setup.

**Why it happens in bae specifically:**
In v1, `__call__(self, lm: LM)` lets tests pass any LM implementation. In v2, `__call__(self)` with implicit LM means the test must either:
- Configure a graph-level LM (couples test to graph)
- Mock at the framework level (fragile, tests mock behavior)
- Use a real LLM (slow, non-deterministic, expensive)

**Prevention:**
1. **Provide a `TestLM` / `StubLM` as a first-class citizen.** A deterministic LM that returns pre-configured responses. Not a mock -- a real implementation of the LM protocol that returns predictable values.
2. **Allow LM override at `graph.run()` time.** The current API already supports `graph.run(node, lm=my_lm)`. Keep this, even though the default is implicit.
3. **Don't remove the LM parameter from node `__call__` too eagerly.** Consider making it optional: `__call__(self, lm: LM | None = None)`. If None, bae provides one. If given, use it. This preserves testability.
4. **DSPy's own testing pattern:** `dspy.configure(lm=dspy.utils.DummyLM({"output": "test"}))` sets a global LM. Bae could offer a similar `bae.configure(lm=...)` context manager for tests.

**Detection (warning signs):**
- Tests that require `ANTHROPIC_API_KEY` or network access
- Test files importing `DSPyBackend` and configuring real models
- Mocking framework internals to avoid real LLM calls

**Phase to address:** Phase 1. Build the test LM alongside the implicit LM feature.

---

### Pitfall 9: Trace Performance with Long Execution Histories

**What goes wrong:**
`Recall()` searches the trace backward. The trace is a `list[Node]`. For each Recall field, bae iterates the list in reverse, checking each node's fields for type matches. With long traces (50+ steps), this is O(n) per Recall field per node construction. With multiple Recall fields and branching graphs, this compounds.

**Why it happens in bae specifically:**
The current `GraphResult.trace` is a flat `list[Node]`. No indexing by type. No caching. Every Recall does a linear scan.

**Prevention:**
1. **Build a type index alongside the trace.** Maintain a `dict[type, Node]` that maps field types to the most recent node containing that type. Update it as each node executes. Recall becomes O(1) lookup.
2. **Index at write time, not read time.** When a node finishes executing, scan its fields and update the index. Don't scan the entire trace on every Recall.
3. **Don't premature-optimize, but design for it.** The flat list is fine for v2. But structure the Recall resolver so the trace representation is swappable. Don't hardcode `for node in reversed(trace)` throughout the codebase.

**Phase to address:** Phase 2 (Recall implementation). Use the indexed approach from the start -- it's not harder to implement, just requires a dict alongside the list.

---

### Pitfall 10: `model_fields_set` Unreliable for "Was This Field LLM-Generated?"

**What goes wrong:**
The v2 design distinguishes "fields with values" (from deps, recall, constructor) from "fields without values" (LLM fills). The natural Pydantic mechanism is `model_fields_set` -- the set of fields explicitly provided at construction. But `model_construct()` (needed per Pitfall 2) doesn't populate `model_fields_set` correctly. And if bae sets dep fields post-construction, those aren't in `model_fields_set` either.

**Why it happens in bae specifically:**
Bae needs to know which fields the LLM should fill. The plan is: "no annotation = LLM fills." But at runtime, after deps and recall are resolved, bae needs to determine which fields are still empty. If using `model_construct()`, `model_fields_set` won't help.

**Prevention:**
1. **Don't rely on `model_fields_set`.** Instead, determine LLM-fillable fields at class definition time from annotations: any field without `Dep()` or `Recall()` metadata and without a value from the constructor = LLM fills.
2. **Static analysis, not runtime inspection.** Walk the class's `model_fields` and `get_type_hints(include_extras=True)` at graph build time. Cache the result: `{NodeClass: {"llm_fields": [...], "dep_fields": [...], "recall_fields": [...]}}`.
3. **Start node is the exception.** Start node fields are caller-provided. Detect this from the graph (it's `graph.start`), not from runtime field inspection.

**Detection (warning signs):**
- Logic that checks `if field_name not in node.model_fields_set` to decide LLM behavior
- Inconsistent results when nodes are created via `model_construct()` vs normal init
- Bug where dep-populated fields get sent to the LLM anyway

**Phase to address:** Phase 1. Settle the field classification strategy before implementing any field-source logic.

---

## Minor Pitfalls

Mistakes that cause annoyance but are fixable.

---

### Pitfall 11: Dep Function Return Type Not Matching Field Type

**What goes wrong:**
User writes `Annotated[WeatherResult, Dep(get_weather)]` but `get_weather` returns `dict` instead of `WeatherResult`. Bae calls the function, gets a dict, assigns it to the field. Pydantic might coerce it (if the dict matches the model schema), or might fail late with a confusing error.

**Prevention:**
1. At graph build time, inspect `get_weather`'s return type annotation. Compare it to the field's base type. Warn if they don't match.
2. After dep execution, validate the returned value: `isinstance(result, expected_type)`.
3. Good error: "Dep function get_weather returns dict, but field 'weather' expects WeatherResult."

**Phase to address:** Phase 1.

---

### Pitfall 12: Dep Type Aliases Scatter Dep Definitions

**What goes wrong:**
The `ootd.py` pattern uses type aliases: `WeatherDep = Annotated[WeatherResult, Dep(get_weather)]`. This is clean for the user, but scatters dep definitions across files. When debugging which function populates which field, users have to trace through type aliases.

**Prevention:**
1. This is a documentation/convention issue, not a code issue. Recommend grouping all dep aliases in a `deps.py` module per graph.
2. Add a `graph.describe()` or `graph.deps()` method that lists all dep functions, their types, and which nodes use them.
3. Consider supporting inline deps too: `weather: Annotated[WeatherResult, Dep(get_weather)]` directly on the node field, without the alias indirection.

**Phase to address:** Phase 3 (developer experience).

---

### Pitfall 13: Node `__call__` Signature Divergence

**What goes wrong:**
v1 nodes: `def __call__(self, lm: LM) -> NextNode | None`. v2 nodes: `def __call__(self) -> NextNode: ...`. During migration, some nodes have the old signature, some have the new one. The graph runner must handle both, or one set breaks.

**Prevention:**
1. The graph runner already inspects `__call__` signatures (via `_has_ellipsis_body` and routing strategies). Add signature detection: if `__call__` accepts `lm` param, use v1 path. If not, use v2 path.
2. Document the migration: "Remove `lm` from `__call__` parameters. Use ellipsis body."
3. Add a deprecation warning when detecting v1-style `__call__` signatures.

**Phase to address:** Phase 1. Support both signatures during transition.

---

## Phase-Specific Warning Summary

| Phase | Pitfall | Risk | Mitigation Priority |
|-------|---------|------|---------------------|
| Phase 0 (Prep) | #3: Future import annotation breakage | HIGH | Audit and standardize annotation access |
| Phase 1 (Dep) | #1: Circular dep chains | HIGH | Use graphlib.TopologicalSorter |
| Phase 1 (Dep) | #2: Pydantic validation vs deferred population | CRITICAL | Decide model_construct strategy |
| Phase 1 (Dep) | #6: Error propagation in dep chains | MEDIUM | Wrap dep errors with chain context |
| Phase 1 (Dep) | #7: Incant caching with dynamic deps | MEDIUM | Verify or replace incant |
| Phase 1 (Dep) | #8: Implicit LM untestable | MEDIUM | Build StubLM alongside |
| Phase 1 (Dep) | #10: model_fields_set unreliable | HIGH | Static field classification |
| Phase 1 (Dep) | #11: Return type mismatch | LOW | Validate at build time |
| Phase 1 (Dep) | #13: __call__ signature divergence | MEDIUM | Support both during migration |
| Phase 2 (Recall) | #4: Type collision in Recall | HIGH | Uniqueness validation |
| Phase 2 (Recall) | #9: Trace performance | LOW (initially) | Index by type |
| All phases | #5: Removing markers breaks tests | HIGH | Parallel implementation |
| Phase 3 (DX) | #12: Dep alias scattering | LOW | Documentation + describe() |

## Key Architectural Decisions Forced by Pitfalls

These pitfalls force design decisions that should be made before coding starts:

1. **How to construct nodes with unpopulated fields?** (Pitfall #2)
   `model_construct()` + post-validation, or sentinel defaults, or Optional everywhere?

2. **How to classify field sources?** (Pitfall #10)
   Static analysis at build time (recommended) vs runtime `model_fields_set` inspection (fragile)?

3. **Keep incant or build custom dep resolver?** (Pitfall #7)
   Incant doesn't know about dep chaining. Custom resolver with `graphlib.TopologicalSorter` may be simpler.

4. **Remove `from __future__ import annotations`?** (Pitfall #3)
   Python 3.14 PEP 649 makes it unnecessary. Removing it simplifies annotation introspection.

5. **Big-bang marker replacement or parallel migration?** (Pitfall #5)
   Parallel implementation is safer but means maintaining two systems temporarily.

## Sources

**HIGH confidence:**
- [PEP 649 -- Deferred Evaluation of Annotations](https://peps.python.org/pep-0649/)
- [PEP 749 -- Implementing PEP 649](https://peps.python.org/pep-0749/)
- [Python graphlib documentation](https://docs.python.org/3/library/graphlib.html)
- [Pydantic v2 Models documentation](https://docs.pydantic.dev/latest/concepts/models/)
- [Pydantic v2 Forward Annotations](https://docs.pydantic.dev/latest/concepts/forward_annotations/)
- [incant documentation](https://incant.threeofwands.com/en/stable/usage.html)
- Bae codebase analysis (node.py, graph.py, markers.py, compiler.py, dspy_backend.py, examples/ootd.py)

**MEDIUM confidence:**
- [FastAPI Python 3.14 TYPE_CHECKING issue](https://github.com/fastapi/fastapi/discussions/14784) -- relevant pattern for annotation introspection under PEP 649
- [Pydantic v2.12 MISSING sentinel](https://pydantic.dev/articles/pydantic-v2-12-release) -- experimental, may not stabilize
- [FastAPI dependency injection patterns](https://fastapi.tiangolo.com/tutorial/dependencies/)

**LOW confidence:**
- incant caching behavior under mutation -- inferred from docs, not verified with tests
- `model_construct()` + post-validation pattern -- logical but not documented as an official Pydantic pattern

---
*Pitfalls research for: Bae v2.0 Context Frames*
*Researched: 2026-02-07*
