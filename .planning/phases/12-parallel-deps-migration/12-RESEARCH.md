# Phase 12: Parallel Deps + Migration - Research

**Researched:** 2026-02-08
**Domain:** asyncio.gather-based concurrent dep resolution, sync/async callable coexistence, run/arun API split
**Confidence:** HIGH

## Summary

Phase 12 converts the dep resolution pipeline from sequential to concurrent. The current `resolve_dep()` resolves deps recursively one at a time; the new version uses `graphlib.TopologicalSorter.prepare()/get_ready()/done()` to identify independent callables per topo level and fires them concurrently via `asyncio.gather()`. Both sync and async dep callables are supported through runtime detection with `inspect.iscoroutinefunction()`, with sync callables wrapped in a thin coroutine.

The migration also restores a sync public API: `Graph.run()` becomes sync (wrapping `asyncio.run(self.arun(...))`) and `Graph.arun()` becomes the native async version. `resolve_dep()` and `resolve_fields()` become `async def` in-place with no dual sync/async versions.

All key mechanisms have been verified against Python 3.14 stdlib on the actual bae codebase. The `build_dep_dag()` function already exists and produces correct topo levels (verified with OOTD example: level 0 = `[get_location, get_schedule]`, level 1 = `[get_weather]`). `asyncio.gather()` preserves result ordering, cancels remaining tasks on first failure, and propagates the raw exception (no ExceptionGroup).

**Primary recommendation:** Restructure `resolve_fields()` to be the async orchestrator -- it builds the dep DAG, walks levels with `get_ready()`, gathers each level, caches results, then resolves recalls concurrently alongside the first dep level. `resolve_dep()` changes from recursive to single-callable resolution (transitive deps already resolved by earlier topo levels).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | Python 3.14.2 | `gather()`, event loop | Built-in, already used throughout |
| graphlib (stdlib) | Python 3.14.2 | `TopologicalSorter` for level-by-level DAG iteration | Built-in, already used for validation |
| inspect (stdlib) | Python 3.14.2 | `iscoroutinefunction()` for sync/async detection | Built-in, correct approach per Python docs |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | 1.3.0 | Async test collection (`asyncio_mode="auto"`) | Already configured in pyproject.toml |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.gather()` | `asyncio.TaskGroup` (3.11+) | TaskGroup raises ExceptionGroup, contradicts decision to propagate first error raw |
| `inspect.iscoroutinefunction` | `asyncio.iscoroutinefunction` | Deprecated in 3.14, removed in 3.16. Use `inspect` version. |
| Thin coroutine wrapper | `asyncio.to_thread()` | Decision locked: NOT to_thread. Wrapper is simpler, no thread pool overhead for pure computation deps |

**Installation:**
No new packages needed. Everything is stdlib or already installed.

## Architecture Patterns

### Recommended resolve_fields Restructure

The core architectural change: `resolve_fields()` becomes the async orchestrator that replaces the sequential field-by-field approach with DAG-level-by-level gather.

```
Before (sequential):
  for field in node_cls fields:
    if Dep: resolve_dep(fn, cache)     # recursive, one at a time
    if Recall: recall_from_trace(...)

After (concurrent):
  1. Classify all fields (dep vs recall vs plain)
  2. Build dep DAG from all dep callables
  3. For each topo level:
     - gather all ready callables (async)
     - cache results
     - mark done
  4. Map cached results back to field names
  5. Gather recall resolutions concurrently (or inline -- they're pure computation)
```

### Pattern 1: Level-by-Level Gather
**What:** Use `TopologicalSorter.prepare()` + `get_ready()` + `done()` to walk the dep DAG level by level, gathering all ready callables in each level.
**When to use:** Inside `resolve_fields()` for dep resolution.
**Verified:** Yes, with actual OOTD dep functions (see below).
**Example:**
```python
# Source: Verified against Python 3.14.2 graphlib + bae's build_dep_dag()
async def resolve_fields(node_cls, trace, dep_cache):
    # 1. Classify fields
    hints = get_type_hints(node_cls, include_extras=True)
    dep_fields = {}   # field_name -> callable
    recall_fields = {}  # field_name -> base_type

    for field_name, hint in hints.items():
        if field_name == "return":
            continue
        if get_origin(hint) is not Annotated:
            continue
        args = get_args(hint)
        base_type = args[0]
        for m in args[1:]:
            if isinstance(m, Dep) and m.fn is not None:
                dep_fields[field_name] = m.fn
                break
            if isinstance(m, Recall):
                recall_fields[field_name] = base_type
                break

    # 2. Resolve deps level-by-level via topo sort
    if dep_fields:
        dag = build_dep_dag(node_cls)
        dag.prepare()
        while dag.is_active():
            ready = dag.get_ready()
            # Filter out already-cached callables
            to_resolve = [fn for fn in ready if fn not in dep_cache]
            if to_resolve:
                results = await asyncio.gather(
                    *[_resolve_one(fn, dep_cache) for fn in to_resolve]
                )
                for fn, result in zip(to_resolve, results):
                    dep_cache[fn] = result
            for fn in ready:
                dag.done(fn)

    # 3. Build resolved dict
    resolved = {}
    for field_name, fn in dep_fields.items():
        resolved[field_name] = dep_cache[fn]
    for field_name, base_type in recall_fields.items():
        resolved[field_name] = recall_from_trace(trace, base_type)

    return resolved
```

### Pattern 2: Thin Coroutine Wrapper for Sync Deps
**What:** Wrap sync callables in an async wrapper so they can participate in `asyncio.gather()`.
**When to use:** In `_resolve_one()` when the dep callable is not a coroutine function.
**Verified:** Yes, tested with Python 3.14.2.
**Example:**
```python
# Source: Verified against Python 3.14.2 inspect + asyncio
async def _resolve_one(fn, cache):
    """Resolve a single dep callable, handling sync/async uniformly."""
    # Build kwargs from fn's own Dep-annotated params (already in cache from earlier levels)
    hints = get_type_hints(fn, include_extras=True)
    kwargs = {}
    for param_name, hint in hints.items():
        if param_name == "return":
            continue
        if get_origin(hint) is Annotated:
            for m in get_args(hint)[1:]:
                if isinstance(m, Dep) and m.fn is not None:
                    kwargs[param_name] = cache[m.fn]  # guaranteed by topo ordering
                    break

    if inspect.iscoroutinefunction(fn):
        return await fn(**kwargs)
    else:
        return fn(**kwargs)
```

### Pattern 3: run() / arun() Split
**What:** `Graph.arun()` is the native async implementation. `Graph.run()` is the sync convenience wrapper.
**When to use:** Public API entry points.
**Verified:** `asyncio.run()` cannot be called from within a running event loop (raises `RuntimeError`), confirming the need for both variants.
**Example:**
```python
# Source: Verified against Python 3.14.2 asyncio.run()
class Graph:
    def run(self, start_node, lm=None, max_iters=10) -> GraphResult:
        """Sync entry point. Cannot be called from within an event loop."""
        return asyncio.run(self.arun(start_node, lm=lm, max_iters=max_iters))

    async def arun(self, start_node, lm=None, max_iters=10) -> GraphResult:
        """Async entry point. Use when already in an event loop."""
        # ... current run() body, but with await resolve_fields(...)
```

### Pattern 4: DepError Wrapping in resolve_fields
**What:** Wrap dep function exceptions in `DepError(node_type, field_name, cause)` at the `resolve_fields` level, not in `graph.run()`.
**When to use:** When a dep callable raises during resolution.
**Why:** `resolve_fields` knows both the field name and the node type. The current wrapping in `graph.run()` loses field-level granularity.
**Example:**
```python
# In resolve_fields, wrap the gather call:
try:
    results = await asyncio.gather(
        *[_resolve_one(fn, dep_cache) for fn in to_resolve]
    )
except Exception as e:
    # Find which field this callable belongs to
    field_name = next(
        (name for name, dep_fn in dep_fields.items() if dep_fn is fn_that_failed),
        "",
    )
    raise DepError(
        f"Dep function failed: {e}",
        node_type=node_cls,
        field_name=field_name,
        cause=e,
    ) from e
```

**Challenge:** With `gather(return_exceptions=False)`, the exception propagates from the first failing coroutine, but we don't directly know which callable failed. Two approaches:

**Approach A (recommended):** Wrap each `_resolve_one` call individually to capture field context:
```python
async def _resolve_one_wrapped(fn, cache, node_cls, field_name):
    try:
        return await _resolve_one(fn, cache)
    except Exception as e:
        raise DepError(
            f"Dep function {_callable_name(fn)} failed: {e}",
            node_type=node_cls,
            field_name=field_name,
            cause=e,
        ) from e
```

**Approach B:** Let the exception propagate raw from `_resolve_one`, then wrap at the `resolve_fields` level. Simpler but loses field name for transitive dep failures (transitive deps don't map to a single field).

For transitive dep failures, the `field_name` should be empty string since the failing callable may not correspond to any field directly -- it could be a deep transitive dep. The `cause` chain gives the full story.

### Anti-Patterns to Avoid
- **Using `asyncio.TaskGroup` instead of `asyncio.gather()`:** TaskGroup wraps exceptions in ExceptionGroup, contradicting the locked decision to propagate first error raw.
- **Adding semaphores/concurrency limits:** Explicitly deferred. All ready deps fire without throttling.
- **Keeping recursive `resolve_dep()` alongside topo-sort gather:** The recursive approach is incompatible with level-by-level gather. Replace it entirely.
- **Running `recall_from_trace` through the async gather pipeline:** Recall is pure computation (walks a list in memory). No I/O benefit from async. Can be called directly (sync) after dep resolution, or gathered alongside first dep level if desired.
- **Nested `asyncio.run()` inside `arun()`:** Will raise `RuntimeError`. The sync `run()` must be a standalone boundary.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Topological level iteration | Manual BFS/DFS with visited set | `graphlib.TopologicalSorter.prepare()/get_ready()/done()` | Already in stdlib, already used in codebase for validation |
| Coroutine function detection | Duck-typing or try/except | `inspect.iscoroutinefunction(fn)` | Handles all edge cases (partials, bound methods, etc.) |
| Concurrent task dispatch | Manual task creation + wait | `asyncio.gather(*coros)` | Preserves result ordering, handles cancellation, simpler |
| Sync-to-async bridge | `asyncio.to_thread()` or `loop.run_in_executor()` | `async def w(): return fn(**kwargs)` | Decision locked: thin wrapper, not thread pool |
| Event loop entry | `loop.run_until_complete()` | `asyncio.run()` | Handles loop lifecycle, cleanup |

**Key insight:** This phase is about wiring together stdlib primitives (`graphlib.TopologicalSorter`, `asyncio.gather`, `inspect.iscoroutinefunction`) that already exist. No custom concurrency primitives needed.

## Common Pitfalls

### Pitfall 1: gather Does NOT Cancel for Sync-Wrapped Deps
**What goes wrong:** Sync-wrapped deps (`async def w(): return fn()`) complete immediately (no `await` suspension point inside), so `asyncio.gather` can't actually cancel them once started. The "fail fast" behavior only cancels tasks that haven't completed yet.
**Why it matters:** For sync deps, all tasks in a level will run to completion even if one fails early. This is acceptable (sync deps are fast, pure computation), but worth understanding.
**How to avoid:** This is inherent and fine. True async deps (with `await` inside) will benefit from cancellation.
**Warning signs:** None -- this is expected behavior.

### Pitfall 2: Forgetting `await` on resolve_fields After Conversion
**What goes wrong:** `graph.run()` calls `resolve_fields()` which is now async. Missing `await` means `resolved` is a coroutine object, not a dict. Subsequent `for field_name, value in resolved.items()` fails with `AttributeError`.
**Why it happens:** `resolve_fields` is called twice in `graph.run()` (once for current node, once for target node before fill). Easy to miss one.
**How to avoid:** Both calls must become `await resolve_fields(...)`. Grep for all call sites.
**Warning signs:** `AttributeError: 'coroutine' object has no attribute 'items'` or `RuntimeWarning: coroutine 'resolve_fields' was never awaited`.

### Pitfall 3: Tests Calling resolve_dep/resolve_fields Must Become Async
**What goes wrong:** `test_resolver.py` has ~14 tests directly calling `resolve_dep()` and `resolve_fields()`. These are currently sync tests. After conversion, they must become `async def` tests.
**Why it happens:** These functions change from sync to async.
**How to avoid:** Convert all `TestResolveDep` and `TestResolveFields` test methods to `async def` and add `await`. With `asyncio_mode="auto"`, no decorators needed.
**Warning signs:** `TypeError: 'coroutine' object is not subscriptable` or similar.

### Pitfall 4: resolve_dep Signature Change Breaks Imports
**What goes wrong:** `resolve_dep` is currently exported from `bae.resolver` and imported in tests. If the function signature changes (e.g., it now requires a DAG context), callers break.
**Why it happens:** The refactoring changes `resolve_dep`'s role from "recursive resolver" to "single-callable resolver".
**How to avoid:** Keep `resolve_dep` as a public function but change its semantics. Or rename to `_resolve_one` (private) and let `resolve_fields` be the only public async API. The test file imports `resolve_dep` -- decide whether to keep it as a public API or make tests call through `resolve_fields`.
**Recommendation:** Keep `resolve_dep` as a thin async wrapper for backward compatibility and direct testing. It resolves a single callable with its transitive deps via the topo-sort approach. Tests can still call it directly.

### Pitfall 5: DepError.field_name Empty for Transitive Dep Failures
**What goes wrong:** When a transitive dep (not directly on the node, but a dep-of-a-dep) fails, there's no single `field_name` to attribute the error to.
**Why it matters:** The DepError constructor takes `field_name` -- what to put there?
**How to avoid:** Use empty string for transitive dep failures. The `cause` chain provides the full story. For direct dep failures, include the field name.
**Warning signs:** Tests that assert `err.field_name == "some_field"` may need updating.

### Pitfall 6: asyncio.run() in Graph.run() vs Existing Tests
**What goes wrong:** All existing tests call `await graph.run(...)` (async). If `graph.run()` becomes sync (calls `asyncio.run()` internally), these tests will get `RuntimeError: asyncio.run() cannot be called from a running event loop` because pytest-asyncio already has an event loop running.
**Why it matters:** This is the most impactful migration issue. Every test that currently does `await graph.run()` must change to `await graph.arun()`.
**How to avoid:** Two-step migration: (1) rename current `async def run()` to `async def arun()`, (2) add sync `def run()` that calls `asyncio.run(self.arun(...))`. Update all tests to call `arun()`. Update ootd.py to call `graph.run()` (sync, from `__main__` context).
**Warning signs:** `RuntimeError: asyncio.run() cannot be called from a running event loop` in test output.

### Pitfall 7: build_dep_dag Returns Callables, Not Field Names
**What goes wrong:** The topo sort produces levels of callables, but `resolve_fields` needs to map results back to field names.
**Why it matters:** After gathering all dep results in the cache (keyed by callable), the final step is building `{field_name: dep_cache[callable]}`.
**How to avoid:** Maintain a `dep_fields: dict[str, callable]` mapping from field name to callable. After all topo levels resolved, iterate this mapping to build the result dict.
**Warning signs:** Results dict has callable objects as keys instead of field names.

## Code Examples

### Complete resolve_fields Async Implementation
```python
# Source: Designed from verified stdlib APIs
async def resolve_fields(node_cls: type, trace: list, dep_cache: dict) -> dict[str, object]:
    """Resolve all Dep and Recall fields on a Node subclass concurrently.

    Dep fields are resolved level-by-level via topological sort, with
    independent deps in each level fired concurrently via asyncio.gather().
    Recall fields are resolved after deps (pure computation, no I/O).
    """
    resolved: dict[str, object] = {}
    hints = get_type_hints(node_cls, include_extras=True)

    dep_fields: dict[str, object] = {}     # field_name -> callable
    recall_fields: dict[str, type] = {}     # field_name -> base_type

    for field_name, hint in hints.items():
        if field_name == "return":
            continue
        if get_origin(hint) is not Annotated:
            continue
        args = get_args(hint)
        base_type = args[0]
        metadata = args[1:]
        for m in metadata:
            if isinstance(m, Dep) and m.fn is not None:
                dep_fields[field_name] = m.fn
                break
            if isinstance(m, Recall):
                recall_fields[field_name] = base_type
                break

    # Resolve deps via topo-sort levels
    if dep_fields:
        dag = build_dep_dag(node_cls)
        dag.prepare()
        while dag.is_active():
            ready = dag.get_ready()
            to_resolve = [fn for fn in ready if fn not in dep_cache]
            if to_resolve:
                results = await asyncio.gather(
                    *[_resolve_one(fn, dep_cache) for fn in to_resolve]
                )
                for fn, result in zip(to_resolve, results):
                    dep_cache[fn] = result
            for fn in ready:
                dag.done(fn)

        # Map cached results to field names
        for field_name, fn in dep_fields.items():
            resolved[field_name] = dep_cache[fn]

    # Resolve recalls (pure computation, no I/O)
    for field_name, base_type in recall_fields.items():
        resolved[field_name] = recall_from_trace(trace, base_type)

    return resolved
```

### Single-Callable Resolver
```python
# Source: Designed from verified stdlib APIs
async def _resolve_one(fn: object, cache: dict) -> object:
    """Resolve a single dep callable. Transitive deps already in cache."""
    hints = get_type_hints(fn, include_extras=True)
    kwargs: dict[str, object] = {}

    for param_name, hint in hints.items():
        if param_name == "return":
            continue
        if get_origin(hint) is Annotated:
            for m in get_args(hint)[1:]:
                if isinstance(m, Dep) and m.fn is not None:
                    kwargs[param_name] = cache[m.fn]  # guaranteed by topo order
                    break

    if inspect.iscoroutinefunction(fn):
        return await fn(**kwargs)
    else:
        return fn(**kwargs)
```

### Graph.run() / arun() Split
```python
# Source: Verified against Python 3.14.2 asyncio.run() behavior
class Graph:
    def run(self, start_node, lm=None, max_iters=10) -> GraphResult:
        """Execute the graph synchronously.

        Convenience wrapper around arun() for callers not in an event loop.
        Cannot be called from within a running event loop.
        """
        return asyncio.run(self.arun(start_node, lm=lm, max_iters=max_iters))

    async def arun(self, start_node, lm=None, max_iters=10) -> GraphResult:
        """Execute the graph asynchronously.

        Native async version for callers already in an event loop.
        """
        # ... current run() body with await resolve_fields(...)
```

### Test Migration Pattern
```python
# Before (current):
class TestResolveDep:
    def test_resolve_leaf_dep(self):
        cache = {}
        result = resolve_dep(get_location, cache)
        assert result == "NYC"

# After:
class TestResolveDep:
    async def test_resolve_leaf_dep(self):
        cache = {}
        result = await resolve_dep(get_location, cache)
        assert result == "NYC"

# Before (graph tests):
class TestGraphRun:
    async def test_run_simple_path(self):
        result = await graph.run(start, lm=lm)

# After:
class TestGraphRun:
    async def test_run_simple_path(self):
        result = await graph.arun(start, lm=lm)
```

### OOTD.py Migration
```python
# Before:
if __name__ == "__main__":
    import asyncio
    result = asyncio.run(graph.run(IsTheUserGettingDressed(user_message="ugh i just got up")))

# After:
if __name__ == "__main__":
    result = graph.run(IsTheUserGettingDressed(user_message="ugh i just got up"))
    # graph.run() is now sync -- calls asyncio.run() internally
```

## Key Verified Behaviors

All behaviors verified against Python 3.14.2 on the bae venv:

| Behavior | Verified | Notes |
|----------|----------|-------|
| `TopologicalSorter.prepare()/get_ready()/done()` with function objects as nodes | YES | Works with actual OOTD dep functions |
| OOTD dep DAG produces 2 levels: `[get_location, get_schedule]` then `[get_weather]` | YES | Verified with `build_dep_dag(AnticipateUsersDay)` |
| `asyncio.gather()` preserves result order | YES | Results match input order regardless of completion order |
| `asyncio.gather(return_exceptions=False)` cancels remaining tasks on first failure | YES | Remaining tasks receive CancelledError |
| `asyncio.gather()` propagates first exception raw (no ExceptionGroup) | YES | ValueError propagates directly |
| `inspect.iscoroutinefunction()` works on regular funcs, async funcs, partials | YES | Correct for all tested cases |
| `inspect.iscoroutinefunction` is NOT deprecated (unlike `asyncio.iscoroutinefunction`) | YES | Python 3.14.2 |
| `asyncio.run()` cannot be nested in running event loop | YES | Raises `RuntimeError` |
| Sync-wrapped coroutine (`async def w(): return fn()`) works in gather | YES | Returns correct result |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `graph.run()` async only | `graph.run()` sync + `graph.arun()` async | Phase 12 | Better public API |
| Sequential `resolve_dep()` recursion | Topo-level `asyncio.gather()` | Phase 12 | Concurrent dep resolution |
| Sync-only dep callables | Sync + async via `inspect.iscoroutinefunction` | Phase 12 | Async I/O deps become possible |
| `asyncio.iscoroutinefunction()` | `inspect.iscoroutinefunction()` | Python 3.14 deprecation | Must use `inspect` version |

## Migration Impact Analysis

### Files that MUST change

| File | Change | Scope |
|------|--------|-------|
| `bae/resolver.py` | `resolve_dep` -> async, `resolve_fields` -> async with gather | Core implementation |
| `bae/graph.py` | `run()` -> sync wrapper, add `arun()` async, `await resolve_fields()` | API change |
| `bae/__init__.py` | No change needed (exports stay the same) | None |
| `examples/ootd.py` | Remove `asyncio.run()` wrapper, call `graph.run()` directly | Simplification |
| `tests/test_resolver.py` | ~14 tests for resolve_dep/resolve_fields become async | Mechanical |
| `tests/test_dep_injection.py` | `await graph.run()` -> `await graph.arun()` | Rename |
| `tests/test_graph.py` | `await graph.run()` -> `await graph.arun()` | Rename |
| `tests/test_auto_routing.py` | `await graph.run()` -> `await graph.arun()` | Rename |
| `tests/test_fill_protocol.py` | `await graph.run()` -> `await graph.arun()` (if used) | Rename |
| `tests/test_node_config.py` | `await graph.run()` -> `await graph.arun()` (if used) | Rename |
| `tests/test_integration.py` | `await graph.run()` -> `await graph.arun()` (if used) | Rename |
| `tests/test_integration_dspy.py` | `await graph.run()` -> `await graph.arun()` (if used) | Rename |
| `tests/test_ootd_e2e.py` | `await graph.run()` -> `await graph.arun()` | Rename |
| `bae/cli.py` | `asyncio.run(graph.run(...))` -> `graph.run(...)` | Simplification |

### Files that DON'T change

| File | Reason |
|------|--------|
| `bae/markers.py` | `Dep` and `Recall` dataclasses unchanged |
| `bae/exceptions.py` | `DepError` already has correct fields |
| `bae/node.py` | `Node.__call__` already async from Phase 11 |
| `bae/lm.py` | LM protocol already async from Phase 11 |
| `bae/dspy_backend.py` | Already async from Phase 11 |
| `tests/test_compiler.py` | Pure sync functions |
| `tests/test_exceptions.py` | Pure sync construction |
| `tests/test_optimizer.py` | Pure sync functions |

### New test areas needed

| Test Area | What to Verify |
|-----------|---------------|
| Gather behavior | Independent deps on same node actually fire concurrently (timing test or mock verification) |
| Sync/async dep mixing | Node with both sync and async dep callables resolves correctly |
| Concurrent caching | Per-run dep cache correct under gather (topo ordering prevents races) |
| Fail-fast cancellation | First dep failure stops remaining deps, propagates DepError |
| DepError wrapping | Exception includes node_type, field_name (when available), cause chain |
| Topo ordering preserved | Transitive deps always resolve before dependents |
| run() vs arun() | run() works from sync context, arun() works from async context |

## Open Questions

1. **resolve_dep Public API Preservation**
   - What we know: `resolve_dep` is imported in tests and exported from `bae.resolver`. Phase 12 changes its semantics from "recursive resolver" to "single-callable resolver that expects transitive deps already in cache."
   - What's unclear: Should `resolve_dep` remain as a public async function for direct testing, or should it become private (`_resolve_one`) with tests going through `resolve_fields`?
   - Recommendation: Keep `resolve_dep` as public `async def resolve_dep(fn, cache)` -- but reimplement internally to use topo-sort. This preserves the test API. Internally it builds a mini-DAG for just that callable and resolves level-by-level. Tests that call `resolve_dep` directly continue to work. Alternatively, add `_resolve_one` as the internal per-callable resolver and keep `resolve_dep` as a higher-level function that builds a DAG and gathers.

2. **Recall Resolution: Sync or Gathered?**
   - What we know: `recall_from_trace` is pure computation (walks a list). The decision says "recalls resolved concurrently with dep fields."
   - What's unclear: Whether to `asyncio.gather` recalls alongside deps or just call them synchronously after dep resolution.
   - Recommendation: Call recalls synchronously after deps. They're pure computation -- no I/O benefit from gathering them. "Concurrently with dep fields" likely means "in the same `resolve_fields` call, not in a separate step" rather than "in the same `asyncio.gather()`." Putting zero-cost sync computation into gather adds complexity without benefit.

3. **Declaration Order in Resolved Dict**
   - What we know: The current `resolve_fields` returns results in declaration order (iterates `get_type_hints` which preserves class definition order). The topo-sort approach resolves deps by topo level, not declaration order.
   - What's unclear: Whether any code depends on the ordering of keys in the returned dict.
   - Recommendation: After all deps and recalls are resolved (into `dep_cache` and inline), build the result dict by iterating `hints` in declaration order, looking up results from cache. This preserves declaration ordering. One test (`test_resolve_fields_declaration_order`) explicitly checks this.

## Sources

### Primary (HIGH confidence)
- **Python 3.14.2 stdlib** - `graphlib.TopologicalSorter`, `asyncio.gather()`, `inspect.iscoroutinefunction()` -- all verified by running on bae's Python 3.14.2 venv
- **bae codebase** - `resolver.py`, `graph.py`, `exceptions.py`, `markers.py`, `examples/ootd.py` -- read and analyzed
- **bae test suite** - `test_resolver.py`, `test_dep_injection.py`, `test_graph.py`, `test_ootd_e2e.py` -- read for migration impact
- **Phase 11 research** - `.planning/phases/11-async-core/11-RESEARCH.md` -- prior decisions and patterns

### Secondary (MEDIUM confidence)
- None. All findings verified against installed source and runtime behavior.

### Tertiary (LOW confidence)
- None. All findings verified.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All stdlib, all verified on actual Python 3.14.2
- Architecture: HIGH - Core pattern (topo-sort + gather) verified with real OOTD dep DAG
- Pitfalls: HIGH - Each pitfall verified by running actual code in bae venv
- Migration impact: HIGH - All affected files identified by grepping codebase

**Research date:** 2026-02-08
**Valid until:** 2026-03-08 (stable: stdlib APIs, pinned library versions)
