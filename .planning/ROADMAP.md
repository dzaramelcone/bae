# Roadmap: Bae DSPy Compilation

## Overview

This roadmap delivers DSPy prompt compilation for Bae's type-driven agent graphs. Starting from Node-to-Signature conversion (proving the core integration works), through wiring DSPy's Predict module to replace naive prompts, to trace collection and optimization, and finally production deployment with fallbacks. Each phase builds on the previous - signatures must work before integration, integration must work before optimization, optimization must work before deployment.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Signature Generation** - Convert Node classes to DSPy Signatures
- [ ] **Phase 2: DSPy Integration** - Wire LM backend to use dspy.Predict
- [ ] **Phase 3: Optimization** - Trace collection and BootstrapFewShot compilation
- [ ] **Phase 4: Production Runtime** - Load compiled prompts with fallbacks

## Phase Details

### Phase 1: Signature Generation
**Goal**: Node classes become DSPy Signatures through automatic conversion
**Depends on**: Nothing (first phase)
**Requirements**: SIG-01, SIG-02, SIG-03, SIG-04 (SIG-05 excluded per user decision)
**Plans:** 1 plan

Plans:
- [ ] 01-01-PLAN.md — TDD: node_to_signature() with Context marker

**Success Criteria** (what must be TRUE):
  1. Given a Node subclass, node_to_signature() returns a valid dspy.Signature class
  2. Signature instruction text contains the Node class name (descriptive names like "AnalyzeUserIntent" become task descriptions)
  3. Annotated fields (using Context marker) appear as InputFields in the Signature
  4. Unannotated fields are excluded (internal state)
  5. Return type hint becomes OutputField (str for Phase 1; union handling in Phase 2)

### Phase 2: DSPy Integration
**Goal**: LM calls use dspy.Predict with generated Signatures instead of naive prompts
**Depends on**: Phase 1
**Requirements**: DSP-01, DSP-02, DSP-03, DSP-04
**Success Criteria** (what must be TRUE):
  1. LM.make() and LM.decide() use dspy.Predict internally with Signatures from Phase 1
  2. Naive prompts ("Produce a {ClassName}") are replaced by Signature-based prompts
  3. Pydantic models (Node subclasses) parse correctly from dspy.Predict output
  4. Union return types (Node | OtherNode | None) work with dspy.Predict
  5. Bae's two-step decide pattern (pick type, then fill fields) works with DSPy
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
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Signature Generation | 0/1 | Planned | - |
| 2. DSPy Integration | 0/TBD | Not started | - |
| 3. Optimization | 0/TBD | Not started | - |
| 4. Production Runtime | 0/TBD | Not started | - |

---
*Roadmap created: 2026-02-04*
*Phase 1 planned: 2026-02-04*
*Depth: comprehensive (but focused milestone = 4 phases)*
