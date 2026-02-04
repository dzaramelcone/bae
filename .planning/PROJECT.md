# Bae

## What This Is

A framework for building agent graphs where nodes are Pydantic models and topology comes from type hints. DSPy compiles optimized prompts from class names, so users just name their nodes descriptively and the framework handles prompt engineering.

## Core Value

DSPy compiles agent graphs from type hints and class names - no manual prompt writing.

## Requirements

### Validated

- ✓ Node base class (Pydantic BaseModel with `__call__(lm: LM)`) — existing
- ✓ Graph discovery from return type hints — existing
- ✓ Graph execution loop — existing
- ✓ LM protocol (`make`, `decide`) — existing
- ✓ PydanticAIBackend — existing
- ✓ ClaudeCLIBackend — existing
- ✓ Terminal node detection (returns None) — existing

### Active

- [ ] DSPy compilation from class names
- [ ] DSPy compilation from docstrings (optional hints)
- [ ] NodeConfigDict for per-node config
- [ ] AgentConfigDict for graph-level config
- [ ] Traced execution for optimization

### Out of Scope

- Validation error retry loops — DSPy optimization may solve this
- Async interface — sync is simpler, revisit if needed
- Explicit deps injection — model may pass state via fields

## Context

Brownfield project with working scaffolding:
- `bae/node.py` - Node base class, type hint extraction
- `bae/graph.py` - Graph discovery, validation, run()
- `bae/lm.py` - LM protocol + backends
- `bae/compiler.py` - DSPy stubs (not wired up)
- Tests passing (unit + integration with real LLM)

Python 3.14+ required for PEP 649 (deferred annotation evaluation).

Current prompts are naive ("Produce a {ClassName}"). DSPy compilation will replace these with optimized versions based on traced executions.

## Constraints

- **Python**: 3.14+ — PEP 649 eliminates forward ref issues
- **Dependencies**: pydantic, pydantic-ai, dspy
- **Interface**: Sync only — simpler than async for now

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Class name as primary prompt source | Cleaner than docstring-heavy approach | — Pending |
| Two-step decide (pick type, then fill) | Avoids slow oneOf schemas | ✓ Good |
| No prev parameter | self has all needed state | ✓ Good |
| LM as tool, not executor | User calls lm.make/decide from __call__ | ✓ Good |

---
*Last updated: 2025-02-04 after initialization*
