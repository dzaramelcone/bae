# Phase 6: Node & LM Protocol - Context

**Gathered:** 2026-02-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Nodes declare field sources through annotations; LM fills only what it should, configured at graph level. This phase defines the node API contract (`__call__`, field classification, start/terminal semantics) and the LM protocol (`choose_type`/`fill`), configured once at graph level with per-node overrides via NodeConfig.

</domain>

<decisions>
## Implementation Decisions

### `__call__` contract
- `__call__` stays on every node — it carries the return type hint that defines graph edges
- `...` body = bae handles fill + route automatically (same convention as v1)
- Custom body = full escape hatch — user writes their own logic, constructs and returns the next node instance
- `lm: LM` parameter is opt-in injection: declare it in `__call__` signature and bae passes it; don't declare it and bae doesn't
- In escape hatch, user returns a constructed node instance (not a type for bae to fill)
- User can call `lm.choose_type()` / `lm.fill()` directly in escape hatch if they opted into the `lm` param

### NodeConfig shape
- Class-level attribute following Pydantic's `model_config` pattern: `node_config = NodeConfig(lm=...)`
- LM-only for now (YAGNI — expand later if needed)
- No `node_config` = inherit graph-level LM
- `node_config` with no `lm` set = also falls through to graph-level LM (only overrides what's explicitly set)

### Terminal node as response
- `Graph.run()` returns `GraphResult` wrapping the terminal node + execution trace
- Graph optionally generic: `Graph[TerminalType]` — if specified, `.result` is typed as `TerminalType`; otherwise `.result` is `Node`
- `.trace` includes ALL nodes: start + intermediate + terminal (complete execution history)

### Claude's Discretion
- `choose_type()` / `fill()` internal implementation and signature details
- How `...` body detection works (inspect-based, same as v1 likely)
- Field classification integration with Phase 5's `classify_fields()`
- Start node detection mechanism (topology-based)

</decisions>

<specifics>
## Specific Ideas

- NodeConfig follows Pydantic's `model_config` naming convention — familiar to Pydantic users
- Escape hatch is full control: user constructs the instance, can use LM methods if needed, returns the concrete next node
- Generic Graph is opt-in ergonomics, not required — if you don't care about typing `.result`, just use `Graph`

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-node-lm-protocol*
*Context gathered: 2026-02-07*
