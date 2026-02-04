# Requirements: Bae

**Defined:** 2026-02-04
**Core Value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing

## v1 Requirements

### Signature Generation

- [ ] **SIG-01**: Node class name becomes Signature instruction
- [ ] **SIG-02**: Node fields become InputFields
- [ ] **SIG-03**: Dep fields (typed deps like TodoList, Request) become InputFields
- [ ] **SIG-04**: Return type hint becomes OutputField (single type or union)
- [ ] **SIG-05**: Docstring used as additional instruction hint (optional)

### DSPy Integration

- [ ] **DSP-01**: LM backend uses dspy.Predict with generated Signatures
- [ ] **DSP-02**: Replace naive prompts with Signature-based prompts
- [ ] **DSP-03**: Support Pydantic models as output types (Node subclasses)
- [ ] **DSP-04**: Handle union return types (Node | OtherNode | None)

### Optimization

- [ ] **OPT-01**: Trace collection during graph execution
- [ ] **OPT-02**: BootstrapFewShot optimization with collected traces
- [ ] **OPT-03**: Save compiled prompts (JSON)
- [ ] **OPT-04**: Load compiled prompts at runtime

### Runtime

- [ ] **RUN-01**: OptimizedLM wrapper uses compiled prompts when available
- [ ] **RUN-02**: Fallback to naive prompts if no compiled version exists
- [ ] **RUN-03**: Typed deps injection into node __call__

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
| make/decide abstraction | Revisit after DSPy integration - may be redundant |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SIG-01 | Phase 1 | Pending |
| SIG-02 | Phase 1 | Pending |
| SIG-03 | Phase 1 | Pending |
| SIG-04 | Phase 1 | Pending |
| SIG-05 | Phase 1 | Pending |
| DSP-01 | Phase 2 | Pending |
| DSP-02 | Phase 2 | Pending |
| DSP-03 | Phase 2 | Pending |
| DSP-04 | Phase 2 | Pending |
| OPT-01 | Phase 3 | Pending |
| OPT-02 | Phase 3 | Pending |
| OPT-03 | Phase 3 | Pending |
| OPT-04 | Phase 3 | Pending |
| RUN-01 | Phase 4 | Pending |
| RUN-02 | Phase 4 | Pending |
| RUN-03 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-04*
