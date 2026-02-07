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
| Class name as primary prompt source | Cleaner than docstring-heavy approach | ✓ Good |
| Two-step decide (pick type, then fill) | Avoids slow oneOf schemas | ✓ Good |
| No prev parameter | self has all needed state | ✓ Good |
| LM as tool, not executor | User calls lm.make/decide from __call__ | ⚠️ Revisit (v2 removes LM from __call__) |
| make/decide abstraction | May be redundant - revisit after DSPy | ⚠️ Revisit |

### v2 Design Decisions (2026-02-07)

Discussed and agreed before v2 milestone planning.

| Decision | Rationale | Status |
|----------|-----------|--------|
| **Nodes are context frames** | A node's fields assemble the information the LLM needs to construct the next node. Fields ARE the prompt context. Class name IS the instruction. Return type IS the output schema. | Agreed |
| **Dep(callable) for external data** | `Annotated[WeatherResult, Dep(my_fn)]` — bae calls the function to populate the field. Replaces v1's service injection via __call__ params. | Agreed |
| **Dep chaining** | Dep functions can themselves declare dep-typed params. Bae resolves the DAG in topological order. | Agreed |
| **Recall() for graph state** | `Annotated[WeatherResult, Recall()]` — bae searches the trace backward for the nearest prior node with a matching field type. Replaces Bind. | Agreed |
| **Kill Context marker** | Fields with values (from deps, recall, constructor) = LLM inputs. Fields without values = LLM fills them. Pydantic already models this. Context is redundant. | Agreed |
| **Kill Bind marker** | Replaced by Recall (read side). Write side is implicit — all executed node fields are in the trace and available for Recall. | Agreed |
| **Explicit Bind (BindFor) — YAGNI** | Considered explicit write annotation (e.g., `BindFor[MyRecaller]`) for targeted publishing. Deferred — implicit writes via trace search are clean enough for now. Revisit if type collisions become a real problem. | YAGNI |
| **LM is implicit** | LM removed from __call__ signature. Set once on the graph, or per-node via NodeConfig. Nodes don't know or care about the LM — bae owns it. | Agreed |
| **Parallel fan-out (A & B) — YAGNI** | Discussed `tuple[A, B]` for parallel node production. Deferred — not needed for v2. | YAGNI |

**v2 field annotation summary:**

| Annotation | Meaning | Source |
|------------|---------|--------|
| `Dep(fn)` | Bae calls a function to fill this field | External service/function |
| `Recall()` | Bae searches the trace to fill this field | Prior node in graph execution |
| *(none)* | LLM fills this field | Previous node's context → LLM generation |

---
*Last updated: 2026-02-07 after v2 design discussion*
