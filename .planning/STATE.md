# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-07)

**Core value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing
**Current focus:** v3.0 Phase 9 — JSON Structured Fill

## Current Position

Phase: 9 (JSON Structured Fill) — IN PROGRESS
Plan: spike/e2e-cli branch (pre-plan exploration)
Status: In Progress — pivoted from XML to JSON, updating planning docs
Last activity: 2026-02-08 — JSON pivot complete in code, planning docs catching up

Progress: [##############################] 100% v2.0 (30/30 plans) | Phase 9 in progress

## Performance Metrics

**Velocity:**
- Total plans completed: 30 (13 v1.0 + 17 v2.0)
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Signature Generation | 1 | — | — |
| 1.1 Deps & Signature Extension | 1 | — | — |
| 2. DSPy Integration | 5 | — | — |
| 3. Optimization | 4 | — | — |
| 4. Production Runtime | 2 | — | — |
| 5. Markers & Resolver | 4/4 | ~25min | ~6min |
| 6. Node & LM Protocol | 5/5 | ~40min | ~8min |
| 7. Integration | 4/4 | ~20min | ~5min |
| 8. Cleanup & Migration | 4/4 | ~11min | ~3min |

*All phases complete*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
v2 design decisions documented in PROJECT.md v2 Design Decisions section.

Key v2 decisions affecting Phase 5:
- Use `model_construct()` for internal node creation (bypass Pydantic validation for deferred field population)
- `graphlib.TopologicalSorter` for dep chain resolution and cycle detection
- Dep on start node is allowed (auto-resolved); Recall on start node is an error
- Per-run dep caching (same dep function + args = cached result within one graph run)
- Dep.fn is first positional field so `Dep(callable)` works without keyword (description kwarg removed in Phase 8)
- classify_fields() skips "return" key from get_type_hints
- build_dep_dag uses id(fn) for visited set deduplication
- validate_node_deps calls build_dep_dag internally for cycle detection
- Only first marker per field processed in validation (consistent with classify_fields)
- recall_from_trace uses issubclass(field_type, target_type) direction for MRO matching
- recall_from_trace skips Dep and Recall annotated fields (infrastructure, not LLM-filled)
- resolve_dep cache keyed by callable identity (fn object), not function name
- Dep function exceptions propagate raw (no BaeError wrapping)
- resolve_fields returns only Dep and Recall field values, not plain fields

Key v2 decisions from Phase 6:
- NodeConfig is standalone TypedDict (not extending Pydantic ConfigDict)
- _wants_lm checks for 'lm' parameter in __call__ signature
- node_to_signature uses classify_fields from resolver (not Context markers)
- is_start parameter controls plain field direction (InputField vs OutputField)
- choose_type/fill take context dict, not node instance (decoupled from v1)
- Single-type lists skip LLM call entirely (optimization on all backends)
- DSPyBackend.fill uses model_construct to merge context + LM output

Key v2 decisions from Phase 7:
- _get_base_type kept in graph.py (compiler.py imports it, not incant-specific)
- recall_from_trace skips Dep fields; tests use bridge node pattern for Recall
- max_iters=0 means infinite (falsy check skips iteration guard)
- Terminal nodes appended to trace before loop exit
- Graph.run() no longer accepts **kwargs (external dep injection removed)
- MockLMs keep v1 make/decide as stubs for custom __call__ nodes that invoke them
- v1 incant tests deleted (not ported) — v2 dep resolution covered by test_dep_injection.py
- incant removed from pyproject.toml dependencies

Key decisions from Phase 8:
- _build_inputs collects all node model_fields (not just Context-annotated) — correct v2 behavior
- v1 make/decide kept on LM Protocol for custom __call__ escape-hatch nodes (docstring updated)
- Dep.description removed — Dep(callable) is the only constructor form
- E2E tests gated behind --run-e2e flag to avoid CI failures without API keys
- Structural validation sufficient for phase gate when no LLM key available

Key decisions from Phase 9 (JSON Structured Fill):
- Pivoted from XML completion to JSON structured output — Claude CLI's `--json-schema` provides constrained decoding (guaranteed schema-conformant responses)
- `transform_schema()` from Anthropic SDK prepares Pydantic models for constrained decoding (strips unsupported constraints, adds additionalProperties: false)
- `_build_plain_model()` creates dynamic Pydantic model with only plain fields for LLM output schema
- `_build_choice_schema()` uses dynamic Pydantic enum + transform_schema for choose_type constrained decoding
- `_build_fill_prompt()` serializes source node and resolved deps as JSON (not XML)
- `--setting-sources ""` BREAKS structured output in Claude CLI — removes StructuredOutput internal tool. Must NOT be used.
- `validate_plain_fields()` validates LLM-generated plain fields through Pydantic (FillError on failure)

### Pending Todos

- Real CLI E2E Turn 2 still fails — need to debug after JSON pivot changes are solid
- `format_as_xml` still used in v1 methods (_node_to_prompt) and choose_type (PydanticAIBackend) — clean up or keep for v1 compat
- Tests need verification after _build_fill_prompt JSON change (311 passed before this edit)

### Blockers/Concerns

- **Claude CLI session noise**: Optimizer runs create many boring test sessions that drown out real sessions in Claude CLI history. When using ClaudeCLIBackend for optimization, set the "don't save session to disk" flag to avoid polluting session history.

## Session Continuity

Last session: 2026-02-08
Stopped at: Phase 9 in progress — JSON pivot code done, planning docs updated, need to run tests and real CLI E2E
Branch: spike/e2e-cli
Resume file: None
