# Plan 18-02: Shell integration wiring

## Result: COMPLETE

## What was built
AI object wired into CortexShell — created at init with ClaudeCLIBackend, injected into namespace as `ai`, NL mode stub replaced with real dispatch.

## Key decisions
- **ClaudeCLIBackend for fill/choose_type**: No API key needed for structured output either
- **Error routing**: NL mode errors route to [ai] channel (matches PY mode pattern)
- **AI.__call__ owns channel output**: Shell only handles exceptions, no duplicate writes

## Key files

### Created
- `tests/repl/test_ai_integration.py` — 8 integration tests

### Modified
- `bae/repl/shell.py` — AI import, construction in __init__, NL mode dispatch

## Self-Check: PASSED
- `uv run pytest tests/repl/test_ai_integration.py -v` — 8/8 pass
- `uv run pytest tests/repl/ -v` — 143/143 pass, zero regressions
