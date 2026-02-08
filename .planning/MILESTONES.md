# Project Milestones: Bae

## v2.0 Context Frames (Shipped: 2026-02-08)

**Delivered:** Redesigned the node API around "nodes as context frames" — Dep/Recall field annotations, implicit LM, JSON structured fill with constrained decoding, and explicit Field(description=...) hints.

**Phases completed:** 5-10 (21 plans total)

**Key accomplishments:**
- Dep(callable) field annotation with topological DAG resolution, dep chaining, per-run caching
- Recall() trace search for graph state — backward type-matching with MRO support
- Graph.run() v2: resolve deps → resolve recalls → LM fill, with implicit graph-level LM
- Removed v1 markers (Context, Bind), incant dependency, and all legacy patterns
- JSON structured fill via Claude CLI constrained decoding (--json-schema), replacing XML prompts
- Docstrings made inert — class name is the instruction, Field(description=...) for explicit LLM hints

**Stats:**
- 92 files created/modified
- 9,297 lines of Python (2,718 source + 6,298 test)
- 6 phases, 21 plans, 106 commits
- 2 days (2026-02-07 → 2026-02-08)

**Git range:** `docs(05): research` → `docs: track v4.0 todos`

**What's next:** System prompt for LLM backends, OTel observability with Jaeger, structured logging, PydanticAI backend consistency

---

## v1.0 DSPy Compilation (Shipped: 2026-02-05)

**Delivered:** DSPy compiles agent graphs from type hints and class names — node_to_signature, auto-routing, BootstrapFewShot optimization, compiled prompt loading.

**Phases completed:** 1-4 (13 plans total)

**Key accomplishments:**
- node_to_signature() converts Node subclasses to dspy.Signature automatically
- Graph.run() auto-routes via return type introspection (union → decide, single → make)
- BootstrapFewShot optimization with trace-to-Example conversion
- OptimizedLM with compiled prompt registry and naive fallback

**Stats:**
- 4 phases, 13 plans
- 1 day (2026-02-04 → 2026-02-05)

**Git range:** `docs: initialize project` → `docs(phase-4): complete Production Runtime phase`

**What's next:** v2.0 Context Frames — Dep/Recall field annotations, implicit LM

---
