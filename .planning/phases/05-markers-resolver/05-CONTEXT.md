# Phase 5: Markers & Resolver - Context

**Gathered:** 2026-02-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Field-level dependency resolution and trace recall work correctly in isolation. The resolver populates node fields from non-LLM sources (dep functions and trace recall). This phase does NOT include LM fill, graph-level LM config, or start/terminal node semantics — those are Phases 6-7.

</domain>

<decisions>
## Implementation Decisions

### Dep function contract
- Any Python callable works (functions, lambdas, bound methods, classes with `__call__`)
- Dep functions declare their own dependencies using `Annotated[T, Dep(other_fn)]` on params — mirrors the field annotation pattern
- Dep functions are standalone: no access to the node instance or graph state
- Return type validated via MRO (`issubclass(return_type, field_type)`) — subclasses are valid
- Return type check happens at graph construction time (requires return type annotation on dep functions)
- Sync-only for Phase 5; async dep support deferred

### Recall matching rules
- Type matching uses MRO (`issubclass`) — consistent with dep type checking
- Multiple matches: most recent wins (walk trace backward, take first match)
- No filter params on Recall() — YAGNI; use more specific types if needed
- Recall searches LLM-filled fields only — dep-filled fields are infrastructure, not reasoning trace
- Recall on a start node is a build-time error (no trace exists yet)

### Error & edge case semantics
- Dep function runtime exceptions propagate raw — no wrapping
- Recall finding no match raises RecallError
- Circular dep chains detected at graph construction time via topological sort, error names the cycle
- Dep return type mismatch (MRO check fails) is a graph construction time error

### Resolver execution model
- Per-run dep caching keyed by function identity (like FastAPI's Depends) — same function = cached regardless of args
- No cache opt-out flag — YAGNI
- Resolution order within a node: all fields in declaration order (deps and recalls interleaved, not separated)
- Topological sort for dep chain resolution across the DAG (graphlib.TopologicalSorter)

### Claude's Discretion
- Exact resolver class/function structure
- Internal data structures for the dep DAG
- How `model_construct()` integrates with field population
- Test fixture design

</decisions>

<specifics>
## Specific Ideas

- "Like FastAPI's Depends" — dep caching by callable identity within a single run
- Dep param annotation mirrors field annotation: `Annotated[T, Dep(fn)]` in both places
- Recall is about recalling LLM *reasoning*, not infrastructure data — hence LLM-filled fields only

</specifics>

<deferred>
## Deferred Ideas

- **Dep errors as LM context**: Annotate deps so that when they raise, the exception + traceback is fed to the LM as context rather than crashing the graph. Could be a field on `Dep()` or a union type with errors. Belongs in Phase 6/7 where LM fill exists.
- **Async dep functions**: Support async callables in the resolver. Deferred until Graph.run() itself goes async (avoids sync-calling-async headache).
- **Recall filters**: `Recall(from_node=SomeNode)` to restrict trace search. YAGNI for now.
- **Cache opt-out**: `Dep(fn, cache=False)` for fresh calls. YAGNI for now.

</deferred>

---

*Phase: 05-markers-resolver*
*Context gathered: 2026-02-07*
