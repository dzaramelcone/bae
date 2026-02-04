# External Integrations

**Analysis Date:** 2026-02-04

## APIs & External Services

**Large Language Models:**
- Anthropic Claude API - Primary LLM provider for agent decision-making
  - SDK/Client: `pydantic-ai` (wraps Anthropic SDK)
  - Auth: `ANTHROPIC_API_KEY` environment variable
  - Used in: `bae/lm.py` - `PydanticAIBackend` class
  - Default model: `anthropic:claude-sonnet-4-20250514`

- Claude CLI - Alternative local LLM interface (subprocess-based)
  - SDK/Client: Direct subprocess invocation
  - Auth: None (uses local CLI authentication)
  - Used in: `bae/lm.py` - `ClaudeCLIBackend` class
  - Default model: `claude-sonnet-4-20250514`

## Data Storage

**Databases:**
- None currently. Bae is a stateless agent graph framework with no persistent storage.

**File Storage:**
- Local filesystem only - Test files and code artifacts

**Caching:**
- In-memory agent cache only
  - Implementation: `PydanticAIBackend._agents` dict caches `Agent` instances by output type tuple
  - Location: `bae/lm.py` lines 41-56
  - Scope: Per-backend-instance (not shared across instances)

## Authentication & Identity

**Auth Provider:**
- Anthropic API Key (environment variable)
  - For PydanticAIBackend: Required for actual LLM calls
  - Env var name: `ANTHROPIC_API_KEY`
  - Used by: `pydantic-ai` Agent class when initialized with `anthropic:` model prefix

**Local CLI:**
- Claude CLI tool - Requires local installation and authentication
  - Used by: `ClaudeCLIBackend` in `bae/lm.py`
  - Invocation: Direct subprocess call to `claude` command
  - Schema format: JSON Schema passed via `--json-schema` flag

## Monitoring & Observability

**Error Tracking:**
- None - Errors are raised as exceptions and propagated to caller

**Logs:**
- Standard output/stderr - Test file shows `-s` flag for pytest to capture output
- Location: `tests/test_integration.py` suggests using `pytest -v -s` for visibility

## CI/CD & Deployment

**Hosting:**
- Not applicable - Bae is a framework/library, not a hosted service

**CI Pipeline:**
- None configured - No CI/CD setup files present
- Tests run locally via `uv run pytest`

## Environment Configuration

**Required env vars:**
- `ANTHROPIC_API_KEY` - Required for PydanticAIBackend to make actual API calls
  - Tests using PydanticAI are skipped if not set (see `tests/test_integration.py` line 78-81)

**Optional env vars:**
- None explicitly defined

**Secrets location:**
- Environment variable only (ANTHROPIC_API_KEY)
- No `.env` file management (not part of project)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None - Bae is a synchronous graph execution framework

## LLM Backend Configuration

**PydanticAIBackend:**
- Location: `bae/lm.py` lines 36-111
- Model parameter: `model` kwarg (default: `anthropic:claude-sonnet-4-20250514`)
- Methods:
  - `make(node, target)` - Generates single typed output
  - `decide(node)` - Picks successor type from available options
  - Internal: Uses pydantic-ai `Agent.run_sync()` for synchronous execution

**ClaudeCLIBackend:**
- Location: `bae/lm.py` lines 113-230
- Model parameter: `model` kwarg (default: `claude-sonnet-4-20250514`)
- Timeout: `timeout` kwarg (default: 20 seconds)
- Methods:
  - `make(node, target)` - Uses two-step CLI process (generate schema, run CLI, validate)
  - `decide(node)` - Two-step approach to avoid slow oneOf JSON schemas (pick type, then fill)
  - Command format: `claude -p {prompt} --model {model} --output-format json --json-schema {schema}`

## Integration Testing

**Test Environment:**
- Location: `tests/test_integration.py`
- PydanticAI tests: Conditional on `ANTHROPIC_API_KEY` environment variable
- Claude CLI tests: No dependencies, assumes `claude` command is available
- Test data: In-memory Node instances (no external databases)
- Models used in tests:
  - PydanticAI: `anthropic:claude-sonnet-4-20250514`
  - CLI: `claude-sonnet-4-20250514`

---

*Integration audit: 2026-02-04*
