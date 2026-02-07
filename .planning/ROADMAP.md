# Roadmap: Bae DSPy Compilation

## Milestones

- v1.0 DSPy Compilation - Phases 1-4 (shipped 2026-02-05)
- v2.0 Context Frames - Phases 5-8 (in progress)

## Phases

<details>
<summary>v1.0 DSPy Compilation (Phases 1-4) - SHIPPED 2026-02-05</summary>

### Phase 1: Signature Generation
**Goal**: Node classes become DSPy Signatures through automatic conversion
**Depends on**: Nothing (first phase)
**Requirements**: SIG-01, SIG-02, SIG-03, SIG-04 (SIG-05 excluded per user decision)
**Plans:** 1 plan

Plans:
- [x] 01-01-PLAN.md — TDD: node_to_signature() with Context marker

**Success Criteria** (what must be TRUE):
  1. Given a Node subclass, node_to_signature() returns a valid dspy.Signature class
  2. Signature instruction text contains the Node class name (descriptive names like "AnalyzeUserIntent" become task descriptions)
  3. Annotated fields (using Context marker) appear as InputFields in the Signature
  4. Unannotated fields are excluded (internal state)
  5. Return type hint becomes OutputField (str for Phase 1; union handling in Phase 2)

### Phase 1.1: Deps & Signature Extension (INSERTED)
**Goal**: Dep-annotated `__call__` params become InputFields in Signatures
**Depends on**: Phase 1
**Requirements**: SIG-03, DEP-01
**Plans:** 1 plan

**Success Criteria** (what must be TRUE):
  1. Dep marker exists in bae/markers.py (frozen dataclass like Context)
  2. node_to_signature() reads `__call__` params for Dep-annotated types
  3. Dep-annotated params become InputFields in the Signature
  4. Both Context fields and Dep params appear as InputFields

Plans:
- [x] 01.1-01-PLAN.md — TDD: Dep marker and signature extension

### Phase 2: DSPy Integration
**Goal**: Graph.run() auto-routes and injects deps; LM uses dspy.Predict
**Depends on**: Phase 1.1
**Requirements**: ROUTE-01, ROUTE-02, ROUTE-03, DEP-02, DEP-03, DSP-01, DSP-02, DSP-03, DSP-04
**Plans:** 5 plans

Plans:
- [x] 02-01-PLAN.md — TDD: Foundation types (GraphResult, Bind, exceptions) + validation
- [x] 02-02-PLAN.md — TDD: Auto-routing (return type introspection, ellipsis body)
- [x] 02-03-PLAN.md — TDD: DSPy Predict backend with self-correction
- [x] 02-04-PLAN.md — TDD: Dep injection via incant
- [x] 02-05-PLAN.md — Integration wiring and verification

**Success Criteria** (what must be TRUE):
  1. Graph.run() introspects return type: union -> decide, single type -> make
  2. `__call__` with `...` body uses automatic routing (no explicit lm.decide/make)
  3. Custom `__call__` logic still works as escape hatch
  4. Dep-annotated `__call__` params are injected by Graph.run() via incant
  5. dspy.Predict replaces naive prompts for LM calls
  6. Pydantic models (Node subclasses) parse correctly from dspy.Predict output
  7. Union return types work with two-step pattern (pick type, then fill)

### Phase 3: Optimization
**Goal**: Collect execution traces and compile optimized prompts with BootstrapFewShot
**Depends on**: Phase 2
**Requirements**: OPT-01, OPT-02, OPT-03, OPT-04
**Plans:** 4 plans

Plans:
- [x] 03-01-PLAN.md — TDD: Trace-to-Example conversion and metric function
- [x] 03-02-PLAN.md — TDD: BootstrapFewShot optimization
- [x] 03-03-PLAN.md — TDD: Save/Load compiled prompts
- [x] 03-04-PLAN.md — Wire optimizer into CompiledGraph + exports

**Success Criteria** (what must be TRUE):
  1. Graph.run() captures (input_node, output_node) pairs as execution traces
  2. Traces convert to dspy.Example format for optimizer consumption
  3. BootstrapFewShot optimizer runs on collected traces and produces optimized modules
  4. Compiled prompts serialize to JSON and load back correctly
  5. Optimized modules produce better outputs than naive prompts (measured by metric function)

### Phase 4: Production Runtime
**Goal**: Production graphs load compiled prompts at startup with graceful fallbacks
**Depends on**: Phase 3
**Requirements**: RUN-01, RUN-02
**Plans:** 2 plans

Plans:
- [x] 04-01-PLAN.md — TDD: OptimizedLM with predictor registry and fallback
- [x] 04-02-PLAN.md — CompiledGraph integration and package exports

**Success Criteria** (what must be TRUE):
  1. OptimizedLM wrapper loads compiled prompts at graph startup
  2. OptimizedLM uses compiled prompts when available for a node type
  3. OptimizedLM falls back to naive prompts for nodes without compiled versions
  4. Observability shows which nodes are using optimized vs naive prompts

</details>

### v2.0 Context Frames (In Progress)

**Milestone Goal:** Redesign the node API around the "nodes as context frames" paradigm — Dep/Recall field annotations, implicit LM, clean start/terminal semantics.

#### Phase 5: Markers & Resolver
**Goal**: Field-level dependency resolution and trace recall work correctly in isolation
**Depends on**: Phase 4 (v1.0 complete)
**Requirements**: DEP2-01, DEP2-02, DEP2-03, DEP2-04, DEP2-05, RCL-01, RCL-02, RCL-03
**Plans**: TBD

**Success Criteria** (what must be TRUE):
  1. `Annotated[T, Dep(fn)]` field causes the resolver to call `fn` and return the result for injection
  2. Dep functions whose parameters are themselves dep-typed resolve bottom-up via topological sort (chaining works)
  3. Circular dep chains raise a clear error naming the cycle at graph build time
  4. Recall() searches a trace list backward and returns the most recent node field matching the target type
  5. Recall on a start node raises an error at graph build time (no trace exists yet)

#### Phase 6: Node & LM Protocol
**Goal**: Nodes declare field sources through annotations; LM fills only what it should, configured at graph level
**Depends on**: Phase 5
**Requirements**: NODE-01, NODE-02, NODE-03, NODE-04, LM-01, LM-02, LM-03, LM-04
**Plans**: TBD

**Success Criteria** (what must be TRUE):
  1. Node fields without Dep/Recall annotations are identified as LLM-filled; fields with Dep/Recall are identified as context
  2. Start node fields (without Dep) are treated as caller-provided input, not LLM-generated
  3. Terminal node (returns None) fields ARE the graph's response schema
  4. LM is configured once at graph level and not passed to node `__call__`; per-node override via NodeConfig works
  5. LM protocol exposes `choose_type()` (pick successor from union) and `fill()` (populate plain fields given resolved context)

#### Phase 7: Integration
**Goal**: Graph.run() assembles context frames from all sources and executes the full node lifecycle
**Depends on**: Phase 5, Phase 6
**Requirements**: DEP2-06, CLN-03
**Plans**: TBD

**Success Criteria** (what must be TRUE):
  1. Dep fields on the start node are auto-resolved before graph execution begins (caller provides non-dep fields, bae resolves dep fields)
  2. Each execution loop iteration resolves deps, resolves recalls, then has LM fill remaining fields — in that order
  3. The incant dependency is removed; dep resolution uses bae's own resolver
  4. A multi-node graph with deps, recalls, and LLM-filled fields runs end-to-end producing correct results

#### Phase 8: Cleanup & Migration
**Goal**: v1 markers are gone, all tests use v2 patterns, reference example works end-to-end
**Depends on**: Phase 7
**Requirements**: CLN-01, CLN-02, CLN-04, CLN-05
**Plans**: TBD

**Success Criteria** (what must be TRUE):
  1. Context marker is removed from codebase and package exports — importing it raises ImportError
  2. Bind marker is removed from codebase and package exports — importing it raises ImportError
  3. All tests use v2 patterns (Dep(callable) on fields, Recall(), implicit LM) — no v1 marker usage remains
  4. `examples/ootd.py` runs end-to-end with the v2 runtime and produces a valid outfit recommendation

## Progress

**Execution Order:**
Phases execute in numeric order: 5 -> 6 -> 7 -> 8

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Signature Generation | v1.0 | 1/1 | Complete | 2026-02-04 |
| 1.1 Deps & Signature Extension | v1.0 | 1/1 | Complete | 2026-02-04 |
| 2. DSPy Integration | v1.0 | 5/5 | Complete | 2026-02-05 |
| 3. Optimization | v1.0 | 4/4 | Complete | 2026-02-05 |
| 4. Production Runtime | v1.0 | 2/2 | Complete | 2026-02-05 |
| 5. Markers & Resolver | v2.0 | 0/TBD | Not started | - |
| 6. Node & LM Protocol | v2.0 | 0/TBD | Not started | - |
| 7. Integration | v2.0 | 0/TBD | Not started | - |
| 8. Cleanup & Migration | v2.0 | 0/TBD | Not started | - |

---
*Roadmap created: 2026-02-04*
*v1.0 shipped: 2026-02-05*
*v2.0 roadmap created: 2026-02-07*
*Depth: comprehensive*
