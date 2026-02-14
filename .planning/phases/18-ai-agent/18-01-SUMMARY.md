# Plan 18-01: AI callable class

## Result: COMPLETE

## What was built
AI callable class using Claude CLI subprocess instead of pydantic-ai Agent. No API key needed — uses `--session-id` / `--resume` for persistent conversation with prompt caching benefits.

## Key decisions
- **CLI over SDK**: Claude CLI subprocess instead of pydantic-ai Agent — no API key cost, uses existing Claude Code subscription
- **Session persistence**: UUID-based `--session-id` on first call, `--resume` on subsequent calls — CLI manages conversation history, API-side caching works on message prefix
- **Prompt file**: System prompt in `ai_prompt.md` next to module — easy to iterate and evaluate separately
- **CLAUDECODE unset**: env var filtered out to allow nested CLI invocation from cortex

## Key files

### Created
- `bae/repl/ai.py` — AI class with CLI subprocess __call__, fill/choose_type delegation, extract_code, _build_context
- `bae/repl/ai_prompt.md` — System prompt for cortex AI agent

### Modified
- `tests/repl/test_ai.py` — 20 unit tests (extract_code, build_context, repr, init, prompt file)

## Self-Check: PASSED
- `uv run pytest tests/repl/test_ai.py -v` — 20/20 pass
- `uv run pytest tests/repl/ -v` — 135/135 pass, zero regressions
