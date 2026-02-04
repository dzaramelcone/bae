# Roadmap: Bae DSPy Compilation

## Overview

This roadmap delivers DSPy prompt compilation for Bae's type-driven agent graphs. Starting from Node-to-Signature conversion (proving the core integration works), through wiring DSPy's Predict module to replace naive prompts, to trace collection and optimization, and finally production deployment with fallbacks. Each phase builds on the previous - signatures must work before integration, integration must work before optimization, optimization must work before deployment.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Signature Generation** - Convert Node classes to DSPy Signatures ✓
- [x] **Phase 1.1: Deps & Signature Extension** - Dep marker, __call__ params become InputFields (INSERTED) ✓
- [ ] **Phase 2: DSPy Integration** - Auto-routing, dep injection, dspy.Predict
- [ ] **Phase 3: Optimization** - Trace collection and BootstrapFewShot compilation
- [ ] **Phase 4: Production Runtime** - Load compiled prompts with fallbacks

## Phase Details

### Phase 1: Signature Generation
**Goal**: Node classes become DSPy Signatures through automatic conversion
**Depends on**: Nothing (first phase)
**Requirements**: SIG-01, SIG-02, SIG-03, SIG-04 (SIG-05 excluded per user decision)
**Plans:** 1 plan

Plans:
- [x] 01-01-PLAN.md — TDD: node_to_signature() with Context marker ✓

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
- [x] 01.1-01-PLAN.md — TDD: Dep marker and signature extension ✓

### Phase 2: DSPy Integration
**Goal**: Graph.run() auto-routes and injects deps; LM uses dspy.Predict
**Depends on**: Phase 1.1
**Requirements**: ROUTE-01, ROUTE-02, ROUTE-03, DEP-02, DEP-03, DSP-01, DSP-02, DSP-03, DSP-04
**Success Criteria** (what must be TRUE):
  1. Graph.run() introspects return type: union → decide, single type → make
  2. `__call__` with `...` body uses automatic routing (no explicit lm.decide/make)
  3. Custom `__call__` logic still works as escape hatch
  4. Dep-annotated `__call__` params are injected by Graph.run() via incant
  5. dspy.Predict replaces naive prompts for LM calls
  6. Pydantic models (Node subclasses) parse correctly from dspy.Predict output
  7. Union return types work with two-step pattern (pick type, then fill)
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Optimization
**Goal**: Collect execution traces and compile optimized prompts with BootstrapFewShot
**Depends on**: Phase 2
**Requirements**: OPT-01, OPT-02, OPT-03, OPT-04
**Success Criteria** (what must be TRUE):
  1. Graph.run() captures (input_node, output_node) pairs as execution traces
  2. Traces convert to dspy.Example format for optimizer consumption
  3. BootstrapFewShot optimizer runs on collected traces and produces optimized modules
  4. Compiled prompts serialize to JSON and load back correctly
  5. Optimized modules produce better outputs than naive prompts (measured by metric function)
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Production Runtime
**Goal**: Production graphs load compiled prompts at startup with graceful fallbacks
**Depends on**: Phase 3
**Requirements**: RUN-01, RUN-02
**Success Criteria** (what must be TRUE):
  1. OptimizedLM wrapper loads compiled prompts at graph startup
  2. OptimizedLM uses compiled prompts when available for a node type
  3. OptimizedLM falls back to naive prompts for nodes without compiled versions
  4. Observability shows which nodes are using optimized vs naive prompts
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 1.1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Signature Generation | 1/1 | Complete ✓ | 2026-02-04 |
| 1.1 Deps & Signature Extension | 1/1 | Complete ✓ | 2026-02-04 |
| 2. DSPy Integration | 0/TBD | Not started | - |
| 3. Optimization | 0/TBD | Not started | - |
| 4. Production Runtime | 0/TBD | Not started | - |

---
*Roadmap created: 2026-02-04*
*Phase 1 planned: 2026-02-04*
*Phase 1.1 planned: 2026-02-04*
*Depth: comprehensive (but focused milestone = 4 phases)*
