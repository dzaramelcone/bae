# Project Research Summary

**Project:** Bae v2.0 "Context Frames"
**Domain:** Type-driven agent graphs with dependency injection, trace-based recall, and DSPy optimization
**Researched:** 2026-02-07
**Confidence:** HIGH

## Executive Summary

Bae v2.0's context frame pattern is a genuine innovation in the agent framework space. By making Pydantic model fields the dependency injection site—where each field independently declares how it gets its value via `Dep(callable)` or `Recall()` metadata—bae inverts the typical control flow. Instead of nodes producing successors, bae orchestrates field assembly from three sources (dependency callables, trace search, LLM generation), then constructs nodes. No surveyed framework (FastAPI, PydanticAI, LangGraph, DSPy, Dagster) implements per-field dependency resolution on model classes or type-based trace recall for runtime injection.

The recommended approach leverages stdlib exclusively—no new dependencies needed. Python's `graphlib.TopologicalSorter` handles dependency chaining with cycle detection, `get_type_hints(include_extras=True)` extracts Annotated metadata, and Pydantic's `FieldInfo.metadata` categorizes field sources. The one dependency to remove is `incant`, which v2's simpler, purpose-built `Dep(callable)` system replaces entirely. Critical validation shows all patterns work correctly on Python 3.14 + Pydantic 2.12.5.

The primary architectural risk is Pydantic's eager validation of required fields at `__init__` time, which conflicts with bae's intent to populate Dep/Recall fields after construction. Using `model_construct()` for internal node creation (bypassing validation) followed by explicit validation solves this cleanly without polluting type signatures with `Optional` everywhere. Secondary risks include circular dependency chains (mitigated by upfront DAG validation with `graphlib.CycleError`) and type collision in Recall (mitigated by uniqueness validation at graph build time). The refactoring is focused, not a rewrite—existing topology discovery, validation, and trace collection survive with minor modifications.

## Key Findings

### Recommended Stack

v2.0 requires **zero new dependencies**. Every capability—DAG resolution, Annotated metadata extraction, field categorization, trace search—is covered by Python's stdlib (`graphlib`, `typing`) and Pydantic's existing `FieldInfo` API. The key verified insight: Pydantic's `FieldInfo.metadata` already contains `Dep`/`Recall` instances when fields use `Annotated[T, Dep(fn)]`, enabling clean introspection without re-parsing.

**Core technologies:**
- **`graphlib.TopologicalSorter` (stdlib)**: Dependency chain resolution — guaranteed available since Python 3.9, handles cycle detection via `CycleError`, provides execution order in one call
- **`typing.get_type_hints(include_extras=True)` (stdlib)**: Annotated metadata extraction — needed for dep function parameter introspection, resolves type aliases transparently
- **Pydantic `FieldInfo.metadata` (existing)**: Field categorization — simpler than stdlib approach for node field introspection, already parsed by Pydantic
- **Remove `incant`**: Replaced by purpose-built Dep system — eliminates hook factory indirection, unnecessary generic DI framework

**Version compatibility:**
- Python: 3.9 minimum for `graphlib`, 3.14 installed (PEP 649 deferred annotations)
- Pydantic: 2.11+ minimum (class-level `model_fields` access), 2.12.5 installed

### Expected Features

Research surveyed FastAPI, PydanticAI, LangGraph, DSPy, Dagster to identify table stakes vs differentiators for dependency injection and trace-based recall patterns.

**Must have (table stakes):**
- **Type-based dependency resolution** — Core pattern in FastAPI, Dagster, PydanticAI; users expect deps matched by type
- **Dep callable invocation** — FastAPI `Depends(fn)` is canonical; if annotated `Dep(fn)`, framework must call fn
- **Dep chaining (recursive resolution)** — FastAPI resolves sub-dependencies recursively; expected for `Dep(fn)` where fn itself has deps
- **Clear error on missing deps** — All surveyed frameworks give clear errors; must name missing type and requesting node
- **Execution trace as list of typed nodes** — LangGraph checkpoints, DSPy traces, Prefect task results all track history
- **LLM fills unannotated fields** — Core bae identity: "no annotation = LLM fills it"
- **Caching within single run** — FastAPI caches per-request; prevents calling expensive deps (API calls, DB) twice

**Should have (competitive differentiators):**
- **`Dep(callable)` on fields, not params** — Novel pattern; fields declare their own data sources, node class IS the dependency spec
- **`Recall()` type-based trace search** — `Annotated[WeatherResult, Recall()]` searches execution trace for most recent match; no explicit data passing needed
- **Node class name = LLM instruction** — Already in v1; class name IS the prompt instruction, no docstrings required
- **Fields as context frame** — Node fields = assembled prompt context from heterogeneous sources (Dep, Recall, LLM)
- **Dep chaining across heterogeneous sources** — Unique to bae; dep callable params can be other Dep types, Recall types, or plain values

**Defer (v2+):**
- **Cross-source chaining** (dep callable taking Recall param) — Novel but complex; get basic chaining working first
- **Recall with filters** (e.g., "recall from node named X") — Start with simple type matching
- **Async dep resolution** — Bae is sync-only; don't add async
- **Custom resolution strategies** — Three sources (Dep, Recall, LLM) are sufficient; no plugin architecture needed

### Architecture Approach

v2 inverts control from "nodes produce successors" (v1) to "bae orchestrates field assembly, nodes declare what they need" (v2). The execution loop changes from LM producing entire next nodes to LM filling only plain fields after bae resolves Dep and Recall fields. This is a focused refactoring, not a rewrite—topology discovery, validation, and trace collection survive with minor modifications.

**Major components:**
1. **markers.py (refactored)** — New `Dep(fn: Callable)` with callable, new `Recall()`, remove `Context`/`Bind`
2. **resolver.py (NEW module)** — Houses Dep/Recall resolution logic: `resolve_fields()`, `resolve_dep()` with chaining via DAG, `resolve_recall()` with trace search
3. **graph.py (major changes to run())** — Remove incant dependency, add field resolution step before LM call, modified execution loop with type-then-fill pattern
4. **lm.py (protocol changes)** — Replace `make()`/`decide()` with `choose_type()` (pick successor from union) + `fill()` (populate plain fields given resolved context)
5. **compiler.py (signature generation changes)** — Dep/Recall fields become InputFields (context for LLM), plain fields become OutputFields (LLM must produce)
6. **node.py (minimal changes)** — Remove `lm` parameter from `__call__`, update default implementation to ellipsis

**Data flow (v2):**
```
Graph.run() loop iteration:
  1. Determine target node TYPE (lm.choose_type or return type analysis)
  2. Resolve target's Dep fields (topological order, call functions)
  3. Resolve target's Recall fields (search trace backward)
  4. LM fills remaining plain fields (given resolved deps/recalls as context)
  5. Construct node instance from all field sources
  6. Append to trace
```

### Critical Pitfalls

**Top 5 from PITFALLS.md:**

1. **Pydantic validation fires before Dep/Recall population** — Pydantic validates all fields at `__init__`, but bae populates Dep/Recall after construction. **Solution:** Use `model_construct()` for internal node creation (bypasses validation), populate fields, then optionally validate. Avoids `Optional` pollution of type signatures.

2. **Circular dependencies in Dep chains** — Dep chaining (e.g., `get_weather` depends on `LocationDep`) can create cycles. **Solution:** Build Dep DAG at `Graph.__init__()` using `graphlib.TopologicalSorter`, which raises `CycleError` with exact cycle path. Fail fast at graph build time.

3. **Type collision in Recall** — If two nodes both have `str` field or same domain type, Recall finds wrong one. **Solution:** Validate type uniqueness at graph build time—each Recall target type should appear on exactly one upstream node. Log Recall resolutions for debugging.

4. **`from __future__ import annotations` breaks runtime extraction** — Existing codebase uses future import, turns annotations into strings. **Solution:** Audit all annotation access to use `get_type_hints(include_extras=True)`, never `__annotations__` directly. Consider removing future import entirely since Python 3.14 PEP 649 provides deferred evaluation natively.

5. **Removing Context/Bind breaks existing tests** — v1 API exports these markers; all tests use them. Big-bang removal breaks everything at once. **Solution:** Parallel implementation—add `Recall` and new `Dep(callable)` alongside existing markers, get new system working, then remove old markers. Use `@warnings.deprecated` during transition.

**Additional notable pitfall:**
- **Error propagation in Dep chains** — Errors in chained deps show generic framework error, not actual user function error. Wrap dep execution with chain context tracking: "Error in dep chain: get_weather -> get_location: ConnectionError(...)".

## Implications for Roadmap

Based on research, v2.0 implementation should follow dependency-driven phase structure:

### Phase 1: Foundation (Markers + Resolver)
**Rationale:** Everything else depends on markers and resolver being correct; testable in isolation without touching graph.py or lm.py.
**Delivers:** New `Dep(callable)` and `Recall()` markers, resolver module with Dep DAG resolution (topological sort), Recall trace search, error handling for cycles and missing types.
**Addresses:** Table stakes (type-based resolution, dep chaining, clear errors) and critical pitfall #2 (circular deps via graphlib).
**Avoids:** Pitfall #1 (Pydantic validation)—decide `model_construct()` strategy upfront; Pitfall #4 (annotation access)—audit and standardize before any feature work.
**Research flag:** Standard patterns (FastAPI `Depends` analog, graphlib docs comprehensive)—skip phase research.

### Phase 2: Node + LM Protocol (Interface)
**Rationale:** Node changes are small but affect every test; LM protocol change gates execution loop rewrite; must happen before Phase 3 integration.
**Delivers:** Remove `lm` parameter from node `__call__`, update LM protocol to `choose_type()` + `fill()`, implement new protocol in one backend (PydanticAI or DSPy).
**Addresses:** Differentiator (implicit LM configuration) and pitfall #8 (testability)—build `TestLM`/`StubLM` alongside.
**Avoids:** Pitfall #5 (breaking tests)—support both v1 and v2 `__call__` signatures during transition (pitfall #13).
**Research flag:** Standard patterns (protocol refactoring, documented in existing backends)—skip phase research.

### Phase 3: Execution Loop (Integration)
**Rationale:** Integration phase where Phase 1 (resolver) and Phase 2 (protocol) come together; largest code change in graph.py but built on tested components.
**Delivers:** Rewritten `Graph.run()` with resolver integration, validation changes (remove Bind checks, add start node + DAG checks), remove incant dependency.
**Addresses:** Table stakes (caching per-run, execution trace) and differentiators (context frame assembly).
**Avoids:** Pitfall #7 (incant caching)—custom resolver replaces incant entirely; Pitfall #10 (model_fields_set unreliable)—static field classification at build time.
**Research flag:** May need validation phase research if error handling patterns unclear during implementation—most logic is integration of tested components, but edge cases may surface.

### Phase 4: Compiler + Optimization (Adaptation)
**Rationale:** Compiler and optimization are downstream of core execution changes; DSPy signature generation must adapt to new field taxonomy.
**Delivers:** Updated `compiler.py` (Dep/Recall as InputField, plain as OutputField), updated `optimizer.py` (trace format changes), `OptimizedLM` implementing new protocol.
**Addresses:** Table stakes (LLM fills unannotated fields) with new context assembly model.
**Avoids:** Breaking DSPy optimization pipeline—trace structure remains compatible, only signature generation changes.
**Research flag:** Standard patterns (DSPy Signature construction documented)—skip phase research unless optimization metrics need redesign.

### Phase 5: Cleanup + Migration
**Rationale:** Final phase removes deprecated v1 patterns after new system is fully working; documentation and testing catchall.
**Delivers:** Remove `Context`/`Bind` from `__init__.py` exports, update all tests to v2 patterns, verify `examples/ootd.py` end-to-end.
**Addresses:** Pitfall #5 (breaking changes)—by this point parallel implementation complete.
**Avoids:** Pitfall #12 (dep alias scattering)—document conventions, add `graph.describe()` for dep visibility.
**Research flag:** No research needed—cleanup work.

### Phase Ordering Rationale

- **Phase 1 before 2 before 3:** Dependency chain (resolver → protocol → integration). Can't rewrite `run()` without new LM protocol; can't change protocol without resolver to call.
- **Phase 4 after 3:** Compiler adapts to new execution model; needs working graph to test against.
- **Phase 5 last:** Cleanup only safe after new system validated end-to-end.

**Critical path insight:** Pitfall #1 (Pydantic validation) and #4 (annotation access) must be addressed in Phase 1 or earlier—they block everything. Pitfall #2 (circular deps) must be solved in Phase 1 resolver design. Pitfall #5 (breaking tests) spans all phases via parallel implementation strategy.

### Research Flags

**Phases with standard patterns (skip research-phase):**
- **Phase 1:** FastAPI `Depends` pattern well-documented, `graphlib` stdlib docs comprehensive, Pydantic `FieldInfo` API stable
- **Phase 2:** Protocol refactoring straightforward, existing backends provide reference implementation
- **Phase 4:** DSPy signature construction documented, existing compiler provides starting point
- **Phase 5:** Cleanup work, no domain research needed

**Phases potentially needing validation during planning:**
- **Phase 3:** Integration edge cases may surface during implementation (error propagation in complex dep chains, Recall type matching with inheritance). Standard patterns exist but bae's combination is novel. Consider lightweight validation if unexpected issues arise, but start without phase research.

**No phases require deep research** — all patterns verified against live Python 3.14 + Pydantic 2.12.5 environment.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All patterns verified in bae's venv (Python 3.14, Pydantic 2.12.5); no new dependencies needed; incant removal confirmed viable |
| Features | HIGH | Table stakes verified via official docs for 5 frameworks; differentiators confirmed novel (no framework does per-field dep resolution or type-based trace recall) |
| Architecture | HIGH | Codebase analysis complete; phase dependencies clear; v2 reference implementation (`ootd.py`) demonstrates patterns work |
| Pitfalls | HIGH | Grounded in codebase analysis + verified patterns from FastAPI, Pydantic, graphlib; solutions tested or documented in stdlib |

**Overall confidence:** HIGH

### Gaps to Address

Research is comprehensive with no major gaps. Minor items to validate during implementation:

- **Dep cache scope decision:** Per-run caching (recommended) vs per-step caching. Start with per-run; add `cache=False` to Dep if needed later (YAGNI).
- **Custom `__call__` escape hatch:** When node has custom logic, should it return a type (bae resolves fields) or dict of field overrides + type? Recommend type-only for simplicity; extend to dict if needed.
- **Start node Dep/Recall validation:** Should bae error (recommended) or silently skip if start node has Dep/Recall fields? Recommend error—start node fields are caller-provided, Dep on start node is user mistake.
- **Recall recency semantics:** Should Recall return most recent match (recommended), all matches, or fail if multiple? Start with most recent single match; add multi-match support if use cases emerge.

All gaps are design decisions, not knowledge gaps. Defaults are reasonable; extensions can be added if real use cases emerge.

## Sources

### Primary (HIGH confidence)
- [Python graphlib documentation](https://docs.python.org/3/library/graphlib.html) — TopologicalSorter API, CycleError
- [Python typing documentation](https://docs.python.org/3/library/typing.html) — get_type_hints, Annotated, get_origin, get_args
- [Pydantic Fields API](https://docs.pydantic.dev/latest/api/fields/) — FieldInfo.metadata, FieldInfo.is_required()
- [Pydantic Models documentation](https://docs.pydantic.dev/latest/concepts/models/) — model_fields, model_construct
- [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) — Depends() pattern, chaining, caching
- [PydanticAI Dependencies](https://ai.pydantic.dev/dependencies/) — RunContext, deps_type pattern
- [DSPy Modules](https://dspy.ai/learn/programming/modules/) — Module composition, trace
- [LangGraph Runtime Docs](https://docs.langchain.com/oss/python/langchain/runtime) — InjectedState, Runtime context
- [Dagster Resources](https://dagster.io/blog/a-practical-guide-to-dagster-resources) — Type-annotated resource injection
- Live testing in bae's venv (Python 3.14, Pydantic 2.12.5, graphlib stdlib)
- Bae codebase analysis (`node.py`, `graph.py`, `lm.py`, `compiler.py`, `markers.py`, `examples/ootd.py`)

### Secondary (MEDIUM confidence)
- [PEP 649 — Deferred Evaluation of Annotations](https://peps.python.org/pep-0649/)
- [PEP 749 — Implementing PEP 649](https://peps.python.org/pep-0749/)
- [Pydantic v2.12 release notes](https://pydantic.dev/articles/pydantic-v2-12-release) — MISSING sentinel (experimental, decided against)
- [incant documentation](https://incant.threeofwands.com/en/stable/usage.html) — Hook factory pattern (v1 usage)
- [Anthropic Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Context as assembled frame

### Tertiary (LOW confidence, used for landscape only)
- [Prefect vs Dagster comparison](https://www.decube.io/post/dagster-prefect-compare) — Data passing patterns
- GitHub issues (LangGraph InjectedState, FastAPI Python 3.14 TYPE_CHECKING) — Edge case patterns

---
*Research completed: 2026-02-07*
*Ready for roadmap: yes*
