# Codebase Concerns

**Analysis Date:** 2026-02-14

## Tech Debt

**Unawaited coroutine handling in PY mode:**
- Issue: Creating collections of unawaited coroutines (e.g., `[asyncio.sleep(30) for _ in range(20)]`) crashes the entire REPL process instead of showing a graceful warning
- Files: `bae/repl/shell.py:293-306`, `bae/repl/exec.py:57-67`
- Impact: REPL becomes unusable when users create unawaited coroutines in collections. Process exits, losing session state and unsaved work
- Fix approach: Add `_contains_coroutines()` and `_count_and_close_coroutines()` helpers (already implemented in shell.py lines 47-88), use them in PY mode result handler to detect collections containing coroutines before calling `repr()`, show warning message instead of crashing, close coroutines to prevent RuntimeWarnings
- Status: Partially implemented (helper functions exist) but not yet integrated into PY mode dispatch logic

**REPL namespace binding confusion in SessionStore:**
- Issue: `store.sessions()` fails with AttributeError because `store` namespace binding points to the inspector closure from `make_store_inspector()`, not the SessionStore instance itself
- Files: `bae/repl/store.py:125-141`, `bae/repl/shell.py:65`
- Impact: Users cannot access SessionStore methods like `sessions()`, `recent()`, or `session_entries()` through the REPL namespace. Additionally, `store()` returns raw `sqlite3.Row` objects that repr as ugly `<sqlite3.Row object at 0x...>` instead of formatted data
- Fix approach: Make SessionStore callable by adding `__call__` method that implements inspector behavior, then inject the instance directly into namespace instead of the closure. This maintains single namespace binding while exposing all methods

**REPL-defined class annotation resolution:**
- Issue: Classes defined in the REPL get `__module__='<cortex>'` from `compile(tree, '<cortex>', 'exec')`. When any bae code calls `get_type_hints()` on these classes, Python looks up `'<cortex>'` in `sys.modules` to resolve string annotations, but `'<cortex>'` is not a registered module, causing NameError
- Files: `bae/repl/exec.py:34-49`, `bae/resolver.py:39`, `bae/lm.py:52`, `bae/graph.py:71`
- Impact: Operations on REPL-defined Node classes fail with `NameError: name 'Annotated' is not defined` even though Annotated exists in the REPL namespace. Affects `ns(MyNode)` inspection, graph creation, LM fill, and compilation
- Fix approach: Register `<cortex>` as a module in `sys.modules` with the REPL namespace as its `__dict__`. Already implemented in `_ensure_cortex_module()` function (exec.py:14-25) and called in `async_exec()` before compile (line 48)
- Status: Fixed as of recent commits

**AI tool call translation inconsistency:**
- Issue: AI inconsistently follows tool tag convention. `<R:>` and `<W:>` work reliably, but `<G:>` and `<Grep:>` sometimes output as OSC 8 terminal hyperlink escape sequences instead. `<E:>` sometimes confused with `<R:>` for line reads
- Files: `bae/repl/ai.py:28-57` (regex patterns), Phase 22 UAT test results
- Impact: Tool calls that should execute automatically don't run, forcing users to manually translate AI intent into executable code. Breaks the eval loop for Glob and Grep operations
- Fix approach: Strengthen AI prompt to enforce tool tag vocabulary, improve regex detection to handle edge cases, add validation to detect and warn about malformed tool tags in AI responses
- Status: In progress (Phase 22), 3/7 UAT tests showing issues

## Known Bugs

**None currently tracked in code.**

The bugs identified above (unawaited coroutines crash, store namespace binding, annotation resolution) are classified as tech debt because they represent design shortcuts or incomplete implementations rather than regressions.

## Security Considerations

**Session store database location:**
- Risk: Session history stored in `.bae/store.db` (sqlite) contains all REPL interactions, potentially including sensitive data like API keys or passwords typed in PY mode
- Files: `.bae/store.db`, `bae/repl/store.py`
- Current mitigation: `.bae/` directory is in `.gitignore` (line 27), preventing accidental commit to version control
- Recommendations: Document that users should not commit `.bae/` directory, consider adding encryption option for session store, warn users before storing expressions that look like secrets (regex match for common secret patterns)

**AI agent subprocess invocation:**
- Risk: AI agent spawns Claude CLI subprocess with user input. If prompt contains shell metacharacters and is improperly escaped, could lead to command injection
- Files: `bae/repl/ai.py` (AI class implementation)
- Current mitigation: Uses structured subprocess API (not shell=True) and passes arguments as list, which prevents shell injection
- Recommendations: Current implementation is safe. Maintain discipline of never switching to `shell=True` for Claude CLI invocation

**Environment variable exposure:**
- Risk: REPL namespace includes `os` module (namespace.py:32), allowing users to access `os.environ` which may contain API keys and secrets
- Files: `bae/repl/namespace.py:22-33`
- Current mitigation: None - this is intentional for user convenience
- Recommendations: Acceptable risk for a development REPL. Users who need secure environments should use restricted Python execution contexts

## Performance Bottlenecks

**Synchronous LM calls:**
- Problem: LM fill operations are async but run serially during node execution
- Files: `bae/graph.py:150-250` (Graph.run execution loop)
- Cause: Graph execution processes nodes sequentially. When a node needs LM fill, the entire graph waits
- Improvement path: Batch LM calls when multiple nodes at the same depth need filling. Use `asyncio.gather()` to parallelize independent LM operations. Graph topology already supports parallel execution of nodes without dependencies (depth-based scheduling)

**Large test file execution:**
- Problem: Test suite has 7645 lines across 30 files. Largest test files are 800+ lines (test_resolver.py, test_ai.py)
- Files: `tests/test_resolver.py` (805 lines), `tests/repl/test_ai.py` (800 lines)
- Cause: Comprehensive test coverage with many edge cases. Not inherently a problem but indicates complexity in these modules
- Improvement path: Consider splitting large test files by feature area (e.g., test_resolver.py → test_classify_fields.py, test_recall.py, test_dep_dag.py). Maintain current coverage but improve test organization and parallelization

## Fragile Areas

**Async coroutine detection and cleanup:**
- Files: `bae/repl/shell.py:47-88`, `bae/repl/exec.py:57-61`
- Why fragile: Recursively traversing arbitrary Python objects to detect coroutines must handle circular references (currently uses `_seen` set) and unknown container types. Missing a coroutine deep in a nested structure could cause RuntimeWarnings or crashes
- Safe modification: When adding new coroutine detection logic, always include cycle detection via `_seen` parameter. Test with deeply nested structures and circular references
- Test coverage: Needs explicit tests for circular references, deeply nested collections, and mixed types (e.g., `{"a": [1, asyncio.sleep(1), {"b": asyncio.sleep(2)}]}`)

**REPL namespace state persistence:**
- Files: `bae/repl/exec.py:14-25` (`_ensure_cortex_module`), `bae/repl/namespace.py:36-41` (seed)
- Why fragile: REPL namespace dict and `sys.modules['<cortex>']` must stay synchronized. If namespace is updated without updating the module dict, `get_type_hints()` will fail on newly defined classes
- Safe modification: Always call `_ensure_cortex_module(namespace)` before executing user code in `async_exec()` (currently done at line 48). Never directly modify `sys.modules['<cortex>']` outside of this function
- Test coverage: Test that classes defined in successive REPL executions all resolve correctly (e.g., define ClassA, then ClassB that references ClassA, then call `get_type_hints(ClassB)`)

**Graph topology discovery:**
- Files: `bae/graph.py:55-99` (`_get_routing_strategy`), `bae/graph.py:150-250` (execution loop)
- Why fragile: Graph topology is inferred from Node return type hints and `__call__` body inspection (`_has_ellipsis_body`). Changes to how Python represents ellipsis or union types could break discovery
- Safe modification: When modifying routing logic, ensure all four strategies remain distinct: `("custom",)`, `("terminal",)`, `("make", T)`, `("decide", [T1, T2])`. Any new strategy requires corresponding execution logic
- Test coverage: Coverage is strong (see `tests/test_graph.py:177`), includes all routing strategies and edge cases (optional types, unions, None returns)

**AI eval loop extraction:**
- Files: `bae/repl/ai.py:28-57` (regex patterns for tool tags and executable blocks)
- Why fragile: Relies on regex to extract executable code from AI responses. Changes to tag format or addition of new tags require regex updates. Malformed tags or edge cases (nested tags, escaped characters) could break extraction
- Safe modification: When adding new tool tags, update ALL relevant regexes (`_TOOL_TAG_RE`, `_WRITE_TAG_RE`, `_EDIT_REPLACE_RE`, `_OSC8_TOOL_RE`). Test with edge cases: tags in code comments, tags in strings, multiple tags on same line
- Test coverage: Good coverage in `tests/repl/test_ai.py` but UAT reveals real-world issues with OSC 8 sequences. Need tests for OSC 8 hyperlinks, malformed tags, and edge cases from UAT failures

## Scaling Limits

**Session store query performance:**
- Current capacity: SQLite database with full-text search on session history. No pagination or limits on result sets
- Limit: After thousands of REPL sessions, `store()` queries could become slow. SQLite full-text search scales well to ~1M rows but lacks query time limits
- Scaling path: Add pagination to store inspector (e.g., `store(limit=50)`), implement result streaming for large result sets, add indexes on session_id and timestamp if not already present

**REPL namespace size:**
- Current capacity: All user-defined classes, functions, and variables persist in namespace dict throughout session
- Limit: Very long REPL sessions with hundreds of class definitions could consume significant memory. Namespace dict is kept in sync with `sys.modules['<cortex>']`, doubling memory overhead
- Scaling path: Implement namespace cleanup command (e.g., `clear_namespace()` that preserves preloaded objects), consider weak references for rarely-accessed objects, add memory usage indicator to toolbar (already has `make_mem_widget` in toolbar.py:34)

**Parallel dependency execution:**
- Current capacity: Graph can execute nodes in parallel when they have no dependencies (depth-based scheduling)
- Limit: No limit on concurrent tasks. Graph with wide parallelism (many nodes at same depth) could spawn hundreds of simultaneous LM calls, hitting rate limits or exhausting memory
- Scaling path: Add semaphore to limit concurrent LM operations (e.g., max 10 simultaneous fills), implement backpressure mechanism to pause node execution when hitting rate limits, expose concurrency limit as Graph configuration

## Dependencies at Risk

**Python 3.14 requirement:**
- Risk: Project requires Python 3.14 (pyproject.toml:5), which is unreleased as of knowledge cutoff (January 2025)
- Impact: Users on Python 3.12 or 3.13 cannot run bae. Project is not deployable to standard Python environments
- Migration plan: Verify actual minimum version. If only using stable features, reduce requirement to `>=3.12`. If using 3.14-specific features (e.g., new typing syntax), document which features and provide compatibility shims for 3.12+

**Ruff target version mismatch:**
- Risk: Ruff configured with `target-version = "py312"` (pyproject.toml:30) but project requires `>=3.14`
- Impact: Linting may not catch issues specific to Python 3.14 syntax or features. Code may use 3.12 constructs that break on 3.14
- Migration plan: Update ruff target-version to "py314" or create custom configuration profile. Verify ruff supports Python 3.14 target version

**No LLM backend dependency:**
- Risk: Project imports `LM` protocol (`bae/lm.py:22`) but has no LLM client in dependencies (no anthropic, openai, or similar in pyproject.toml:6-12)
- Impact: Users must manually install and configure LLM backend. No default implementation means code is untestable without external setup
- Migration plan: Add optional dependency group for LLM backends (e.g., `anthropic>=0.40` in `[project.optional-dependencies]`), document which backends are supported, provide mock LM implementation for testing

## Missing Critical Features

**No error recovery in Graph execution:**
- Problem: When a node fails during Graph.run(), entire graph execution halts. No retry logic, no partial result recovery, no error context in trace
- Blocks: Production deployments where transient failures (network issues, rate limits) should trigger retries instead of failing entire workflow
- Fix: Add retry configuration to NodeConfig, implement exponential backoff for DepError and FillError, preserve partial execution trace on failure for debugging

**No graph execution timeout:**
- Problem: Graph.run() has no timeout mechanism. Long-running or infinite loops in Dep functions can hang indefinitely
- Blocks: Production use cases requiring bounded execution time, integration with systems that enforce timeouts
- Fix: Add timeout parameter to Graph.run(), use `asyncio.wait_for()` to enforce limit, raise TimeoutError with partial trace showing which node was executing when timeout occurred

**No structured logging in production code:**
- Problem: Graph execution uses stdlib logging at DEBUG level (`bae/repl/shell.py:456`, `bae/graph.py:17`) but no structured log output (JSON, key-value pairs). No correlation IDs for tracing multi-node execution
- Blocks: Observability in production deployments, debugging complex graph failures, integrating with log aggregation systems
- Fix: Add structured logging (use `logging.LogRecord.extra`), assign execution_id to each Graph.run() call and include in all log messages, log node entry/exit with timing and field values

## Test Coverage Gaps

**No tests for REPL session persistence across restarts:**
- What's not tested: SessionStore correctly persists entries to SQLite and can restore them after process restart
- Files: `bae/repl/store.py`, `tests/repl/test_store.py`, `tests/repl/test_store_integration.py`
- Risk: Database schema changes or corruption could lose session history without detection
- Priority: Medium

**No tests for circular dependency detection in Graph:**
- What's not tested: Graph topology discovery handles circular dependencies in Node return types (e.g., NodeA → NodeB → NodeA)
- Files: `bae/graph.py`, `tests/test_graph.py`
- Risk: Circular dependencies could cause infinite loops during graph discovery or execution
- Priority: High

**No tests for memory cleanup of closed coroutines:**
- What's not tested: `_count_and_close_coroutines()` actually prevents RuntimeWarnings and garbage collection issues
- Files: `bae/repl/shell.py:69-88`, `tests/repl/test_shell.py` (does not exist)
- Risk: Closed coroutines might still leak or cause warnings. No verification that closing works as intended
- Priority: High (related to existing crash bug)

**No tests for OSC 8 hyperlink parsing in AI eval loop:**
- What's not tested: AI responses containing OSC 8 terminal escape sequences are correctly parsed and translated to tool calls
- Files: `bae/repl/ai.py:50-53`, `tests/repl/test_ai.py`
- Risk: UAT failures in Phase 22 show OSC 8 sequences break tool detection. Regression could go undetected
- Priority: High (active UAT failure)

**No tests for get_type_hints with REPL-defined classes:**
- What's not tested: REPL-defined Node classes with Annotated[T, Dep()] fields correctly resolve annotations via `_ensure_cortex_module()`
- Files: `bae/repl/exec.py:14-25`, `tests/repl/test_exec.py` (does not exist)
- Risk: Regression in cortex module registration could break all REPL operations with Node classes
- Priority: High (core REPL functionality)

**No integration tests for Graph.run() with REPL-defined nodes:**
- What's not tested: End-to-end workflow: define Node classes in REPL, create Graph, execute with LM fill, verify results
- Files: All graph/node/lm code, `tests/test_integration.py` (151 lines, may not cover REPL scenario)
- Risk: Integration between REPL namespace management and graph execution could break silently
- Priority: Medium

---

*Concerns audit: 2026-02-14*
