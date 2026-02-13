# Bae

## What This Is

A framework for building agent graphs where nodes are Pydantic models and topology comes from type hints. Nodes are "context frames" — their fields assemble the information the LLM needs to produce the next node. Class names are instructions, return types are output schemas, and Field(description=...) provides explicit per-field hints. Three field sources: Dep(callable) for external data, Recall() for graph state, and plain fields for LLM generation. JSON structured output with constrained decoding for reliable fills. Fully async with parallel dep resolution.

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
- ✓ All LM backends async (PydanticAI, ClaudeCLI, DSPy) — v3.0
- ✓ Graph run/arun split with asyncio.run() CLI boundary — v3.0
- ✓ Node.__call__() async — v3.0
- ✓ Parallel dep resolution via asyncio.gather() — v3.0
- ✓ Sync/async Dep(callable) mixing — v3.0
- ✓ Nested model preservation in fill() — v3.0

### Active

<!-- Current scope: v4.0 Cortex -->

(Defining in v4.0 milestone)

### Out of Scope

- Bind for explicit writes — implicit trace search is clean enough (YAGNI)
- Validation error retry loops — DSPy optimization may solve this
- Dynamic fan-out (runtime N) — async __call__ with manual gather is the escape hatch
- Declarative fan-out (DepMap etc) — deferred until real use case demands it
- Engineering method graph — build after REPL works
- Semantic/vector search on context — deferred
- DuckDB query backends — deferred
- Celery distribution — YAGNI, architecture must not preclude it
- Hot reloading / self-augmenting code — deferred
- State snapshots/restore — deferred

## Current Milestone: v4.0 Cortex

**Goal:** Augmented async Python REPL where human and AI collaborate in a shared namespace — cortex is the core, bae provides agentic coherence.

**Target features:**
- Async REPL shell (prompt_toolkit + asyncio)
- Channel-based I/O with multiplexed labeled streams
- Reflective shared namespace with Python introspection
- AI agent as a first-class Python object in the namespace
- OTel span instrumentation for context tracking

## Context

Shipped v3.0 with 10,412 lines of Python.

Tech stack: Python 3.14+, Pydantic, pydantic-ai, dspy, Anthropic SDK.

Three LM backends: PydanticAIBackend, ClaudeCLIBackend, DSPyBackend — each with v1 (make/decide) and v2 (choose_type/fill) methods, all async.

Reference implementation: `examples/ootd.py` — 3-node outfit recommendation graph with deps, recalls, and LLM-filled fields.

346 tests (336 pass, 10 skip, 0 fail) + 5/5 E2E.

v4.0 architecture: Custom REPL on prompt_toolkit (not extending IPython). Three modes (NL chat, Py exec, Graph bae-run) sharing one Python namespace. Channel-based IO multiplexing with labeled streams (like Docker container prefixes). AI object lives in namespace, callable from any mode. OTel spans for context tracking. Ephemeral spawned interfaces (Ghostty tabs, browser, VS Code) for HitL checkpoints. Brain naming theme — core module = "cortex".

## Constraints

- **Python**: 3.14+ — PEP 649 eliminates forward ref issues
- **Dependencies**: pydantic, pydantic-ai, dspy, anthropic (SDK for transform_schema)
- **Interface**: Async — parallel dep resolution, subgraph composition

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
| Full async, not threading | Correct long-term play, formulaic conversion | ✓ Good — native async across all backends |
| Graph run/arun split | Sync wrapper for CLI, async for programmatic use | ✓ Good — clean boundary |
| Dep supports sync + async callables | Runtime detection via inspect.iscoroutinefunction | ✓ Good — no migration burden |
| getattr over model_dump in fill | Preserves nested BaseModel instances | ✓ Good — fixed v3.0 gap |

**Field annotation summary:**

| Annotation | Meaning | Source |
|------------|---------|--------|
| `Dep(fn)` | Bae calls a function to fill this field | External service/function |
| `Recall()` | Bae searches the trace to fill this field | Prior node in graph execution |
| *(none)* | LLM fills this field | Previous node's context → LLM generation |

## Known Issues

- PydanticAIBackend.choose_type uses free-text string + fuzzy matching — may rip out PydanticAI entirely (LM proxies making backends commodity)
- tests/traces/json_structured_fill_reference.py drifted from real backend
- Bump Python requirement to 3.14 stable when available

---
*Last updated: 2026-02-13 after v4.0 Cortex milestone start*
