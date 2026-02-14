# External Integrations

**Analysis Date:** 2026-02-14

## APIs & External Services

**Claude CLI:**
- Claude CLI subprocess integration - Core LLM backend for node population
  - SDK/Client: subprocess calls to `claude` binary
  - Auth: ANTHROPIC_API_KEY (required by Claude CLI, not directly accessed by bae)
  - Implementation: `bae/lm.py:317` (`ClaudeCLIBackend`)
  - Features: JSON structured output, session persistence (for REPL AI), schema-constrained generation
  - Flags used:
    - `--json-schema` - Constrained decoding via structured output
    - `--output-format json/text` - Response format control
    - `--session-id/--resume` - Session persistence for conversational AI
    - `--tools ""` - Disable built-in tools
    - `--strict-mcp-config` - Disable MCP servers
    - `--no-session-persistence` - Single-shot mode for graph nodes

## Data Storage

**Databases:**
- None

**File Storage:**
- Local filesystem only
  - REPL session storage: `bae/repl/store.py` - `.bae/sessions/` directory
  - AI prompt templates: `bae/repl/ai_prompt.md`

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- None (local tool)

**API Key Management:**
- ANTHROPIC_API_KEY environment variable required for Claude CLI
- No direct API key handling in bae code (delegated to Claude CLI)

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- stderr/stdout only
- No structured logging framework detected

## CI/CD & Deployment

**Hosting:**
- Not applicable - local CLI tool

**CI Pipeline:**
- None detected

## Environment Configuration

**Required env vars:**
- `ANTHROPIC_API_KEY` - For Claude CLI authentication (external dependency)

**Optional env vars:**
- `CLAUDECODE` - Explicitly filtered out in AI subprocess calls (`bae/repl/ai.py:214`)

**Secrets location:**
- Shell environment (ANTHROPIC_API_KEY)
- No .env files present

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## External Binaries

**Claude CLI:**
- Required: `claude` binary in PATH
- Purpose: LLM backend for all fill/choose_type operations
- Invocation: `asyncio.create_subprocess_exec` in `bae/lm.py:371` and `bae/repl/ai.py:216`
- Timeout: Configurable (default 20s for graph, 60s for REPL AI)

**mermaid-cli (optional):**
- Optional: `mmdc` binary for graph export
- Purpose: Export graph visualizations to files
- Referenced in: `bae/cli.py` graph export command

## Browser Integration

**mermaid.live:**
- Web-based graph visualization
- Implementation: `bae/cli.py:25` (`_encode_mermaid_for_live`)
- Opens browser with encoded graph diagram
- No API calls - URL-based state encoding

---

*Integration audit: 2026-02-14*
