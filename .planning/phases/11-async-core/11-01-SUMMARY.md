# Phase 11 Plan 01: Async LM Protocol Summary

**One-liner:** Converted LM Protocol, PydanticAIBackend, and ClaudeCLIBackend from sync to async with native APIs

## What Was Done

### Task 1: Convert lm.py to async
- LM Protocol: 4 methods (make, decide, choose_type, fill) declared as `async def`
- PydanticAIBackend: `agent.run_sync()` replaced with `await agent.run()` (native async)
- ClaudeCLIBackend: `subprocess.run()` replaced with `asyncio.create_subprocess_exec()` + `await process.communicate()` with timeout via `asyncio.wait_for()`
- Fill helpers remain sync: `_build_fill_prompt`, `_build_plain_model`, `validate_plain_fields`, `_strip_format`, `_build_choice_schema`, `_get_base_type`
- Added `import asyncio` at module level
- Commit: `3991ca6`

### Task 2: Migrate test_lm_protocol.py and test_fill_protocol.py to async
- All test functions calling backend methods converted to `async def` with `await`
- DSPy mock predictors: `mock_predictor.acall = AsyncMock(...)` (DSPyBackend uses `predictor.acall()`)
- PydanticAI mock agents: `mock_agent.run = AsyncMock(...)` (was `run_sync`)
- ClaudeCLI mock: `new_callable=AsyncMock` for `_run_cli_json` patches
- `CapturingLM` mock: all 4 methods converted to `async def`
- `TestGraphFillIntegration`: 3 tests skipped with `@pytest.mark.skip(reason="Requires async Graph.run - Plan 11-03")`
- `TestBuildInstruction` and `TestLMProtocol` shape tests remain sync (no I/O)
- Commit: `64a1431`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DSPy mock predictor calls used wrong method**
- **Found during:** Task 2
- **Issue:** DSPyBackend was already async (converted in prior work), using `predictor.acall()` and `self._call_with_retry()`. The original mocks used `mock_predictor.return_value` (for sync `__call__`), but the async path calls `predictor.acall()`.
- **Fix:** Changed mocks to `mock_predictor.acall = AsyncMock(return_value=...)` and updated assertion from `mock_predictor.call_args` to `mock_predictor.acall.call_args`.
- **Files modified:** `tests/test_lm_protocol.py`

## Verification Results

| Check | Result |
|-------|--------|
| `import bae.lm` | PASS |
| PydanticAIBackend 4 methods are coroutines | PASS |
| ClaudeCLIBackend._run_cli_json is coroutine | PASS |
| test_lm_protocol.py | 18 passed |
| test_fill_protocol.py | 5 passed, 3 skipped |
| test_fill_helpers.py | 20 passed (unchanged) |
| **Total** | **43 passed, 3 skipped** |

## Commits

| Hash | Message |
|------|---------|
| `3991ca6` | feat(11-01): convert LM Protocol and backends to async |
| `64a1431` | test(11-01): migrate LM protocol tests to async |

## Key Files

| File | Role |
|------|------|
| `bae/lm.py` | Async LM Protocol + PydanticAIBackend + ClaudeCLIBackend |
| `tests/test_lm_protocol.py` | Async tests for all 3 backends |
| `tests/test_fill_protocol.py` | Async prompt structure tests + skipped graph.run tests |

## Duration

~5 minutes

## Next Phase Readiness

Plan 11-02 (DSPyBackend async) is already done (commits `1b9eb1e`, `080cbd4` visible in git log). Plan 11-03 (async Graph.run) can proceed -- it will re-enable the 3 skipped `TestGraphFillIntegration` tests.
