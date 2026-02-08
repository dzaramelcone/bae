# Phase 11: Async Core - Research

**Researched:** 2026-02-08
**Domain:** Python asyncio conversion of sync codebase (LM backends, graph execution, node dispatch)
**Confidence:** HIGH

## Summary

Phase 11 converts bae's synchronous execution pipeline to async. The conversion is formulaic: every method that calls an LM backend (or subprocess, or dep function) becomes `async def` and uses `await`. The three LM backends (DSPy, PydanticAI, ClaudeCLI) all have native async APIs already available in the installed versions. Tests must become `async def` wherever they call converted methods, and `asyncio_mode = "auto"` (already configured) handles the rest.

The conversion is bottom-up: backends first, then resolver, then graph.run(), then CLI boundary. Each layer awaits the layer below it. The critical challenge is NOT the async conversion itself (it's mechanical) but avoiding breaking the 323 existing tests during the process. The recommended strategy is to convert and test one layer at a time, starting from the leaves (backends) and working up.

**Primary recommendation:** Convert bottom-up (backends -> node.__call__ -> resolver -> graph.run -> CLI boundary). Each layer: convert methods to async, convert their tests to async, run full suite before moving to next layer.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | Python 3.14 | Event loop, subprocess, sleep | Built-in, no dependencies |
| pytest-asyncio | 1.3.0 | Async test collection | Already installed and configured |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dspy | 3.1.2 | `Predict.acall()` native async | DSPyBackend + OptimizedLM |
| pydantic-ai | 1.53.0 | `Agent.run()` native async | PydanticAIBackend |
| asyncio.create_subprocess_exec | stdlib | Async subprocess for CLI backend | ClaudeCLIBackend |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Native async | `asyncio.to_thread(sync_fn)` | Worse: wraps sync in thread, doesn't unlock parallelism |
| `asyncio.wait_for()` timeout | Manual timer + proc.kill() | Worse: more complex, no benefit |
| `anyio` | stdlib asyncio | Unnecessary: bae is asyncio-only, no trio support needed |

**Installation:**
No new packages needed. All async capabilities already present in installed dependencies.

## Architecture Patterns

### Recommended Conversion Order

```
Layer 0: LM Protocol (lm.py)     -- async def in Protocol class
Layer 1: Backends (lm.py backends, dspy_backend.py, optimized_lm.py)
Layer 2: Node.__call__ (node.py)  -- base class becomes async
Layer 3: Resolver (resolver.py)   -- resolve_dep, resolve_fields (Phase 12 adds gather)
Layer 4: Graph.run() (graph.py)   -- async def run(), await all calls
Layer 5: CompiledGraph.run() (compiler.py) -- delegates to Graph.run()
Layer 6: CLI boundary (cli.py)    -- asyncio.run() wraps graph.run()
Layer 7: Tests (~323 functions)   -- mechanical: add async def + await
```

### Pattern 1: Async LM Protocol
**What:** Convert the `LM` Protocol class to declare async methods.
**When to use:** Every LM backend must implement these.
**Example:**
```python
# Source: bae/lm.py (current)
@runtime_checkable
class LM(Protocol):
    def make(self, node: Node, target: type[T]) -> T: ...
    def decide(self, node: Node) -> Node | None: ...
    def choose_type(self, types: list[type[Node]], context: dict[str, object]) -> type[Node]: ...
    def fill(self, target: type[T], resolved: dict[str, object], instruction: str, source: Node | None = None) -> T: ...

# BECOMES:
@runtime_checkable
class LM(Protocol):
    async def make(self, node: Node, target: type[T]) -> T: ...
    async def decide(self, node: Node) -> Node | None: ...
    async def choose_type(self, types: list[type[Node]], context: dict[str, object]) -> type[Node]: ...
    async def fill(self, target: type[T], resolved: dict[str, object], instruction: str, source: Node | None = None) -> T: ...
```

### Pattern 2: DSPy Backend (acall)
**What:** Replace `predictor(**kwargs)` with `await predictor.acall(**kwargs)`.
**When to use:** Every `dspy.Predict` call in DSPyBackend and OptimizedLM.
**Example:**
```python
# Current:
result = predictor(**inputs)

# BECOMES:
result = await predictor.acall(**inputs)
```
**Verified:** DSPy 3.1.2 has `Predict.acall()` which delegates to `Predict.aforward()`. Both are genuinely async (call `adapter.acall()` which makes real async HTTP requests). Not a sync wrapper.

### Pattern 3: PydanticAI Backend (Agent.run)
**What:** Replace `agent.run_sync(prompt)` with `await agent.run(prompt)`.
**When to use:** Every `run_sync()` call in PydanticAIBackend.
**Example:**
```python
# Current:
result = agent.run_sync(prompt)

# BECOMES:
result = await agent.run(prompt)
```
**Verified:** PydanticAI 1.53.0 `Agent.run()` is `async def`. `run_sync()` is the convenience sync wrapper.

### Pattern 4: ClaudeCLI Backend (asyncio subprocess)
**What:** Replace `subprocess.run()` with `asyncio.create_subprocess_exec()`.
**When to use:** `ClaudeCLIBackend._run_cli_json()`.
**Example:**
```python
# Current:
result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)

# BECOMES:
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
try:
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(),
        timeout=self.timeout,
    )
except asyncio.TimeoutError:
    proc.kill()
    await proc.wait()
    raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")
```
**Key differences from subprocess.run():**
- `create_subprocess_exec` takes `*cmd` (splatted), not a list
- stdout/stderr come back as `bytes`, need `.decode("utf-8")`
- Timeout via `asyncio.wait_for()` wrapping `proc.communicate()`
- Must explicitly kill and wait on timeout (process doesn't auto-terminate)
- Return code via `proc.returncode` after communicate completes

### Pattern 5: Retry with async sleep
**What:** Replace `time.sleep(1)` with `await asyncio.sleep(1)`.
**When to use:** DSPyBackend._call_with_retry().
**Critical:** `time.sleep()` blocks the event loop. Must use `asyncio.sleep()`.

### Pattern 6: Graph.run() async loop
**What:** The main execution loop becomes async, awaiting each operation.
**Example:**
```python
# Current:
def run(self, start_node, lm=None, max_iters=10) -> GraphResult:
    ...
    resolved = resolve_fields(current.__class__, trace, dep_cache)
    ...
    current = current(lm)  # or current()
    ...
    target_type = lm.choose_type(types_list, context)
    current = lm.fill(target_type, target_resolved, instruction, source=current)

# BECOMES:
async def run(self, start_node, lm=None, max_iters=10) -> GraphResult:
    ...
    resolved = resolve_fields(current.__class__, trace, dep_cache)  # stays sync in Phase 11
    ...
    current = await current(lm)  # or await current()
    ...
    target_type = await lm.choose_type(types_list, context)
    current = await lm.fill(target_type, target_resolved, instruction, source=current)
```
**Note:** `resolve_fields` stays sync in Phase 11. Phase 12 makes it async for parallel gather.

### Pattern 7: CLI asyncio.run() boundary
**What:** Typer commands stay sync, call `asyncio.run()` to enter async.
**Example:**
```python
# Current:
result = graph.run(start_node, lm=lm)

# BECOMES:
result = asyncio.run(graph.run(start_node, lm=lm))
```
**Typer stays sync** because Typer/Click don't support async command handlers.

### Pattern 8: Node.__call__ async
**What:** Base Node.__call__ and all subclass __call__ become async.
**Example:**
```python
# Current (base class):
def __call__(self, lm: LM) -> Node | None:
    return lm.decide(self)

# BECOMES:
async def __call__(self, lm: LM) -> Node | None:
    return await lm.decide(self)

# Current (user subclass - custom logic):
def __call__(self, lm: LM) -> Review | None:
    return lm.decide(self)

# BECOMES:
async def __call__(self, lm: LM) -> Review | None:
    return await lm.decide(self)

# Current (user subclass - ellipsis body):
def __call__(self, lm: LM) -> TargetA: ...
# BECOMES:
async def __call__(self, lm: LM) -> TargetA: ...
```
**Impact:** ALL user-defined nodes must change `def __call__` to `async def __call__`. This is a breaking API change.

### Pattern 9: Mock LM in Tests
**What:** Mock LM classes in tests must also become async.
**Example:**
```python
# Current:
class MockLM:
    def make(self, node, target):
        return self.sequence[self.index]

# BECOMES:
class MockLM:
    async def make(self, node, target):
        return self.sequence[self.index]
```
**Note:** Even though mock methods don't actually do I/O, they must be `async def` because callers `await` them.

### Anti-Patterns to Avoid
- **`asyncio.to_thread()` for LM calls:** Don't wrap sync calls in threads. Use native async APIs instead. The whole point is native async.
- **Mixing sync and async backend methods:** All four LM protocol methods must be async. Don't leave some sync.
- **`time.sleep()` in async code:** Blocks the event loop. Always use `await asyncio.sleep()`.
- **`subprocess.run()` in async code:** Blocks the event loop. Use `asyncio.create_subprocess_exec()`.
- **Forgetting `await` on coroutines:** Silent bug. The coroutine object is truthy, so `if await_me()` passes but doesn't execute. Python 3.14 warns about this.
- **Converting resolve_fields to async in Phase 11:** Phase 12 handles this. Keep it sync for now.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async subprocess timeout | Manual timer + signals | `asyncio.wait_for(proc.communicate(), timeout=N)` | Handles edge cases (zombie processes, cleanup) |
| Async retries | Custom retry decorator | Keep existing loop pattern, just replace `time.sleep` with `asyncio.sleep` | The retry loop is simple enough; a decorator adds complexity |
| Event loop management | Manual `loop.run_until_complete()` | `asyncio.run()` | `asyncio.run()` handles loop lifecycle correctly |
| Async Protocol checking | Custom isinstance check for async methods | Accept that `runtime_checkable` doesn't verify async-ness | Python limitation; document it, don't fight it |

**Key insight:** This conversion is mechanical, not architectural. Every sync call becomes `await async_call`. No new abstractions needed.

## Common Pitfalls

### Pitfall 1: Forgetting `await` on coroutine calls
**What goes wrong:** `result = lm.fill(...)` returns a coroutine object, not the actual result. Since coroutines are truthy, control flow proceeds but with wrong values. Types break silently.
**Why it happens:** Missing a single `await` when converting many call sites.
**How to avoid:** After conversion, run mypy or grep for `DeprecationWarning: coroutine .* was never awaited` in test output. Python 3.14+ warns about unawaited coroutines.
**Warning signs:** Tests pass but with unexpected types. `isinstance(result, CoroutineType)` instead of expected type.

### Pitfall 2: Blocking calls in async code
**What goes wrong:** `time.sleep()` or `subprocess.run()` blocks the event loop. In Phase 12, this would prevent parallel dep resolution from working.
**Why it happens:** Easy to miss during conversion — the code "works" but blocks.
**How to avoid:** Grep for `time.sleep` and `subprocess.run` in all async code paths. Replace with `asyncio.sleep` and `asyncio.create_subprocess_exec`.
**Warning signs:** No concurrency benefit from async. Tests pass but are slow.

### Pitfall 3: Mock LMs not matching async Protocol
**What goes wrong:** Test mock LMs have sync methods. When production code `await`s them, it gets a non-coroutine. Error: `TypeError: object X can't be used in 'await' expression`.
**Why it happens:** Tests are converted to `async def` but mock classes inside them still have sync methods.
**How to avoid:** Convert ALL mock LM classes (there are ~5 across test files) to have `async def` methods. Search for `class Mock` in tests.
**Warning signs:** `TypeError: object X can't be used in 'await' expression` in test output.

### Pitfall 4: `_has_ellipsis_body` and `get_type_hints` with async
**What goes wrong:** Could break ellipsis detection or type hint extraction for async methods.
**Why it happens:** AST has `AsyncFunctionDef` instead of `FunctionDef`.
**How to avoid:** Already handled: `_has_ellipsis_body` checks for both `ast.FunctionDef` and `ast.AsyncFunctionDef`. `get_type_hints()` works identically on async methods. Verified in research.
**Warning signs:** Auto-routing stops working (all nodes detected as "custom").

### Pitfall 5: runtime_checkable Protocol doesn't verify async-ness
**What goes wrong:** A class with sync `def make(...)` passes `isinstance(obj, LM)` even after LM Protocol methods are async.
**Why it happens:** `runtime_checkable` only checks attribute existence, not whether the attribute is a coroutine function.
**How to avoid:** Accept this limitation. Document it. If runtime validation is needed, use `inspect.iscoroutinefunction()` explicitly. But in practice, the `await` at call sites will catch mismatches at runtime.
**Warning signs:** None (until you actually try to `await` a sync method).

### Pitfall 6: Async subprocess cleanup on timeout
**What goes wrong:** Process left running after timeout. Resource leak.
**Why it happens:** `asyncio.wait_for` raises `TimeoutError` but doesn't kill the subprocess.
**How to avoid:** Always `proc.kill(); await proc.wait()` in the except block.
**Warning signs:** Orphaned `claude` processes in `ps aux`.

### Pitfall 7: Converting tests that don't need conversion
**What goes wrong:** Wasted effort converting 323 tests when many don't call async methods.
**Why it happens:** Shotgun approach to test conversion.
**How to avoid:** Only tests that call: `graph.run()`, `lm.make()`, `lm.decide()`, `lm.choose_type()`, `lm.fill()`, `node()` (call), `resolve_dep()` (Phase 12), `resolve_fields()` (Phase 12) need conversion. Tests for pure functions like `classify_fields()`, `_build_plain_model()`, `_has_ellipsis_body()`, `node_to_signature()`, `trace_to_examples()` stay sync.
**Warning signs:** Large diffs with no functional change.

## Code Examples

### DSPyBackend.fill() async conversion
```python
# Source: Verified against dspy 3.1.2 Predict.acall()
async def fill(self, target, resolved, instruction, source=None):
    signature = node_to_signature(target, is_start=False)
    predictor = dspy.Predict(signature)
    result = await self._call_with_retry(predictor, resolved)
    all_fields = dict(resolved)
    for key in result.keys():
        if key not in resolved:
            all_fields[key] = getattr(result, key)
    return target.model_construct(**all_fields)
```

### DSPyBackend._call_with_retry() async conversion
```python
# Source: asyncio.sleep replaces time.sleep
async def _call_with_retry(self, predictor, inputs, error_hint=None):
    if error_hint:
        inputs = {**inputs, "parse_error": error_hint}
    last_error = None
    for attempt in range(self.max_retries + 1):
        try:
            return await predictor.acall(**inputs)
        except API_RETRY_EXCEPTIONS as e:
            last_error = e
            if attempt < self.max_retries:
                await asyncio.sleep(1)
                continue
            raise BaeLMError(str(e), cause=e) from e
    raise BaeLMError("Unexpected error", cause=last_error)
```

### ClaudeCLIBackend._run_cli_json() async conversion
```python
# Source: Python 3.14 asyncio subprocess docs
async def _run_cli_json(self, prompt, schema):
    import json
    clean_schema = _strip_format(schema)
    cmd = ["claude", "-p", prompt, "--model", self.model,
           "--output-format", "json",
           "--json-schema", json.dumps(clean_schema),
           "--no-session-persistence",
           "--tools", "",
           "--strict-mcp-config",
           "--setting-sources", ""]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=self.timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")

    stdout = stdout_bytes.decode("utf-8")
    stderr = stderr_bytes.decode("utf-8")

    if proc.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {stderr}")

    data = json.loads(stdout)
    # ... same extraction logic as before
```

### PydanticAIBackend.fill() async conversion
```python
# Source: Verified against pydantic-ai 1.53.0 Agent.run()
async def fill(self, target, resolved, instruction, source=None):
    plain_model = _build_plain_model(target)
    agent = self._get_agent((plain_model,), allow_none=False)
    prompt = _build_fill_prompt(target, resolved, instruction, source)
    result = await agent.run(prompt)  # was: agent.run_sync(prompt)
    all_fields = dict(resolved)
    plain_output = result.output
    if isinstance(plain_output, BaseModel):
        all_fields.update(plain_output.model_dump())
    return target.model_construct(**all_fields)
```

### Test conversion pattern
```python
# Current:
class TestGraphRun:
    def test_run_simple_path(self):
        graph = Graph(start=Start)
        lm = MockLM(sequence=[Process(task="do it"), None])
        result = graph.run(Start(query="hello"), lm=lm)
        assert isinstance(result, GraphResult)

# BECOMES:
class TestGraphRun:
    async def test_run_simple_path(self):
        graph = Graph(start=Start)
        lm = MockLM(sequence=[Process(task="do it"), None])
        result = await graph.run(Start(query="hello"), lm=lm)
        assert isinstance(result, GraphResult)
```
With `asyncio_mode = "auto"`, no `@pytest.mark.asyncio` decorator needed.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `agent.run_sync()` | `await agent.run()` | pydantic-ai was always async-first | Direct performance + concurrency |
| `predictor(**kwargs)` | `await predictor.acall(**kwargs)` | dspy 2.x+ added acall | Native async LLM calls |
| `subprocess.run()` | `asyncio.create_subprocess_exec()` | Python 3.4+ (always existed) | Non-blocking subprocess |
| `time.sleep()` | `await asyncio.sleep()` | Python 3.4+ (always existed) | Non-blocking delay |

**Deprecated/outdated:**
- `asyncio.iscoroutinefunction()`: Deprecated in Python 3.14, slated for removal in 3.16. Use `inspect.iscoroutinefunction()` instead. (Already seen in litellm deprecation warning.)
- `asyncio.get_event_loop()`: Deprecated for getting/creating loops. Use `asyncio.run()` at boundaries.

## Test Impact Analysis

### Tests that MUST become async (call converted methods)
| Test File | Tests | Reason |
|-----------|-------|--------|
| test_graph.py | 3 tests | Call `graph.run()` |
| test_auto_routing.py | ~6 tests | Call `graph.run()` |
| test_dep_injection.py | ~8 tests | Call `graph.run()` |
| test_fill_protocol.py | ~5 tests | Call `graph.run()` or backend.fill() |
| test_lm_protocol.py | ~10 tests | Call backend methods (choose_type/fill) |
| test_dspy_backend.py | ~15 tests | Call backend methods (make/decide/fill) |
| test_optimized_lm.py | ~6 tests | Call backend.make() |
| test_integration.py | ~3 tests | Call `graph.run()` |
| test_integration_dspy.py | ~12 tests | Call `graph.run()` with real DSPy |
| test_ootd_e2e.py | ~1 test | Call `graph.run()` |
| test_node.py | ~4 tests | Call `node()` directly |
| test_node_config.py | ~8 tests | Call `node()` or `graph.run()` |

### Tests that stay sync (pure functions, no I/O)
| Test File | Tests | Reason |
|-----------|-------|--------|
| test_resolver.py | ~30 tests | `classify_fields`, `recall_from_trace`, `build_dep_dag`, `validate_node_deps` are sync |
| test_resolver.py | ~14 tests | `resolve_dep`, `resolve_fields` stay sync in Phase 11 |
| test_compiler.py | ~10 tests | `node_to_signature`, `compile_graph` are sync |
| test_signature_v2.py | ~13 tests | `node_to_signature` is sync |
| test_exceptions.py | ~14 tests | Exception construction is sync |
| test_result.py | ~11 tests | `GraphResult` construction is sync |
| test_result_v2.py | ~11 tests | `GraphResult` construction is sync |
| test_fill_helpers.py | ~20 tests | `_build_plain_model`, `validate_plain_fields` are sync |
| test_optimizer.py | ~36 tests | `trace_to_examples`, metrics are sync |

**Estimated:** ~80 tests need async conversion, ~240 stay sync.

### Mock classes that must become async
Located via grep for `class Mock` and `class Capturing` in test files:
1. `test_graph.py::MockLM` - 4 methods
2. `test_auto_routing.py::MockLM` - 4 methods
3. `test_dep_injection.py::MockV2LM` - 4 methods
4. `test_fill_protocol.py::CapturingLM` - 4 methods
5. `test_node_config.py` - check for mock LMs

## Open Questions

1. **resolve_dep/resolve_fields: sync or async in Phase 11?**
   - What we know: Phase 11 keeps resolver sync. Phase 12 makes it async for parallel gather.
   - What's unclear: Dep functions themselves are currently sync (`def get_weather() -> ...`). When Phase 12 adds async dep support, `resolve_dep` will need `inspect.iscoroutinefunction()` to detect and `await` async deps.
   - Recommendation: Leave resolver sync in Phase 11. The roadmap already calls this out.

2. **User-facing `__call__` must become `async def` - migration story?**
   - What we know: Every subclass of Node must change `def __call__` to `async def __call__`. This is a breaking change.
   - What's unclear: How to communicate this to users. No users yet (pre-v1.0), so not urgent.
   - Recommendation: Just do it. Document in changelog. No backward compat shim.

3. **CompiledGraph.run() async**
   - What we know: It delegates to `graph.run()` which becomes async.
   - What's unclear: Nothing. It's trivial: `async def run(self, start_node) -> GraphResult: ... return await self.graph.run(start_node, lm=lm)`
   - Recommendation: Convert in same pass as graph.py.

4. **CLI `_start` attribute bug**
   - What we know: `cli.py` references `graph._start` but Graph stores `self.start`. Pre-existing bug.
   - What's unclear: Whether this CLI path is actually used/tested.
   - Recommendation: Fix it during async conversion of cli.py (change `_start` to `start`).

## Sources

### Primary (HIGH confidence)
- **DSPy 3.1.2 installed source** - Verified `Predict.acall()`, `Predict.aforward()`, `Module.acall()` are genuinely async via `inspect.getsource()`. Not wrappers.
- **PydanticAI 1.53.0 installed source** - Verified `Agent.run()` is `async def`, `Agent.run_sync()` is sync wrapper.
- **Python 3.14 stdlib** - `asyncio.create_subprocess_exec()`, `asyncio.wait_for()`, `asyncio.sleep()`.
- **pytest-asyncio 1.3.0** - `asyncio_mode = "auto"` auto-collects `async def test_*` without decorator.
- **bae codebase inspection** - All source files and test files read and analyzed.

### Secondary (MEDIUM confidence)
- [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io/en/stable/concepts.html) - auto mode documentation, verified via WebFetch
- [Python subprocess docs](https://docs.python.org/3/library/asyncio-subprocess.html) - create_subprocess_exec patterns

### Tertiary (LOW confidence)
- None. All findings verified against installed source or official docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries verified against installed versions via inspect.getsource()
- Architecture: HIGH - Conversion pattern is mechanical, verified each step against real APIs
- Pitfalls: HIGH - Each pitfall verified by running code in the bae venv

**Research date:** 2026-02-08
**Valid until:** 2026-03-08 (stable: pinned library versions, stdlib APIs)
