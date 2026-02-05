# Requirements: Bae

**Defined:** 2026-02-04
**Core Value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing

## v1 Requirements

### Signature Generation

- [x] **SIG-01**: Node class name becomes Signature instruction
- [x] **SIG-02**: Context-annotated node fields become InputFields
- [x] **SIG-03**: Dep-annotated `__call__` params become InputFields
- [x] **SIG-04**: Return type hint becomes OutputField (str for now; union in Phase 2)
- [x] **SIG-05**: N/A — docstring support excluded per decision

### Graph Routing

- [x] **ROUTE-01**: Graph.run() auto-routes based on return type (union → decide, single → make)
- [x] **ROUTE-02**: `__call__` body `...` signals automatic routing
- [x] **ROUTE-03**: Custom `__call__` logic still works as escape hatch

### Dependency Injection

- [x] **DEP-01**: Dep marker for `__call__` params that need injection
- [x] **DEP-02**: Graph.run() injects Dep-annotated params via incant
- [x] **DEP-03**: Deps flow through graph without explicit field copying

### DSPy Integration

- [x] **DSP-01**: LM backend uses dspy.Predict with generated Signatures
- [x] **DSP-02**: Replace naive prompts with Signature-based prompts
- [x] **DSP-03**: Support Pydantic models as output types (Node subclasses)
- [x] **DSP-04**: Handle union return types (Node | OtherNode | None)

### Optimization

- [x] **OPT-01**: Trace collection during graph execution
- [x] **OPT-02**: BootstrapFewShot optimization with collected traces
- [x] **OPT-03**: Save compiled prompts (JSON)
- [x] **OPT-04**: Load compiled prompts at runtime

### Runtime

- [x] **RUN-01**: OptimizedLM wrapper uses compiled prompts when available
- [x] **RUN-02**: Fallback to naive prompts if no compiled version exists

## v2 Requirements

### Advanced Optimization

- **OPT-05**: MIPROv2 optimizer (needs 50-200+ examples)
- **OPT-06**: Graph-aware optimization (optimize with topology awareness)
- **OPT-07**: Incremental compilation (update prompts without full retrain)

### Developer Experience

- **DX-01**: CLI for compilation (`bae compile`)
- **DX-02**: Compilation metrics/reporting
- **DX-03**: A/B testing compiled vs naive prompts

## Out of Scope

| Feature | Reason |
|---------|--------|
| Async interface | DSPy recommends starting sync; revisit if needed |
| Validation retry loops | DSPy optimization may solve validation issues |
| Custom adapters | Use DSPy's ChatAdapter (default) for now |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SIG-01 | Phase 1 | Complete |
| SIG-02 | Phase 1 | Complete |
| SIG-04 | Phase 1 | Complete |
| SIG-05 | Phase 1 | N/A (excluded) |
| SIG-03 | Phase 1.1 | Complete |
| DEP-01 | Phase 1.1 | Complete |
| ROUTE-01 | Phase 2 | Complete |
| ROUTE-02 | Phase 2 | Complete |
| ROUTE-03 | Phase 2 | Complete |
| DEP-02 | Phase 2 | Complete |
| DEP-03 | Phase 2 | Complete |
| DSP-01 | Phase 2 | Complete |
| DSP-02 | Phase 2 | Complete |
| DSP-03 | Phase 2 | Complete |
| DSP-04 | Phase 2 | Complete |
| OPT-01 | Phase 3 | Complete |
| OPT-02 | Phase 3 | Complete |
| OPT-03 | Phase 3 | Complete |
| OPT-04 | Phase 3 | Complete |
| RUN-01 | Phase 4 | Complete |
| RUN-02 | Phase 4 | Complete |

**Coverage:**
- v1 requirements: 19 total (3 new routing/dep reqs)
- Mapped to phases: 19
- Unmapped: 0

---
*Requirements defined: 2026-02-04*
*Traceability updated: 2026-02-04*
