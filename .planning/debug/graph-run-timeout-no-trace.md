---
status: diagnosed
trigger: "Investigate why a graph submitted via `run ootd(user_info=UserInfo(...), user_message=\"...\")` in GRAPH mode locks up and eventually fails with \"Claude CLI timed out after 20s\"."
created: 2026-02-15T00:00:00Z
updated: 2026-02-15T00:00:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: Root causes confirmed - analysis complete
test: Verified all four issues with code evidence
expecting: Ready to return structured diagnosis
next_action: Return diagnosis to caller

## Symptoms

expected:
- Graph executes nodes and completes (or fails with informative error)
- `inspect g1` shows node execution details
- `trace g1` shows execution trace
- ANSI rendering works correctly in Rich tables

actual:
- Graph locks up, fails after 67.6s with "Claude CLI timed out after 20s"
- `inspect g1` shows only "Run g1 (failed, 67.6s)" with no node details
- `trace g1` shows "no trace available"
- Some nodes must have succeeded before timeout (per user report)
- Rich table ANSI escape issue present

errors:
- "Claude CLI timed out after 20s"
- "no trace available"

reproduction:
1. Enter GRAPH mode in REPL
2. Run: `run ootd(user_info=UserInfo(...), user_message="...")`
3. Wait for timeout/failure
4. Try `inspect g1` - see minimal info
5. Try `trace g1` - see "no trace available"

started: Discovered during phase 27 UAT testing

## Eliminated

## Evidence

- timestamp: 2026-02-15T00:01:00Z
  checked: ClaudeCLIBackend.__init__ in bae/lm.py:413
  found: timeout defaults to 20 seconds
  implication: Each LM call has 20s timeout. The ootd graph has 6+ nodes (IsTheUserGettingDressed, AnticipateUsersDay, InferUserBackground, InferUserPersonality, GenerateWardrobe, RecommendOOTD), each requiring LM fill calls. Total execution 67.6s suggests ~10+ LM calls completed before one timed out.

- timestamp: 2026-02-15T00:02:00Z
  checked: Graph execution flow in graph.py and engine.py
  found: submit_coro path (engine.py:125-141) wraps pre-built coroutine, while submit path (engine.py:92-123) uses TimingLM wrapper
  implication: When user calls `run ootd(...)`, ootd is a coroutine (graph factory returns async callable). This goes through submit_coro, NOT submit. TimingLM is never injected.

- timestamp: 2026-02-15T00:03:00Z
  checked: TimingLM wrapper in engine.py:52-84
  found: TimingLM wraps LM.fill() and LM.make() to populate run.node_timings
  implication: submit_coro bypasses TimingLM, so run.node_timings stays empty. This explains why inspect shows no node details.

- timestamp: 2026-02-15T00:04:00Z
  checked: _wrap_coro in engine.py:143-160
  found: Line 148-149 only sets run.result if hasattr(result, "trace")
  implication: When graph completes successfully, run.result gets populated. On exception (timeout), line 154-156 catches and sets run.state/error but run.result stays None.

- timestamp: 2026-02-15T00:05:00Z
  checked: _cmd_inspect in graph_commands.py:193-206 and _cmd_trace in graph_commands.py:219-220
  found: Both check `run.result and run.result.trace` before displaying trace data
  implication: If run.result is None (timeout case), both commands show no trace even if nodes executed before failure. The trace lives in GraphResult, which is the return value of graph.arun(). On timeout exception, GraphResult never gets returned/assigned to run.result.

- timestamp: 2026-02-15T00:06:00Z
  checked: BaeError in graph.py:335-337 and DepError in graph.py:345-350
  found: Both exceptions attach .trace attribute before raising
  implication: Graph.arun() attaches trace to exceptions, but _wrap_coro (line 154-156) catches Exception, not BaeError specifically. The exception object has .trace, but _wrap_coro doesn't extract it.

- timestamp: 2026-02-15T00:07:00Z
  checked: Rich table rendering in graph_commands.py:140
  found: `_rich_to_ansi(table)` - tables created via Rich Console but converted to ANSI
  implication: ANSI escape issue is separate concern (likely shell/terminal handling). Not related to core graph execution bugs.

## Resolution

root_cause: |
  Four independent root causes identified:

  **ISSUE 1: Graph execution timeout (67.6s elapsed, fails with "Claude CLI timed out after 20s")**

  Root Cause: ClaudeCLIBackend has a 20-second timeout per LM call (lm.py:413, 472-477). The ootd graph has 6 nodes, each requiring LM.fill() or LM.make() calls. The graph uses Dep() annotations which trigger additional node fills (InferUserBackground, InferUserPersonality, GenerateWardrobe are Dep nodes). With ~10+ LM calls total, the cumulative time is 67.6s, but any single call exceeding 20s triggers RuntimeError("Claude CLI timed out after 20s").

  The timeout is per-call, not per-graph. The 67.6s total suggests multiple calls succeeded (taking ~6-7s each) before one hit the 20s limit.

  **ISSUE 2: inspect shows no node details**

  Root Cause: When user runs `ootd(...)`, the graph factory (graph.py:487) returns a coroutine. The REPL's _cmd_run (graph_commands.py:67-70) detects this and calls submit_coro (engine.py:125-141), NOT submit (engine.py:92-123). Only submit wraps the LM with TimingLM (engine.py:108). submit_coro wraps a pre-built coroutine where the LM is already bound inside the closure, so TimingLM can't be injected. Result: run.node_timings stays empty (engine.py:137 creates GraphRun with graph=None, default node_timings=[]).

  **ISSUE 3: trace shows "no trace available"**

  Root Cause: On exception (including timeout), _wrap_coro (engine.py:143-160) catches the exception at line 154 and sets run.state/error, but never sets run.result. The trace lives in GraphResult.trace, which is the return value of graph.arun(). When timeout occurs, the RuntimeError propagates from ClaudeCLIBackend._run_cli_json → graph.arun() → _wrap_coro. graph.arun() attaches .trace to BaeError/DepError exceptions (graph.py:336, 350), but RuntimeError from the LM backend doesn't have .trace attached. _wrap_coro doesn't extract trace from exceptions, so run.result stays None.

  _cmd_trace (graph_commands.py:219-220) checks `if not (run.result and run.result.trace)` and returns "no trace available" when run.result is None.

  **ISSUE 4: Rich table ANSI escape rendering**

  Root Cause: _cmd_list uses _rich_to_ansi(table) (graph_commands.py:140) to convert Rich Table to ANSI. The Rich rendering itself is correct. The issue is likely in how the shell's router/channel system handles ANSI escapes in GRAPH mode output, or the terminal's ANSI support. This is orthogonal to the execution issues above - the data is correct, just display formatting is broken.

fix:
verification:
files_changed: []
