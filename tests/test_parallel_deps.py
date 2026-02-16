"""Tests for Phase 12 parallel dep resolution behavior.

Covers: concurrent gather, sync/async mixing, topo ordering, per-run caching,
fail-fast cancellation, DepError wrapping, and run/arun API split.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Annotated

import pytest

from bae import Graph
from bae.exceptions import DepError
from bae.markers import Dep, Recall
from bae.node import Node
from bae.resolver import resolve_dep, resolve_fields


# ---------------------------------------------------------------------------
# Dep callables for test fixtures
# ---------------------------------------------------------------------------

# -- Async deps --

async def async_get_location() -> str:
    return "NYC"


async def async_get_temperature() -> int:
    return 72


# -- Sync deps --

def sync_get_location() -> str:
    return "NYC"


def sync_get_temperature() -> int:
    return 72


# -- Slow async deps (for concurrency verification) --

async def slow_dep_a() -> str:
    await asyncio.sleep(0.1)
    return "a"


async def slow_dep_b() -> str:
    await asyncio.sleep(0.1)
    return "b"


# -- Execution-order tracking deps --

execution_order: list[str] = []


async def order_dep_a() -> str:
    execution_order.append("a_start")
    await asyncio.sleep(0)
    execution_order.append("a_end")
    return "a"


async def order_dep_b() -> str:
    execution_order.append("b_start")
    await asyncio.sleep(0)
    execution_order.append("b_end")
    return "b"


# -- Transitive deps (topo ordering) --

async def async_base() -> str:
    return "base"


async def async_derived(base: Annotated[str, Dep(async_base)]) -> str:
    return f"derived({base})"


# Three-level async chain for deep topo ordering test

async def level_a() -> str:
    return "a"


async def level_b(a: Annotated[str, Dep(level_a)]) -> str:
    return f"b({a})"


async def level_c(b: Annotated[str, Dep(level_b)]) -> str:
    return f"c({b})"


# -- Tracked call-count deps --

call_count: dict[str, int] = {}


async def counted_dep() -> str:
    call_count["counted_dep"] = call_count.get("counted_dep", 0) + 1
    return "counted"


# -- Failing deps --

def failing_dep() -> str:
    raise ConnectionError("boom")


async def slow_never_finishes() -> str:
    await asyncio.sleep(10)
    return "never"


# ---------------------------------------------------------------------------
# 1. Concurrent gather verification
# ---------------------------------------------------------------------------


class TestConcurrentGather:
    async def test_independent_deps_resolve_concurrently_by_timing(self):
        """Two independent async deps each sleeping 0.1s complete in ~0.1s total, not ~0.2s."""

        class ConcurrentNode(Node):
            a: Annotated[str, Dep(slow_dep_a)]
            b: Annotated[str, Dep(slow_dep_b)]

        start = time.monotonic()
        result = await resolve_fields(ConcurrentNode, trace=[], dep_cache={})
        elapsed = time.monotonic() - start

        assert result["a"] == "a"
        assert result["b"] == "b"
        # If sequential, would take ~0.2s. Concurrent should be ~0.1s.
        assert elapsed < 0.18, f"Took {elapsed:.3f}s -- deps may not be concurrent"

    async def test_independent_deps_interleave_execution(self):
        """Two async deps with sleep(0) interleave: both start before either ends."""
        execution_order.clear()

        class InterleavedNode(Node):
            a: Annotated[str, Dep(order_dep_a)]
            b: Annotated[str, Dep(order_dep_b)]

        await resolve_fields(InterleavedNode, trace=[], dep_cache={})

        # Both should start before either ends (interleaved)
        starts = [i for i, x in enumerate(execution_order) if x.endswith("_start")]
        ends = [i for i, x in enumerate(execution_order) if x.endswith("_end")]
        # At least one start should occur before the other's end
        assert len(starts) == 2
        assert len(ends) == 2
        # The second start should come before the first end in concurrent execution
        assert starts[1] < ends[0], (
            f"Expected interleaving, got: {execution_order}"
        )


# ---------------------------------------------------------------------------
# 2. Sync/async dep mixing
# ---------------------------------------------------------------------------


class TestSyncAsyncMixing:
    async def test_mixed_sync_and_async_deps_resolve(self):
        """Node with one sync dep and one async dep -- both resolve correctly."""

        class MixedNode(Node):
            location: Annotated[str, Dep(sync_get_location)]
            temperature: Annotated[int, Dep(async_get_temperature)]

        result = await resolve_fields(MixedNode, trace=[], dep_cache={})
        assert result["location"] == "NYC"
        assert result["temperature"] == 72

    async def test_async_dep_in_resolve_dep(self):
        """resolve_dep works with an async callable."""
        cache: dict = {}
        result = await resolve_dep(async_get_location, cache)
        assert result == "NYC"
        assert async_get_location in cache

    async def test_sync_dep_in_resolve_dep(self):
        """resolve_dep works with a sync callable."""
        cache: dict = {}
        result = await resolve_dep(sync_get_location, cache)
        assert result == "NYC"
        assert sync_get_location in cache


# ---------------------------------------------------------------------------
# 3. Async dep callable detection
# ---------------------------------------------------------------------------


class TestAsyncDetection:
    def test_async_dep_detected_as_coroutine(self):
        """async def dep is detected by inspect.iscoroutinefunction."""
        assert inspect.iscoroutinefunction(async_get_location)

    def test_sync_dep_detected_as_non_coroutine(self):
        """def dep is not detected as coroutine function."""
        assert not inspect.iscoroutinefunction(sync_get_location)

    async def test_both_dispatch_correctly_through_resolve_fields(self):
        """Sync and async deps both resolve through resolve_fields."""

        class DetectionNode(Node):
            sync_val: Annotated[str, Dep(sync_get_location)]
            async_val: Annotated[str, Dep(async_get_location)]

        result = await resolve_fields(DetectionNode, trace=[], dep_cache={})
        assert result["sync_val"] == "NYC"
        assert result["async_val"] == "NYC"


# ---------------------------------------------------------------------------
# 4. Topo ordering under concurrency
# ---------------------------------------------------------------------------


class TestTopoOrdering:
    async def test_transitive_dep_resolves_before_dependent(self):
        """async_derived depends on async_base -- base resolves first."""

        class TopoNode(Node):
            derived: Annotated[str, Dep(async_derived)]

        cache: dict = {}
        result = await resolve_fields(TopoNode, trace=[], dep_cache=cache)

        assert result["derived"] == "derived(base)"
        # Both should be cached
        assert async_base in cache
        assert async_derived in cache
        # Base resolved before derived (it's in cache when derived runs)
        assert cache[async_base] == "base"

    async def test_deep_transitive_chain(self):
        """Three-level async chain: C -> B -> A, all resolve correctly."""

        class DeepTopoNode(Node):
            result: Annotated[str, Dep(level_c)]

        cache: dict = {}
        resolved = await resolve_fields(DeepTopoNode, trace=[], dep_cache=cache)
        assert resolved["result"] == "c(b(a))"
        assert cache[level_a] == "a"
        assert cache[level_b] == "b(a)"
        assert cache[level_c] == "c(b(a))"


# ---------------------------------------------------------------------------
# 5. Per-run cache correctness
# ---------------------------------------------------------------------------


class TestCacheCorrectness:
    async def test_shared_cache_prevents_duplicate_calls(self):
        """Shared dep_cache across two resolve_fields calls -- dep called once."""
        call_count.clear()

        class CacheNodeA(Node):
            val: Annotated[str, Dep(counted_dep)]

        class CacheNodeB(Node):
            val: Annotated[str, Dep(counted_dep)]

        shared_cache: dict = {}
        await resolve_fields(CacheNodeA, trace=[], dep_cache=shared_cache)
        await resolve_fields(CacheNodeB, trace=[], dep_cache=shared_cache)

        assert call_count["counted_dep"] == 1

    async def test_cache_hit_returns_same_value(self):
        """Cached value is the exact same object on second resolution."""
        call_count.clear()

        class CacheHitNode(Node):
            val: Annotated[str, Dep(counted_dep)]

        shared_cache: dict = {}
        r1 = await resolve_fields(CacheHitNode, trace=[], dep_cache=shared_cache)
        r2 = await resolve_fields(CacheHitNode, trace=[], dep_cache=shared_cache)

        assert r1["val"] is r2["val"]
        assert call_count["counted_dep"] == 1

    async def test_resolve_dep_cache_hit(self):
        """resolve_dep returns cached value without calling fn again."""
        call_count.clear()

        cache: dict = {}
        r1 = await resolve_dep(counted_dep, cache)
        r2 = await resolve_dep(counted_dep, cache)

        assert r1 == r2
        assert call_count["counted_dep"] == 1


# ---------------------------------------------------------------------------
# 6. Fail-fast cancellation
# ---------------------------------------------------------------------------


class TestFailFast:
    async def test_first_exception_propagates_raw(self):
        """Dep failure propagates as the original exception, not ExceptionGroup."""

        class FailNode(Node):
            bad: Annotated[str, Dep(failing_dep)]

        with pytest.raises(ConnectionError, match="boom"):
            await resolve_fields(FailNode, trace=[], dep_cache={})

    async def test_exception_not_wrapped_in_exception_group(self):
        """Even with multiple deps, failure is raw -- not ExceptionGroup."""

        class MultiFailNode(Node):
            bad: Annotated[str, Dep(failing_dep)]
            good: Annotated[str, Dep(sync_get_location)]

        with pytest.raises(ConnectionError):
            await resolve_fields(MultiFailNode, trace=[], dep_cache={})

    async def test_resolve_dep_exception_propagates_raw(self):
        """resolve_dep propagates exceptions without wrapping."""
        with pytest.raises(ConnectionError, match="boom"):
            await resolve_dep(failing_dep, {})


# ---------------------------------------------------------------------------
# 7. DepError wrapping (via graph.arun)
# ---------------------------------------------------------------------------


class FailingDepNode(Node):
    """Node with a dep that raises."""
    bad: Annotated[str, Dep(failing_dep)]
    async def __call__(self) -> None: ...


class TestDepErrorWrapping:
    async def test_graph_arun_wraps_dep_failure_in_dep_error(self):
        """graph.arun raises DepError when a dep fails."""
        graph = Graph(start=FailingDepNode)
        with pytest.raises(DepError) as exc_info:
            await graph.arun()

        err = exc_info.value
        assert err.node_type is FailingDepNode
        assert isinstance(err.__cause__, ConnectionError)

    async def test_dep_error_preserves_cause_chain(self):
        """DepError.__cause__ is the original ConnectionError."""
        graph = Graph(start=FailingDepNode)
        with pytest.raises(DepError) as exc_info:
            await graph.arun()

        err = exc_info.value
        assert err.__cause__ is not None
        assert "boom" in str(err.__cause__)


# ---------------------------------------------------------------------------
# 8. run() vs arun() API
# ---------------------------------------------------------------------------


class SimpleNode(Node):
    """Minimal terminal node for API tests."""
    value: str
    async def __call__(self) -> None: ...


class TestRunArunAPI:
    async def test_arun_works_from_async_context(self):
        """graph.arun() called with await in async test."""
        graph = Graph(start=SimpleNode)
        result = await graph.arun(value="hello")
        assert len(result.trace) == 1
        assert result.trace[0].value == "hello"

    def test_run_works_from_sync_context(self):
        """graph.run() called without await from sync test."""
        graph = Graph(start=SimpleNode)
        result = graph.run(value="hello")
        assert len(result.trace) == 1
        assert result.trace[0].value == "hello"

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_run_from_running_event_loop_raises(self):
        """graph.run() from inside a running event loop raises RuntimeError.

        asyncio.run() cannot be called from within an existing event loop.
        The unawaited coroutine warning is expected and suppressed.
        """
        graph = Graph(start=SimpleNode)
        with pytest.raises(RuntimeError):
            graph.run(value="hello")
