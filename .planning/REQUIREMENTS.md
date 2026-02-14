# Requirements: Bae

**Defined:** 2026-02-14
**Core Value:** DSPy compiles agent graphs from type hints and class names - no manual prompt writing

## v5.0 Requirements

Requirements for v5.0 Stream Views milestone. Each maps to roadmap phases.

### AI Hardening

- [ ] **AIHR-01**: AI system prompt includes explicit no-tools constraint and fewshot showing Python-only execution convention
- [ ] **AIHR-02**: Eval loop detects terse tool call patterns in AI responses and translates to Python equivalents with argument parsing
- [ ] **AIHR-03**: Read tool call `<R:filepath>` translated to file read with truncated output
- [ ] **AIHR-04**: Edit tool call `<E:filepath:line_start-line_end>` translated to file region read and edit
- [ ] **AIHR-05**: Write tool call `<W:filepath>` translated to file write with content from response
- [ ] **AIHR-06**: Glob tool call `<G:pattern>` translated to glob search with truncated results
- [ ] **AIHR-07**: Grep tool call `<Grep:pattern>` translated to content search with truncated results
- [ ] **AIHR-08**: User sees visible indicator when tool call is translated and executed

### Execution Convention

- [ ] **EXEC-01**: AI can distinguish between executable code and illustrative/pseudocode in its responses
- [ ] **EXEC-02**: Only code blocks explicitly marked as executable are extracted and run by the eval loop

### Multi-View Framework

- [ ] **VIEW-01**: ViewFormatter protocol defines the display strategy interface
- [ ] **VIEW-02**: Channel._display() delegates to formatter when set, preserving existing behavior when unset
- [ ] **VIEW-03**: UserView renders AI code execution as framed Rich Panel with syntax highlighting
- [ ] **VIEW-04**: DebugView renders raw channel data with metadata for debugging
- [ ] **VIEW-05**: User can toggle between views at runtime via keybinding
- [ ] **VIEW-06**: AI self-view provides structured feedback format for eval loop consumption

### Execution Display

- [ ] **DISP-01**: AI-executed code blocks render in Rich Panel with syntax highlighting and title
- [ ] **DISP-02**: Execution output renders in separate framed panel below code panel
- [ ] **DISP-03**: Code and output are grouped into a single visual unit (buffered rendering)
- [ ] **DISP-04**: AI-initiated code execution suppresses redundant [py] channel echo, keeping only results

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Streaming

- **STRM-01**: AI responses stream token-by-token to terminal
- **STRM-02**: User can interrupt streaming with Ctrl+C

### Observability

- **OTEL-01**: OTel spans for graph execution, node steps, LM calls
- **OTEL-02**: TracedLM wrapper for opt-in instrumentation

## Out of Scope

| Feature | Reason |
|---------|--------|
| AI bash dispatch (direct shell execution) | Security surface — AI uses Python only, tool calls translated to Python equivalents |
| Token-by-token streaming | Requires switching from Claude CLI subprocess to API client — separate milestone |
| Custom view plugins | YAGNI — three built-in views cover all known use cases |
| Configurable view per channel | Combinatorial complexity — single active view for terminal sufficient |
| Semantic XML parsing of tool calls | Regex detection + Python translation is simpler and correct for known patterns |
| Rich Live display | Conflicts with prompt_toolkit patch_stdout — use static Panel rendering |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AIHR-01 | Deferred | Deferred |
| AIHR-02 | Phase 22 | Pending |
| AIHR-03 | Phase 22 | Pending |
| AIHR-04 | Phase 22 | Pending |
| AIHR-05 | Phase 22 | Pending |
| AIHR-06 | Phase 22 | Pending |
| AIHR-07 | Phase 22 | Pending |
| AIHR-08 | Phase 22 | Pending |
| EXEC-01 | Phase 21 | Pending |
| EXEC-02 | Phase 21 | Pending |
| VIEW-01 | Phase 23 | Pending |
| VIEW-02 | Phase 23 | Pending |
| VIEW-03 | Phase 24 | Pending |
| VIEW-04 | Phase 25 | Pending |
| VIEW-05 | Phase 25 | Pending |
| VIEW-06 | Phase 25 | Pending |
| DISP-01 | Phase 24 | Pending |
| DISP-02 | Phase 24 | Pending |
| DISP-03 | Phase 24 | Pending |
| DISP-04 | Phase 24 | Pending |

**Coverage:**
- v5.0 requirements: 20 total
- Mapped to phases: 19
- Deferred: 1 (AIHR-01)

---
*Requirements defined: 2026-02-14*
*Last updated: 2026-02-14 after prompt hardening deferred, phases renumbered 21-25*
