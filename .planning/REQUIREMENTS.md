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

- [x] **ROUTE-01**: Graph.run() auto-routes based on return type (union -> decide, single -> make)
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

## v2.0 Requirements — Context Frames

### Dependency Injection

- [x] **DEP2-01**: Dep(callable) resolves fields — `Annotated[T, Dep(fn)]` causes bae to call `fn` and inject the result into the field
- [x] **DEP2-02**: Dep chaining resolves recursively — dep functions with dep-typed params are resolved bottom-up via topological sort
- [x] **DEP2-03**: Circular dep chains detected at graph build time with clear error naming the cycle
- [x] **DEP2-04**: Per-run dep caching — same dep function with same resolved args returns cached result within a single graph run
- [x] **DEP2-05**: Clear error when dep callable fails — error names the dep function, the node, and the underlying exception
- [ ] **DEP2-06**: Dep fields on start node are auto-resolved before graph execution begins

### Trace & Recall

- [x] **RCL-01**: Recall() searches execution trace backward for most recent node with matching field type
- [x] **RCL-02**: Clear error when Recall target type is not found in trace
- [x] **RCL-03**: Recall on start node raises error at graph build time (no trace exists yet)

### Node Semantics

- [ ] **NODE-01**: Node fields without Dep/Recall annotations are filled by the LLM
- [ ] **NODE-02**: Start node fields (without Dep) are caller-provided via constructor
- [ ] **NODE-03**: Terminal node (returns None) fields ARE the response schema
- [ ] **NODE-04**: Class name is the LLM instruction (docstrings are optional hints)

### LM Protocol

- [ ] **LM-01**: LM is implicit — configured at graph level, removed from node `__call__` signature
- [ ] **LM-02**: Per-node LM override via NodeConfig (optional, graph-level is default)
- [ ] **LM-03**: New protocol: choose_type() picks successor type from union, fill() populates plain fields given resolved context
- [ ] **LM-04**: Dep/Recall fields are passed to LLM as context (InputFields), plain fields are LLM output (OutputFields)

### Cleanup

- [ ] **CLN-01**: Remove Context marker from codebase and exports
- [ ] **CLN-02**: Remove Bind marker from codebase and exports
- [ ] **CLN-03**: Remove incant dependency
- [ ] **CLN-04**: All tests updated to v2 patterns
- [ ] **CLN-05**: examples/ootd.py runs end-to-end with v2 runtime

## Future Requirements

- **OPT-05**: MIPROv2 optimizer (needs 50-200+ examples)
- **OPT-06**: Graph-aware optimization (optimize with topology awareness)
- **OPT-07**: Incremental compilation (update prompts without full retrain)
- **DX-01**: CLI for compilation (`bae compile`)
- **Cross-source chaining** — dep callable taking Recall param
- **Recall with filters** — recall from specific node by name
- **BindFor explicit writes** — targeted publishing to specific recallers (YAGNI)
- **Parallel fan-out** — `tuple[A, B]` for producing multiple nodes (YAGNI)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Async dep resolution | Bae is sync-only |
| Custom resolution strategies / plugin system | Three sources (Dep, Recall, LLM) are sufficient |
| Validation error retry loops | DSPy optimization may solve this |
| Dep result mutation | Dep results treated as immutable snapshots |

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
| DEP2-01 | Phase 5 | Complete |
| DEP2-02 | Phase 5 | Complete |
| DEP2-03 | Phase 5 | Complete |
| DEP2-04 | Phase 5 | Complete |
| DEP2-05 | Phase 5 | Complete |
| RCL-01 | Phase 5 | Complete |
| RCL-02 | Phase 5 | Complete |
| RCL-03 | Phase 5 | Complete |
| NODE-01 | Phase 6 | Pending |
| NODE-02 | Phase 6 | Pending |
| NODE-03 | Phase 6 | Pending |
| NODE-04 | Phase 6 | Pending |
| LM-01 | Phase 6 | Pending |
| LM-02 | Phase 6 | Pending |
| LM-03 | Phase 6 | Pending |
| LM-04 | Phase 6 | Pending |
| DEP2-06 | Phase 7 | Pending |
| CLN-03 | Phase 7 | Pending |
| CLN-01 | Phase 8 | Pending |
| CLN-02 | Phase 8 | Pending |
| CLN-04 | Phase 8 | Pending |
| CLN-05 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 19 mapped, 19 complete
- v2.0 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-02-04*
*v2.0 traceability updated: 2026-02-07*
