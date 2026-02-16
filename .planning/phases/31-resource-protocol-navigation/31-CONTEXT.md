# Phase 31: Resource Protocol + Navigation - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Foundational protocol that lets the agent navigate a self-describing resource tree where tools operate on the current resource context. Includes: resourcespace protocol, registry, navigation state, tool dispatch routing, and output pruning. Individual resourcespaces (source, tasks, memory) are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Resource entry display
- Functions table columns: system tool override (if applicable) → function name → one-line procedural description
- Docstrings are result-oriented: describe what the agent gets back, not what the function does
- Python hints for advanced `<run>` operations in a separate "Advanced:" block after the functions table
- Entry always includes resource state (e.g., current path, item count) — agent immediately knows where it is
- Entry includes breadcrumb showing parent chain (e.g., "home > source > meta")

### Navigation feel
- `.nav()` shows an indented tree view of the full navigable structure from current position
- Tree marks the agent's current position with a "you are here" indicator
- Tree depth capped at 2-3 levels; collapsed nodes show "+N more" to stay within token budget
- Tree updates on next `nav()` call, not automatically when registry changes
- `@resource()` mentions are navigable anywhere they appear — tool results, errors, nav listings
- Navigation supports both stack-based `back()` and explicit direct jumps
- Direct jump to any target including nested (e.g., `source.meta()` from anywhere, not just from `source()`)
- Brief transition message on navigation (e.g., "Left source → entering tasks")
- `homespace()` returns to root, shows root nav tree (no dashboard — that's Phase 36)

### Error messaging
- Protocol wraps all resource errors into a consistent format — uniform experience across resources
- Human-readable messages only, no error codes — the consumer is an AI
- Unsupported tool: fact + nav hint pointing to the right resource (e.g., "source does not support edit. Try @source.meta()")
- Bad navigation: error + closest match fuzzy correction (e.g., "No resource 'sourc'. Did you mean @source()?")
- Errors always include @resource() hyperlinks when a better resource exists for the operation
- Tools at homespace root auto-dispatch to sensible defaults (e.g., `read()` at root lists resourcespaces)
- Multiple errors in a single operation: collect all and report together, not fail-fast
- Errors subject to the same 500 token cap as all other output

### Pruning
- 500 token hard cap — protocol-level constant, not configurable per-resource
- Structure-first preservation: keep headings, counts, shape; trim content details
- Protocol layer handles all pruning — generic, not resource-specific
- Deterministic algorithm: no LM calls, algorithmic truncation with structure preservation
- Always indicate when pruning happened (e.g., "[pruned: 42 → 10 items]") so agent knows more exists

### Claude's Discretion
- Whether to mark unvisited vs visited targets in the nav tree
- Exact breadcrumb formatting
- Specific tree indentation and collapse thresholds
- Pruning algorithm internals (which items to keep, how to count structure tokens)

</decisions>

<specifics>
## Specific Ideas

- Functions table reads like a man page synopsis: tool override, name, result description
- Nav tree feels like a filesystem `tree` command with a "you are here" marker
- Errors are helpful redirections, not just rejections — always point somewhere useful
- Transitions between resources are announced briefly, like changing directories

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 31-resource-protocol-navigation*
*Context gathered: 2026-02-16*
