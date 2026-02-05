# Phase 2: DSPy Integration - Context

**Gathered:** 2026-02-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire signatures to Graph.run() with auto-routing, dep injection, and dspy.Predict. Graph.run() introspects return types (union → decide, single → make), `__call__` with `...` body uses automatic routing, and Dep-annotated params get injected. DSPy replaces naive prompts.

</domain>

<decisions>
## Implementation Decisions

### Return type handling
- Two-step pattern (pick type, then fill) transparent to callers
- Exposed in traces: log which type was chosen (e.g., "decided: BuildCommand")
- Graph.run() returns GraphResult with .node and .trace attributes
- Trace is flat list of nodes in execution order

### DSPy failure behavior
- Parse failures: pass validation error back to LM for self-correction
- Default 1 retry (2 total attempts), configurable via parameter
- API failures (timeout, rate limit, network): retry once, then raise
- Bae exception hierarchy wrapping original errors as `__cause__`

### Dep injection API
- External deps via kwargs on run(): `graph.run(node, db=conn, cache=redis)`
- New `Bind` marker for node fields that should be available to downstream nodes
- Bind fields injected into downstream Dep params by type matching
- Type-unique constraint: multiple nodes binding same type is a graph validation error

### Claude's Discretion
- Exact GraphResult class design
- Exception class names (BaeParseError, BaeLMError, etc.)
- Retry backoff strategy for API failures
- How validation errors are formatted for LM self-correction

</decisions>

<specifics>
## Specific Ideas

- Deps "accumulate throughout the run" - Bind captures values nodes produce, Dep consumes them downstream
- Keep validation simple: type-unique Binds avoids complex resolution logic

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope

</deferred>

---

*Phase: 02-dspy-integration*
*Context gathered: 2026-02-04*
