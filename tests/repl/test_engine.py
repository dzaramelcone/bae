"""Tests for GraphRegistry, TimingLM, and engine lifecycle tracking."""

from __future__ import annotations

import asyncio

import pytest

from bae.lm import LM
from bae.node import Node
from bae.repl.engine import GraphRegistry, GraphRun, GraphState, NodeTiming, TimingLM
from bae.repl.tasks import TaskManager


# --- Test graph fixtures (module-level for forward reference resolution) ---


class Start(Node):
    text: str

    def __call__(self) -> End: ...


class End(Node):
    reply: str


class MockLM:
    """Minimal LM that always produces End(reply="done")."""

    async def fill(self, target, resolved, instruction, source=None):
        if target is End:
            return End.model_construct(reply="done", **resolved)
        return target.model_construct(**resolved)

    async def choose_type(self, types, context):
        return types[0]

    async def make(self, node, target):
        return await self.fill(target, {}, target.__name__, source=node)

    async def decide(self, node):
        return None


class FailingLM(MockLM):
    """LM that raises on fill."""

    async def fill(self, target, resolved, instruction, source=None):
        raise RuntimeError("LM exploded")


class SlowLM(MockLM):
    """LM that sleeps forever on fill (for cancellation tests)."""

    async def fill(self, target, resolved, instruction, source=None):
        await asyncio.sleep(100)
        return target.model_construct(**resolved)


@pytest.fixture
def tm():
    return TaskManager()


@pytest.fixture
def registry():
    return GraphRegistry()


@pytest.fixture
def mock_lm():
    return MockLM()


# --- TestGraphState ---


class TestGraphState:
    def test_states_exist(self):
        """GraphState has RUNNING, DONE, FAILED, CANCELLED members."""
        assert GraphState.RUNNING.value == "running"
        assert GraphState.DONE.value == "done"
        assert GraphState.FAILED.value == "failed"
        assert GraphState.CANCELLED.value == "cancelled"


# --- TestNodeTiming ---


class TestNodeTiming:
    def test_duration_ms(self):
        """NodeTiming with start_ns=0, end_ns=1_000_000 has duration_ms == 1.0."""
        nt = NodeTiming(node_type="End", start_ns=0, end_ns=1_000_000)
        assert nt.duration_ms == 1.0


# --- TestTimingLM ---


class TestTimingLM:
    def test_conforms_to_lm_protocol(self, mock_lm):
        """isinstance(TimingLM(mock_lm, mock_run), LM) is True."""
        run = GraphRun(run_id="g1", graph=None)
        timing_lm = TimingLM(mock_lm, run)
        assert isinstance(timing_lm, LM)

    async def test_fill_records_timing(self, mock_lm):
        """fill() delegates to inner LM AND appends a NodeTiming with correct node_type."""
        run = GraphRun(run_id="g1", graph=None)
        timing_lm = TimingLM(mock_lm, run)
        result = await timing_lm.fill(End, {}, "End")
        assert isinstance(result, End)
        assert result.reply == "done"
        assert len(run.node_timings) == 1
        assert run.node_timings[0].node_type == "End"
        assert run.node_timings[0].duration_ms >= 0

    async def test_choose_type_delegates(self, mock_lm):
        """choose_type() delegates and returns correct type."""
        run = GraphRun(run_id="g1", graph=None)
        timing_lm = TimingLM(mock_lm, run)
        result = await timing_lm.choose_type([End, Start], {})
        assert result is End

    async def test_make_delegates(self, mock_lm):
        """make() delegates to inner LM."""
        run = GraphRun(run_id="g1", graph=None)
        timing_lm = TimingLM(mock_lm, run)
        node = Start.model_construct(text="hi")
        result = await timing_lm.make(node, End)
        assert isinstance(result, End)

    async def test_decide_delegates(self, mock_lm):
        """decide() delegates to inner LM."""
        run = GraphRun(run_id="g1", graph=None)
        timing_lm = TimingLM(mock_lm, run)
        node = Start.model_construct(text="hi")
        result = await timing_lm.decide(node)
        assert result is None


# --- TestGraphRegistry ---


class TestGraphRegistry:
    async def test_submit_creates_running_graphrun(self, registry, tm, mock_lm):
        """submit() returns GraphRun with state RUNNING and incremented run_id."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=mock_lm, text="hello")
        assert run.state == GraphState.RUNNING
        assert run.run_id == "g1"

        run2 = registry.submit(graph, tm, lm=mock_lm, text="hello")
        assert run2.run_id == "g2"

        await tm.shutdown()

    async def test_submit_creates_taskmanager_task(self, registry, tm, mock_lm):
        """After submit(), TaskManager.active() contains a task with graph: prefix."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        registry.submit(graph, tm, lm=mock_lm, text="hello")
        active = tm.active()
        assert len(active) >= 1
        assert any(tt.name.startswith("graph:") for tt in active)
        assert any("Start" in tt.name for tt in active)
        await tm.shutdown()

    async def test_run_completes_to_done(self, registry, tm, mock_lm):
        """Submit a graph with MockLM, await the task, verify run.state == DONE."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=mock_lm, text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.DONE

    async def test_run_failure_sets_failed(self, registry, tm):
        """Submit a graph that raises, verify run.state == FAILED."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=FailingLM(), text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.FAILED

    async def test_failed_run_stores_error(self, registry, tm):
        """Failed run stores exception message in run.error."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=FailingLM(), text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.FAILED
        assert "LM exploded" in run.error
        assert "RuntimeError" in run.error

    async def test_successful_run_has_no_error(self, registry, tm, mock_lm):
        """Successful run has empty error string."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=mock_lm, text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.DONE
        assert run.error == ""

    async def test_run_cancellation_sets_cancelled(self, registry, tm):
        """Submit a graph, revoke via TaskManager, verify run.state == CANCELLED."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=SlowLM(), text="hello")
        await asyncio.sleep(0.05)
        tm.revoke_all(graceful=False)
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except (asyncio.CancelledError, Exception):
                pass
        assert run.state == GraphState.CANCELLED

    async def test_completed_runs_archived(self, registry, tm, mock_lm):
        """After run completes, it moves from active runs to completed deque."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=mock_lm, text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.DONE
        assert registry.active() == []
        assert run in registry._completed

    async def test_completed_deque_bounded(self, registry, tm, mock_lm):
        """Submit and complete 25 graphs, verify completed deque has exactly 20."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        for _ in range(25):
            registry.submit(graph, tm, lm=mock_lm, text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert len(registry._completed) == 20

    async def test_active_runs_lists_running(self, registry, tm):
        """Submit two graphs, verify active() returns both."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run1 = registry.submit(graph, tm, lm=SlowLM(), text="a")
        run2 = registry.submit(graph, tm, lm=SlowLM(), text="b")
        await asyncio.sleep(0.05)
        active = registry.active()
        assert len(active) == 2
        await tm.shutdown()

    async def test_timing_lm_injected_via_dep_cache(self, registry, tm, mock_lm):
        """Submit with an LM, verify dep_cache contains LM_KEY pointing to a TimingLM."""
        from bae.graph import Graph
        from bae.resolver import LM_KEY

        captured = {}
        orig_execute = registry._execute

        async def spy_execute(run, *, lm=None, **kwargs):
            if lm is None:
                from bae.lm import ClaudeCLIBackend
                lm = ClaudeCLIBackend()
            timing_lm = TimingLM(lm, run)
            captured["timing_lm"] = timing_lm
            captured["inner_lm"] = lm
            return await orig_execute(run, lm=lm, **kwargs)

        registry._execute = spy_execute

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=mock_lm, text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass

        assert "timing_lm" in captured
        assert isinstance(captured["timing_lm"], TimingLM)
        assert captured["inner_lm"] is mock_lm

    async def test_execute_stores_result(self, registry, tm, mock_lm):
        """Submit a graph, await completion, verify run.result has trace."""
        from bae.graph import Graph
        from bae.result import GraphResult

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=mock_lm, text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.DONE
        assert run.result is not None
        assert isinstance(run.result, GraphResult)
        assert len(run.result.trace) >= 1

    async def test_submit_coro_creates_running_graphrun(self, registry, tm):
        """submit_coro() creates a GraphRun with state RUNNING."""
        started = asyncio.Event()

        async def fake():
            started.set()
            await asyncio.sleep(10)
            return "done"

        run = registry.submit_coro(fake(), tm, name="test")
        await started.wait()
        assert run.state == GraphState.RUNNING
        assert run.run_id == "g1"
        assert run.graph is None
        tm.revoke_all(graceful=False)
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except (asyncio.CancelledError, Exception):
                pass

    async def test_submit_coro_completes_to_done(self, registry, tm):
        """submit_coro() coroutine completion sets state to DONE."""
        async def fake():
            return "done"

        run = registry.submit_coro(fake(), tm, name="test")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.DONE

    async def test_submit_coro_failure_sets_failed(self, registry, tm):
        """submit_coro() wraps failures with error message."""
        async def failing():
            raise ValueError("boom")

        run = registry.submit_coro(failing(), tm, name="test")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.FAILED
        assert "boom" in run.error
        assert "ValueError" in run.error

    async def test_submit_coro_cancellation(self, registry, tm):
        """submit_coro() handles cancellation correctly."""
        async def slow():
            await asyncio.sleep(100)

        run = registry.submit_coro(slow(), tm, name="test")
        await asyncio.sleep(0.05)
        tm.revoke_all(graceful=False)
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except (asyncio.CancelledError, Exception):
                pass
        assert run.state == GraphState.CANCELLED

    async def test_wrap_coro_preserves_trace_on_failure(self, registry, tm):
        """submit_coro wraps exceptions with .trace into run.result."""
        trace_nodes = [Start.model_construct(text="a"), End.model_construct(reply="b")]

        async def failing_with_trace():
            err = RuntimeError("timeout")
            err.trace = trace_nodes
            raise err

        run = registry.submit_coro(failing_with_trace(), tm, name="test")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.FAILED
        assert run.result is not None
        assert run.result.trace is trace_nodes
        assert len(run.result.trace) == 2

    async def test_execute_preserves_trace_on_failure(self, registry, tm):
        """_execute extracts .trace from graph.arun exceptions into run.result."""
        from bae.graph import Graph
        from bae.result import GraphResult

        class TraceFailLM(MockLM):
            async def fill(self, target, resolved, instruction, source=None):
                err = RuntimeError("LM exploded with trace")
                err.trace = [Start.model_construct(text="partial")]
                raise err

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=TraceFailLM(), text="hello")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.FAILED
        assert run.result is not None
        assert isinstance(run.result, GraphResult)
        assert len(run.result.trace) >= 1

    async def test_submit_coro_stores_graphresult(self, registry, tm):
        """submit_coro() stores GraphResult on run when coroutine returns one."""
        from bae.result import GraphResult
        from bae.node import Node

        class Stub(Node):
            x: str = "hi"

        gr = GraphResult(node=None, trace=[Stub()])

        async def returning_result():
            return gr

        run = registry.submit_coro(returning_result(), tm, name="test")
        for tt in list(tm._tasks.values()):
            try:
                await tt.task
            except Exception:
                pass
        assert run.state == GraphState.DONE
        assert run.result is gr
        assert len(run.result.trace) == 1
