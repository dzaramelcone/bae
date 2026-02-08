# Bae

## What This Is

A framework for building agent graphs where nodes are Pydantic models and topology comes from type hints. Nodes are "context frames" — their fields assemble the information the LLM needs to produce the next node. Class names are instructions, return types are output schemas, and Field(description=...) provides explicit per-field hints. Three field sources: Dep(callable) for external data, Recall() for graph state, and plain fields for LLM generation. JSON structured output with constrained decoding for reliable fills.

## Core Value

DSPy compiles agent graphs from type hints and class names - no manual prompt writing.

## Requirements

### Validated

- ✓ Node base class (Pydantic BaseModel) — v1.0
- ✓ Graph discovery from return type hints — v1.0
- ✓ Graph execution loop — v1.0
- ✓ LM protocol (make, decide) — v1.0
- ✓ PydanticAIBackend — v1.0
- ✓ ClaudeCLIBackend — v1.0
- ✓ Terminal node detection (returns None) — v1.0
- ✓ node_to_signature() with DSPy Signature generation — v1.0
- ✓ BootstrapFewShot optimization with trace collection — v1.0
- ✓ OptimizedLM with compiled prompt loading — v1.0
- ✓ Dep(callable) with DAG resolution and dep chaining — v2.0
- ✓ Recall() for graph state via backward trace search — v2.0
- ✓ Context marker removed — v2.0
- ✓ Bind marker removed — v2.0
- ✓ Implicit LM (graph-level config) — v2.0
- ✓ Start node fields = caller-provided input — v2.0
- ✓ Terminal node fields = response schema — v2.0
- ✓ JSON structured fill with constrained decoding — v2.0
- ✓ Field(description=...) for explicit LLM hints, docstrings inert — v2.0

### Active

(None — next milestone will define new requirements)

### Out of Scope

- BindFor explicit writes — implicit trace search is clean enough (YAGNI)
- Parallel fan-out (`tuple[A, B]`) — not needed yet (YAGNI)
- Validation error retry loops — DSPy optimization may solve this
- Async interface — sync is simpler, revisit if needed

## Context

Shipped v2.0 with 9,297 lines of Python (2,718 source + 6,298 test).

Tech stack: Python 3.14+, Pydantic, pydantic-ai, dspy, Anthropic SDK.

Three LM backends: PydanticAIBackend, ClaudeCLIBackend, DSPyBackend — each with v1 (make/decide) and v2 (choose_type/fill) methods.

Reference implementation: `examples/ootd.py` — 3-node outfit recommendation graph with deps, recalls, and LLM-filled fields.

323 tests passing (313 unit + 5 e2e gated behind --run-e2e + 5 PydanticAI integration skipped without API key).

## Constraints

- **Python**: 3.14+ — PEP 649 eliminates forward ref issues
- **Dependencies**: pydantic, pydantic-ai, dspy, anthropic (SDK for transform_schema)
- **Interface**: Sync only — simpler than async for now

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Class name as primary prompt source | Cleaner than docstring-heavy approach | ✓ Good — enforced in v2.0, docstrings made inert |
| Two-step decide (pick type, then fill) | Avoids slow oneOf schemas | ✓ Good — became choose_type/fill in v2.0 |
| No prev parameter | self has all needed state | ✓ Good |
| LM as tool, not executor | User calls lm.make/decide from __call__ | ✓ Resolved — v2.0 made LM implicit, graph-level |
| make/decide abstraction | May be redundant - revisit after DSPy | ✓ Resolved — kept as v1 escape hatch for custom __call__, v2 uses choose_type/fill |
| Nodes are context frames | Fields ARE prompt context, class name IS instruction, return type IS output schema | ✓ Good — core v2.0 paradigm |
| Dep(callable) for external data | Replaces v1 service injection via __call__ params | ✓ Good — DAG resolution with topo sort |
| Recall() for graph state | Backward trace search with MRO type matching | ✓ Good — replaced Bind |
| Kill Context and Bind markers | Pydantic field presence is sufficient | ✓ Good — both removed, ImportError on import |
| LM is implicit | Set once on graph, per-node via NodeConfig | ✓ Good |
| JSON structured fill | Claude CLI --json-schema for constrained decoding | ✓ Good — replaced XML, ~10-15s per fill |
| Field(description=...) for LLM hints | Explicit opt-in, docstrings are developer docs | ✓ Good — _build_plain_model preserves FieldInfo |

**v2 field annotation summary:**

| Annotation | Meaning | Source |
|------------|---------|--------|
| `Dep(fn)` | Bae calls a function to fill this field | External service/function |
| `Recall()` | Bae searches the trace to fill this field | Prior node in graph execution |
| *(none)* | LLM fills this field | Previous node's context → LLM generation |

## Known Issues

- No system prompt in any LLM backend — LLM has no framing for the fill task
- PydanticAIBackend.choose_type uses free-text string + fuzzy matching (should constrain like ClaudeCLI)
- tests/traces/json_structured_fill_reference.py drifted from real backend
- `--setting-sources ""` correlation with broken structured output (root cause unknown)

---
*Last updated: 2026-02-08 after v2.0 milestone*
