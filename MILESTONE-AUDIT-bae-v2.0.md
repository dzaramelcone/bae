---
milestone: v2.0
audited: 2026-02-08
status: passed
scores:
  requirements: 22/22
  phases: 4/4
  integration: 11/11
  flows: 5/5
gaps:
  requirements: []
  integration: []
  flows: []
tech_debt:
  - phase: 08-cleanup-migration
    items:
      - "ootd.py E2E validated structurally only — full LLM E2E requires API key"
---

# Milestone Audit: v2.0 Context Frames

**Audited:** 2026-02-08
**Status:** PASSED
**Milestone Goal:** Redesign the node API around the "nodes as context frames" paradigm — Dep/Recall field annotations, implicit LM, clean start/terminal semantics.

## Requirements Coverage

**Score:** 22/22 v2.0 requirements satisfied

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEP2-01: Dep(callable) resolves fields | Phase 5 | Complete |
| DEP2-02: Dep chaining resolves recursively | Phase 5 | Complete |
| DEP2-03: Circular dep chains detected at build time | Phase 5 | Complete |
| DEP2-04: Per-run dep caching | Phase 5 | Complete |
| DEP2-05: Clear error when dep callable fails | Phase 5 | Complete |
| DEP2-06: Dep fields on start node auto-resolved | Phase 7 | Complete |
| RCL-01: Recall searches trace backward | Phase 5 | Complete |
| RCL-02: Clear error when Recall target not found | Phase 5 | Complete |
| RCL-03: Recall on start node raises error at build time | Phase 5 | Complete |
| NODE-01: Plain fields filled by LLM | Phase 6 | Complete |
| NODE-02: Start node fields are caller-provided | Phase 6 | Complete |
| NODE-03: Terminal node fields ARE the response schema | Phase 6 | Complete |
| NODE-04: Class name is the LLM instruction | Phase 6 | Complete |
| LM-01: Implicit LM (graph-level config) | Phase 6 | Complete |
| LM-02: Per-node LM override via NodeConfig | Phase 6 | Complete |
| LM-03: choose_type/fill protocol methods | Phase 6 | Complete |
| LM-04: Dep/Recall → InputField, plain → OutputField | Phase 6 | Complete |
| CLN-01: Context marker removed | Phase 8 | Complete |
| CLN-02: Bind marker removed | Phase 8 | Complete |
| CLN-03: incant dependency removed | Phase 7 | Complete |
| CLN-04: All tests use v2 patterns | Phase 8 | Complete |
| CLN-05: ootd.py runs with v2 runtime | Phase 8 | Complete |

## Phase Verification Summary

| Phase | Status | Score | Tests |
|-------|--------|-------|-------|
| 5. Markers & Resolver | ✓ Passed | 5/5 | 44 tests |
| 6. Node & LM Protocol | ✓ Passed | 5/5 | 57 tests |
| 7. Integration | ✓ Passed | 4/4 | 300 total |
| 8. Cleanup & Migration | ✓ Passed | 4/4 | 285 total |

**Final test suite:** 285 passed, 5 skipped (PydanticAI API key), 0 failures

## Cross-Phase Integration

**Score:** 11/11 core connections verified

| From | To | Via | Status |
|------|----|----|--------|
| classify_fields (P5) | node_to_signature (P6) | Direct call | ✓ |
| Dep/Recall markers (P5) | resolve_fields (P5) | Type checking | ✓ |
| RecallError (P5) | recall_from_trace (P5) | Raise on no match | ✓ |
| resolve_fields (P5) | Graph.run (P7) | Execution loop | ✓ |
| _wants_lm (P6) | Graph.run (P7) | Custom __call__ routing | ✓ |
| choose_type/fill (P6) | Graph.run (P7) | Ellipsis body routing | ✓ |
| DepError (P7) | Graph.run (P7) | Dep failure wrapping | ✓ |
| node_to_signature (P6) | DSPyBackend.fill (P6) | Signature generation | ✓ |
| GraphResult.result (P6) | Graph.run return (P7) | Trace[-1] property | ✓ |
| Graph.run (P7) | CompiledGraph.run (P8) | Delegation | ✓ |
| bae/__init__.py | All modules | Package exports | ✓ |

## E2E Flow Verification

**Score:** 5/5 flows complete

1. **Basic graph execution** (start → terminal) ✓
2. **Dep resolution → custom __call__ → result** ✓
3. **Multi-node Dep → Recall → LM fill** ✓
4. **CompiledGraph optimization pipeline** ✓
5. **Error propagation (DepError with trace)** ✓

## Tech Debt

**1 item (non-blocking):**

- **Phase 8:** ootd.py validated structurally (imports, graph topology, dep chaining) but not with a real LLM call. Full E2E requires DSPy LM configuration. The `--run-e2e` pytest marker was added for future CI integration.

## Orphaned Code

**None detected.** All 30 exported symbols in `bae/__init__.py` have consumers. All v1 markers (Context, Bind, Dep.description, incant) fully removed.

## Package API

30 exports in logical groups:
- Core types: Node, Graph, GraphResult, NodeConfig
- Markers: Dep, Recall
- Resolver: classify_fields, resolve_fields
- LM backends: LM, DSPyBackend, PydanticAIBackend, ClaudeCLIBackend, OptimizedLM
- Compiler: node_to_signature, compile_graph, create_optimized_lm
- Optimizer: trace_to_examples, optimize_node, save_optimized, load_optimized, node_transition_metric
- Exceptions: BaeError, BaeParseError, BaeLMError, DepError, FillError, RecallError

---
*Audit completed: 2026-02-08*
*Auditor: Claude (gsd-integration-checker + orchestrator)*
