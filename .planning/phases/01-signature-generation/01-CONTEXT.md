# Phase 1: Signature Generation - Context

**Gathered:** 2026-02-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Convert Node classes to DSPy Signatures through automatic conversion. `node_to_signature()` takes a Node subclass and returns a valid `dspy.Signature` class. This phase handles the conversion only — wiring DSPy into the LM backend is Phase 2.

</domain>

<decisions>
## Implementation Decisions

### Instruction text
- Use raw class name as-is (no parsing, no space insertion)
- `AnalyzeUserIntent` becomes instruction `"AnalyzeUserIntent"`
- No special handling for acronyms, CamelCase, etc. — keeps implementation simple
- No docstring support — class name is the only instruction source

### InputField sources
- Fields annotated with `Annotated[type, SomeMarker(description="...")]` become InputFields
- Unannotated fields are internal state — they don't appear in the Signature
- Research needed: what DSPy calls its annotation marker (likely `InputField`)

### OutputField
- Comes from the Node's return type hint
- Union types (e.g., `Response | Clarify | None`) are handled by the two-step decide pattern in Phase 2, not in the Signature itself
- Single return types map directly to OutputField

### Claude's Discretion
- Exact annotation marker naming (mirror DSPy or use our own)
- Whether output type info appears in the instruction text
- How to handle nodes without any annotated fields

</decisions>

<specifics>
## Specific Ideas

- Example usage pattern Dzara mentioned:
  ```python
  repl_log: Annotated[str, Context(description="The REPL's history.")]
  ```
- Keep it simple — complexity belongs in the DSPy integration phase, not here

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-signature-generation*
*Context gathered: 2026-02-04*
