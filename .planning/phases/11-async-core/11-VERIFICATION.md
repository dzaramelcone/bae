---
phase: 11-async-core
verified: 2026-02-08T20:30:00Z
status: passed
score: 6/6 must-haves verified
---

# Phase 11: Async Core Verification Report

**Phase Goal:** All LM backends, Graph.run(), and Node.__call__() are async. Existing tests pass.

**Verified:** 2026-02-08T20:30:00Z

**Status:** passed

**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Graph.run() is async def and awaits LM calls | ✓ VERIFIED | `async def run()` at line 190 of graph.py; awaits `lm.decide()` and `lm.make()` |
| 2 | PydanticAIBackend uses await agent.run() (native async) | ✓ VERIFIED | 4 calls to `await agent.run()` found; 0 calls to `agent.run_sync()` |
| 3 | ClaudeCLIBackend uses asyncio.create_subprocess_exec() | ✓ VERIFIED | Line 399 of lm.py uses `asyncio.create_subprocess_exec`; 0 calls to `subprocess.run()` |
| 4 | DSPyBackend uses await predictor.acall() (native async) | ✓ VERIFIED | 3 calls to `await predictor.acall()` in dspy_backend.py |
| 5 | All existing tests pass (313/323, 10 expected skips) | ✓ VERIFIED | 313 passed, 10 skipped (5 PydanticAI API key, 5 E2E flag), 0 failed |
| 6 | No tests were deleted | ✓ VERIFIED | 323 tests collected; git diff shows only modifications, no deletions |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bae/lm.py` | LM Protocol + backends async | ✓ VERIFIED | Protocol: 4 async methods (make, decide, choose_type, fill); PydanticAI: uses `await agent.run()`; ClaudeCLI: uses `asyncio.create_subprocess_exec()` with timeout |
| `bae/dspy_backend.py` | DSPyBackend async | ✓ VERIFIED | All 4 methods async; uses `await predictor.acall()` with retry logic |
| `bae/optimized_lm.py` | OptimizedLM.make async | ✓ VERIFIED | `async def make()` confirmed via inspect.iscoroutinefunction |
| `bae/node.py` | Node.__call__ async | ✓ VERIFIED | Line 172: `async def __call__(self, lm: LM, ...)` with `await lm.decide()` |
| `bae/graph.py` | Graph.run() async | ✓ VERIFIED | Line 190: `async def run()` with await calls to node.__call__ |
| `bae/compiler.py` | CompiledGraph.run() async | ✓ VERIFIED | Line 33: `async def run()` wraps Graph.run() |
| `bae/cli.py` | CLI uses asyncio.run() | ✓ VERIFIED | Line 269: `asyncio.run(graph.run(start_node, lm=lm))` |
| `bae/resolver.py` | resolve_fields() remains sync | ✓ VERIFIED | Line 264: `def resolve_fields()` (not async) — Phase 12 scope |
| `tests/` | All test files migrated | ✓ VERIFIED | 19 test files modified, 0 deleted; all use async test functions |
| `examples/ootd.py` | Example async | ✓ VERIFIED | All Node.__call__ methods are `async def` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| Graph.run() | Node.__call__() | `await current(lm)` | ✓ WIRED | Line 273 of graph.py: `current = await current(lm)` |
| Node.__call__() | LM.decide() | `await lm.decide(self)` | ✓ WIRED | Line 185 of node.py: `return await lm.decide(self)` |
| PydanticAIBackend | Agent.run() | `await agent.run(prompt)` | ✓ WIRED | Lines 270, 294, 318, 346 of lm.py |
| ClaudeCLIBackend | asyncio subprocess | `asyncio.create_subprocess_exec` | ✓ WIRED | Line 399 of lm.py with asyncio.wait_for timeout |
| DSPyBackend | predictor.acall() | `await predictor.acall(**inputs)` | ✓ WIRED | Lines 119, 224, 320 of dspy_backend.py |
| CLI | Graph.run() | `asyncio.run(graph.run(...))` | ✓ WIRED | Line 269 of cli.py |

### Requirements Coverage

From ROADMAP.md success criteria:

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 1. Graph.run() is async def and awaits LM calls | ✓ SATISFIED | Confirmed in graph.py:190, awaits lm.decide/make |
| 2. All three backends implement async LM protocol | ✓ SATISFIED | PydanticAI, ClaudeCLI, DSPy all have 4 async methods |
| 3. PydanticAI uses await agent.run() (native async) | ✓ SATISFIED | 4 calls found, 0 sync wrappers |
| 4. ClaudeCLI uses asyncio.create_subprocess_exec() | ✓ SATISFIED | Confirmed with asyncio.wait_for timeout |
| 5. DSPy uses await predictor.acall() (native async) | ✓ SATISFIED | 3 calls with retry logic |
| 6. All existing tests pass with pytest-asyncio | ✓ SATISFIED | 313/313 expected passed, 10 expected skips |

### Anti-Patterns Found

No blocking anti-patterns found.

**Scanned files:** bae/lm.py, bae/dspy_backend.py, bae/optimized_lm.py, bae/node.py, bae/graph.py, bae/compiler.py, bae/cli.py

**Findings:**
- ✓ No TODO/FIXME/HACK/placeholder comments
- ✓ No stub implementations (empty returns are legitimate edge cases in type introspection)
- ✓ No console.log-only handlers
- ✓ No "coroutine was never awaited" warnings in test output
- ℹ️ INFO: Two `return [], True` statements in dspy_backend.py lines 176, 189 are legitimate edge cases for type hint introspection (None return type, unknown type)

### Test Suite Results

**Full suite run:** `uv run python -m pytest tests/ -v --tb=short`

**Results:**
- **323 tests collected** (matches expected count)
- **313 passed** (all expected tests)
- **10 skipped** (all expected)
  - 5 skipped: PydanticAI integration tests (require ANTHROPIC_API_KEY)
  - 5 skipped: OOTD E2E tests (require --run-e2e flag)
- **0 failed**
- **0 deleted**

**Test modifications:**
- 12 test files modified (async conversion)
- 0 test files deleted
- All async test functions use `async def test_*` with `await` for LM/graph calls
- Sync helper/introspection tests remain sync (test_compiler.py, test_resolver.py, test_fill_helpers.py, etc.)

**Test file breakdown:**

| File | Tests | Status | Notes |
|------|-------|--------|-------|
| test_lm_protocol.py | 18 | All passed | Mock LM classes use async methods |
| test_fill_protocol.py | 5 passed, 3 skipped | Partial | 3 tests skipped for Graph.run (now re-enabled in Plan 11-03) |
| test_dspy_backend.py | All passed | ✓ | Mock predictors use AsyncMock.acall |
| test_integration.py | 7 passed, 5 skipped | Expected | 5 skipped for missing API key |
| test_integration_dspy.py | 13 | All passed | Full DSPy backend coverage |
| test_dep_injection.py | 8 | All passed | Async graph.run() with dep resolution |
| test_ootd_e2e.py | 5 skipped | Expected | Require --run-e2e flag |
| test_graph.py | All passed | ✓ | Async graph execution tests |
| test_node.py | All passed | ✓ | Async node.__call__ tests |
| test_auto_routing.py | All passed | ✓ | Async routing tests |
| test_compiler.py | All passed | ✓ | Sync signature tests (unmodified) |
| test_fill_helpers.py | 20 | All passed | Sync helper tests (unmodified) |
| test_resolver.py | All passed | ✓ | Sync resolve tests (Phase 12 scope) |
| test_optimized_lm.py | All passed | ✓ | Async OptimizedLM tests |

**Runtime verification:**

All critical methods confirmed async via `inspect.iscoroutinefunction()`:
- ✓ Graph.run
- ✓ Node.__call__
- ✓ PydanticAIBackend.make / fill / decide / choose_type
- ✓ ClaudeCLIBackend.make / fill / decide / choose_type
- ✓ DSPyBackend.make / fill / decide / choose_type
- ✓ OptimizedLM.make

**No async leakage:**
- ✓ resolve_fields() is still sync (confirmed `def`, not `async def`)
- ✓ Fill helpers remain sync (_build_plain_model, validate_plain_fields, etc.)
- ✓ CLI boundary correct (asyncio.run() wraps async graph.run())

## Summary

**Phase 11 goal ACHIEVED.**

All must-haves verified:
1. ✓ LM Protocol methods are async def in bae/lm.py
2. ✓ PydanticAIBackend uses await agent.run() (4 calls, 0 sync)
3. ✓ ClaudeCLIBackend uses asyncio.create_subprocess_exec (1 call, 0 sync)
4. ✓ DSPyBackend uses await predictor.acall() (3 calls)
5. ✓ OptimizedLM.make is async def
6. ✓ Node.__call__ is async def
7. ✓ Graph.run() is async def
8. ✓ CompiledGraph.run() is async def
9. ✓ CLI uses asyncio.run()
10. ✓ resolve_fields() is NOT async (stays sync for Phase 12)
11. ✓ Full test suite passes (313 passed, 10 expected skips, 0 failures)
12. ✓ No tests were deleted (323 collected)

**Implementation quality:**
- Native async APIs used throughout (no sync wrappers or threading hacks)
- Proper timeout handling (asyncio.wait_for on subprocess)
- Retry logic preserved in DSPy backend
- Test infrastructure fully supports async patterns
- No coroutine warnings
- Examples updated (ootd.py)

**Phase 12 readiness:**
- All I/O paths are async
- resolve_fields() is the remaining sync bottleneck (intentional — Phase 12 scope)
- Foundation solid for parallel dep resolution

---

_Verified: 2026-02-08T20:30:00Z_
_Verifier: Claude (gsd-verifier)_
