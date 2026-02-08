# Phase 7: Integration - Context

**Gathered:** 2026-02-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Graph.run() assembles context frames from all sources (deps, recalls, LM fill) and executes the full node lifecycle. Replaces incant with bae's own resolver. End-to-end multi-node graph execution with the v2 field system.

Requirements: DEP2-06, CLN-03

</domain>

<decisions>
## Implementation Decisions

### Start node bootstrapping
- Caller passes a **node instance** to Graph.run() (not kwargs)
- Start node deps resolve **inside the first loop iteration** (same path as all other nodes, not a special pre-step)
- Dep functions on the start node are **independent** of caller-provided field values (pure external data sources)
- If dep resolution fails on the start node, raise **BaeError** (wrapped) with context — same as any other node
- Note: success criterion #1 wording says "before graph execution begins" but the decision is to resolve inside the first iteration. Criterion needs minor reword to match.

### Execution loop ordering
- Each iteration: resolve deps → resolve recalls → set on self → invoke `__call__`
- `__call__` always invoked (even for `...` body nodes). Ellipsis body = LM handles routing+fill. Custom body = user logic runs
- LM fills the **next** node (the type returned by `__call__`). Union return = choose_type, single type = fill, None = terminal
- Context for LM fill formatted as **model_dump_xml** from the BaseModel (XML serialization, not flat dict)
- LM fill creates a new node instance (model_construct + validation). Validation failure → error messages fed back to LM for correction
- Retry limit on LM fill validation is **configurable** (default exists, overridable per-node or per-graph)
- v1 self-correction mechanism (dspy.Predict retry) stays as-is
- Terminal node (returns None) is **included in the trace**. GraphResult.result = trace[-1]

### Custom `__call__` behavior
- Deps and recalls are **set on self** before `__call__` runs. Custom logic reads `self.field_name`
- `__call__` dep params are **dropped** entirely in v2. Only `self` and optionally an LM-typed parameter
- LM is passed as a **`__call__` argument** (not set on self). Detected by **type hint** on the parameter, not by name

### incant removal
- incant is **removed from pyproject.toml** in this phase (clean cut, not deferred to Phase 8)
- v1 tests that verify incant injection behavior are **deleted and replaced** with v2 integration tests
- `_wants_lm` updated to check for LM protocol **type hint** in `__call__` params, not parameter name "lm"

### Error propagation model
- Error hierarchy: **BaeError** base → **DepError**, **RecallError**, **FillError** subclasses
- All errors carry **structured attributes** (node_type, field_name, attempts, etc.) AND a good `__str__` — both programmatic and human-readable
- Error messages are **terse + context**: `'DepError: fetch_user failed on AnalyzeIntent.user_data'` — no suggestions
- Dep failures **raise immediately** (fail-fast, no skip-and-continue)
- Dep errors use **exception chaining**: `raise DepError(...) from original_exception`
- Partial trace **attached as attribute** on the exception: `err.trace`
- RecallError raised at **graph build time** via static analysis — covers both obvious cases (type never in graph) AND path-dependent cases (type reachable but specific paths skip it)
- Runtime recall miss is also RecallError (same type)
- FillError is a **specific type** with node type, last validation errors, and attempt count

### Iteration guard
- Max iteration limit with **low default (10)** — forces users to set it explicitly for unbounded graphs
- Configurable per-graph
- **0 = infinite** (sentinel value, no limit)

### Observability
- **Python standard logging** at DEBUG level during Graph.run() (node entered, deps resolved, etc.)
- Callers opt-in via log config. Silent by default at INFO+

</decisions>

<specifics>
## Specific Ideas

- Context for LM fill uses `model_dump_xml` format — XML serialization of the BaseModel, not a flat dict or JSON
- `_wants_lm` detects LM protocol type by inspecting `__call__` parameter type hints (not name-based detection)
- Static recall analysis at graph build time should cover path-dependent reachability, not just "type exists in graph"
- Iteration limit default of ~10 is intentionally low to be pedagogical — users learn fast they need to configure it

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-integration*
*Context gathered: 2026-02-07*
