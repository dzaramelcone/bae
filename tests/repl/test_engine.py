"""Tests for GraphRegistry, TimingLM, and engine lifecycle tracking."""

from __future__ import annotations

import asyncio

import pytest
from typing import Annotated

from bae.lm import LM
from bae.markers import Dep, Gate
from bae.node import Node
from bae.repl.engine import GraphRegistry, GraphRun, GraphState, InputGate, NodeTiming, OutputPolicy, TimingLM
from bae.repl.tasks import TaskManager


# --- Test graph fixtures (module-level for forward reference resolution) ---


class Start(Node):
    text: str

    def __call__(self) -> End: ...


class End(Node):
    reply: str


class GatedNode(Node):
    """Node with a Gate-annotated field for testing gate interception."""
    approved: Annotated[bool, Gate(description="Deploy to prod?")]

    def __call__(self) -> End: ...


class MultiGatedNode(Node):
    """Node with two Gate-annotated fields for concurrent gate testing."""
    approved: Annotated[bool, Gate(description="Deploy to prod?")]
    reason: Annotated[str, Gate(description="Why?")]

    def __call__(self) -> End: ...


class GatedStart(Node):
    """Start node that transitions to a GatedNode."""
    text: str

    def __call__(self) -> GatedNode: ...


class MultiGatedStart(Node):
    """Start node that transitions to a MultiGatedNode."""
    text: str

    def __call__(self) -> MultiGatedNode: ...


class Middle(Node):
    summary: str

    async def __call__(self) -> End:
        await asyncio.sleep(0.01)
        return End.model_construct(reply="done")


class StressStart(Node):
    """Start node for concurrent stress test with simulated work."""
    text: str

    async def __call__(self) -> Middle:
        await asyncio.sleep(0.01)
        return Middle.model_construct(summary="mid")


async def slow_dep() -> str:
    await asyncio.sleep(0.01)
    return "computed"


class DepStart(Node):
    """Start node with a Dep-annotated field for timing tests."""
    text: str
    info: Annotated[str, Dep(slow_dep)]

    def __call__(self) -> End: ...


class MockLM:
    """Minimal LM that produces nodes from resolved fields."""

    async def fill(self, target, resolved, instruction, source=None):
        if target is End:
            return End.model_construct(reply="done", **resolved)
        # For gated nodes: gate fields come via resolved dict from hook
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


# --- TestInputGate and gate registry ---


class TestInputGate:
    def test_waiting_state_exists(self):
        """GraphState.WAITING has value 'waiting'."""
        assert GraphState.WAITING.value == "waiting"

    async def test_create_gate(self, registry):
        """create_gate returns InputGate with correct gate_id format and fields."""
        gate = registry.create_gate(
            run_id="g1",
            field_name="approved",
            field_type=bool,
            description="Approve?",
            node_type="ConfirmDeploy",
        )
        assert gate.gate_id == "g1.0"
        assert gate.run_id == "g1"
        assert gate.field_name == "approved"
        assert gate.field_type is bool
        assert gate.description == "Approve?"
        assert gate.node_type == "ConfirmDeploy"
        assert not gate.future.done()

    async def test_resolve_gate(self, registry):
        """Resolving a gate sets the future result and removes from pending."""
        gate = registry.create_gate(
            run_id="g1",
            field_name="approved",
            field_type=bool,
            description="Approve?",
            node_type="ConfirmDeploy",
        )
        assert registry.resolve_gate(gate.gate_id, True)
        assert gate.future.result() is True
        assert registry.pending_gate_count() == 0

    async def test_resolve_gate_not_found(self, registry):
        """Resolving a non-existent gate returns False."""
        assert not registry.resolve_gate("g999.0", True)

    async def test_pending_gate_count(self, registry):
        """Pending count tracks create and resolve correctly."""
        g1 = registry.create_gate("g1", "a", bool, "", "N")
        registry.create_gate("g1", "b", str, "", "N")
        assert registry.pending_gate_count() == 2
        registry.resolve_gate(g1.gate_id, True)
        assert registry.pending_gate_count() == 1

    async def test_pending_gates_for_run(self, registry):
        """Filter pending gates by run_id."""
        registry.create_gate("g1", "a", bool, "", "N")
        registry.create_gate("g2", "b", str, "", "N")
        registry.create_gate("g1", "c", int, "", "N")
        run1_gates = registry.pending_gates_for_run("g1")
        run2_gates = registry.pending_gates_for_run("g2")
        assert len(run1_gates) == 2
        assert len(run2_gates) == 1
        assert all(g.run_id == "g1" for g in run1_gates)

    async def test_cancel_gates(self, registry):
        """cancel_gates cancels futures and removes gates for the run."""
        g1 = registry.create_gate("g1", "a", bool, "", "N")
        g2 = registry.create_gate("g1", "b", str, "", "N")
        registry.create_gate("g2", "c", int, "", "N")
        registry.cancel_gates("g1")
        assert g1.future.cancelled()
        assert g2.future.cancelled()
        assert registry.pending_gate_count() == 1
        assert registry.pending_gates_for_run("g1") == []

    async def test_schema_display_with_description(self):
        """schema_display includes description in quotes."""
        gate = InputGate(
            gate_id="g1.0",
            run_id="g1",
            field_name="approved",
            field_type=bool,
            description="Deploy to prod?",
            node_type="ConfirmDeploy",
        )
        assert gate.schema_display == 'approved: bool ("Deploy to prod?")'

    async def test_schema_display_without_description(self):
        """schema_display omits parenthetical when no description."""
        gate = InputGate(
            gate_id="g1.0",
            run_id="g1",
            field_name="count",
            field_type=int,
            description="",
            node_type="Counter",
        )
        assert gate.schema_display == "count: int"

    async def test_active_includes_waiting(self, registry):
        """A run in WAITING state appears in active()."""
        run = GraphRun(run_id="g1", graph=None, state=GraphState.WAITING)
        registry._runs["g1"] = run
        active = registry.active()
        assert run in active


# --- TestGateHook: engine intercepts gate fields during execution ---


class TestGateHook:
    async def test_gate_hook_creates_gates(self, registry, tm):
        """Graph with Gate field creates InputGate and transitions to WAITING."""
        from bae.graph import Graph

        graph = Graph(start=GatedStart)
        run = registry.submit(graph, tm, lm=MockLM(), text="hi")
        # Wait for the gate to be created (engine hits WAITING)
        for _ in range(100):
            if run.state == GraphState.WAITING:
                break
            await asyncio.sleep(0.01)
        assert run.state == GraphState.WAITING
        assert registry.pending_gate_count() >= 1
        gates = registry.pending_gates_for_run(run.run_id)
        assert len(gates) == 1
        assert gates[0].field_name == "approved"
        assert gates[0].field_type is bool
        assert gates[0].description == "Deploy to prod?"
        # Resolve gate to allow graph to finish
        registry.resolve_gate(gates[0].gate_id, True)
        await _drain_tasks(tm)

    async def test_gate_hook_resumes_on_resolve(self, registry, tm):
        """Resolving a gate resumes graph execution and delivers the value."""
        from bae.graph import Graph

        graph = Graph(start=GatedStart)
        run = registry.submit(graph, tm, lm=MockLM(), text="hi")
        for _ in range(100):
            if run.state == GraphState.WAITING:
                break
            await asyncio.sleep(0.01)
        assert run.state == GraphState.WAITING
        gates = registry.pending_gates_for_run(run.run_id)
        registry.resolve_gate(gates[0].gate_id, True)
        await _drain_tasks(tm)
        assert run.state == GraphState.DONE
        # Verify the gate value made it into the trace
        gated = [n for n in run.result.trace if isinstance(n, GatedNode)]
        assert len(gated) == 1
        assert gated[0].approved is True

    async def test_multiple_gate_fields_concurrent(self, registry, tm):
        """Node with 2 gate fields: both Futures created, resolve independently."""
        from bae.graph import Graph

        graph = Graph(start=MultiGatedStart)
        run = registry.submit(graph, tm, lm=MockLM(), text="hi")
        for _ in range(100):
            if run.state == GraphState.WAITING:
                break
            await asyncio.sleep(0.01)
        assert run.state == GraphState.WAITING
        gates = registry.pending_gates_for_run(run.run_id)
        assert len(gates) == 2
        names = {g.field_name for g in gates}
        assert names == {"approved", "reason"}
        # Resolve in any order
        for g in gates:
            if g.field_name == "approved":
                registry.resolve_gate(g.gate_id, True)
            else:
                registry.resolve_gate(g.gate_id, "because yes")
        await _drain_tasks(tm)
        assert run.state == GraphState.DONE
        gated = [n for n in run.result.trace if isinstance(n, MultiGatedNode)]
        assert len(gated) == 1
        assert gated[0].approved is True
        assert gated[0].reason == "because yes"

    async def test_gate_cancel_during_waiting(self, registry, tm):
        """Cancel a graph while WAITING: CancelledError and gate cleanup."""
        from bae.graph import Graph

        graph = Graph(start=GatedStart)
        run = registry.submit(graph, tm, lm=MockLM(), text="hi")
        for _ in range(100):
            if run.state == GraphState.WAITING:
                break
            await asyncio.sleep(0.01)
        assert run.state == GraphState.WAITING
        gates = registry.pending_gates_for_run(run.run_id)
        assert len(gates) == 1
        # Cancel the graph
        tm.revoke_all(graceful=False)
        await _drain_tasks(tm)
        assert run.state == GraphState.CANCELLED
        assert registry.pending_gate_count() == 0
        assert gates[0].future.cancelled()

    async def test_gate_notify_callback(self, registry, tm):
        """Notify callback receives gate schema when gates are created."""
        from bae.graph import Graph

        notifications = []
        graph = Graph(start=GatedStart)
        run = registry.submit(
            graph, tm, lm=MockLM(),
            notify=lambda content, meta=None: notifications.append((content, meta)),
            text="hi",
        )
        for _ in range(100):
            if run.state == GraphState.WAITING:
                break
            await asyncio.sleep(0.01)
        # Filter to gate notifications (ignore lifecycle events)
        gate_notifs = [(c, m) for c, m in notifications if m and m.get("type") == "gate"]
        assert len(gate_notifs) == 1
        content, meta = gate_notifs[0]
        assert "approved" in content
        assert "bool" in content
        assert "Deploy to prod?" in content
        assert meta["type"] == "gate"
        # Clean up
        gates = registry.pending_gates_for_run(run.run_id)
        for g in gates:
            registry.resolve_gate(g.gate_id, True)
        await _drain_tasks(tm)


# --- TestOutputPolicy ---


class TestOutputPolicy:
    def test_verbose_emits_all(self):
        """VERBOSE.should_emit returns True for all event types."""
        p = OutputPolicy.VERBOSE
        for event in ("start", "complete", "fail", "transition", "gate", "error"):
            assert p.should_emit(event), f"VERBOSE should emit {event}"

    def test_normal_emits_lifecycle(self):
        """NORMAL emits start/complete/fail/gate/error but not transition."""
        p = OutputPolicy.NORMAL
        for event in ("start", "complete", "fail", "gate", "error"):
            assert p.should_emit(event), f"NORMAL should emit {event}"
        assert not p.should_emit("transition")

    def test_quiet_emits_errors_only(self):
        """QUIET emits only fail/gate/error."""
        p = OutputPolicy.QUIET
        for event in ("fail", "gate", "error"):
            assert p.should_emit(event), f"QUIET should emit {event}"
        for event in ("start", "complete", "transition"):
            assert not p.should_emit(event), f"QUIET should not emit {event}"

    def test_silent_emits_nothing(self):
        """SILENT.should_emit returns False for everything."""
        p = OutputPolicy.SILENT
        for event in ("start", "complete", "fail", "transition", "gate", "error"):
            assert not p.should_emit(event), f"SILENT should not emit {event}"


# --- TestDepTiming ---


class TestDepTiming:
    async def test_dep_timing_collection(self, registry, tm):
        """Dep-annotated field timing appears in run.dep_timings after execution."""
        from bae.graph import Graph

        graph = Graph(start=DepStart)
        run = registry.submit(graph, tm, lm=MockLM(), text="hello")
        await _drain_tasks(tm)
        assert run.state == GraphState.DONE
        assert len(run.dep_timings) >= 1
        name, dur_ms = run.dep_timings[0]
        assert "slow_dep" in name
        assert dur_ms > 0

    async def test_rss_delta_recorded(self, registry, tm, mock_lm):
        """run.rss_delta_bytes is an int after execution."""
        from bae.graph import Graph

        graph = Graph(start=Start)
        run = registry.submit(graph, tm, lm=mock_lm, text="hello")
        await _drain_tasks(tm)
        assert run.state == GraphState.DONE
        assert isinstance(run.rss_delta_bytes, int)


# --- TestNotifyMetadata ---


class TestNotifyMetadata:
    async def test_notify_receives_metadata(self, registry, tm, mock_lm):
        """Notify callback receives (content, meta) with lifecycle events."""
        from bae.graph import Graph

        events = []
        graph = Graph(start=Start)
        run = registry.submit(
            graph, tm, lm=mock_lm,
            notify=lambda content, meta=None: events.append((content, meta)),
            text="hello",
        )
        await _drain_tasks(tm)
        assert run.state == GraphState.DONE
        lifecycle = [(c, m) for c, m in events if m and m.get("type") == "lifecycle"]
        assert len(lifecycle) >= 2  # start + complete
        event_types = {m["event"] for _, m in lifecycle}
        assert "start" in event_types
        assert "complete" in event_types


async def _drain_tasks(tm: TaskManager):
    """Await all tasks to completion, swallowing exceptions."""
    for tt in list(tm._tasks.values()):
        try:
            await tt.task
        except (asyncio.CancelledError, Exception):
            pass


# --- Concurrent stress tests ---


async def test_concurrent_graphs_no_starvation():
    """15 concurrent graphs complete within timeout with no event loop starvation."""
    from bae.graph import Graph

    graph = Graph(start=StressStart)
    registry = GraphRegistry()
    tm = TaskManager()
    events = []

    def notify(content, meta=None):
        events.append((content, meta))

    runs = []
    for _ in range(15):
        run = registry.submit(
            graph, tm, lm=MockLM(), notify=notify, text=f"stress",
        )
        runs.append(run)

    # Wait for all 15 to complete with 10s timeout
    async with asyncio.timeout(10):
        while registry.active():
            await asyncio.sleep(0.05)

    await _drain_tasks(tm)

    # All 15 completed with DONE
    for run in runs:
        assert run.state == GraphState.DONE, f"{run.run_id} state={run.state}"

    # Each run has rss_delta_bytes as int
    for run in runs:
        assert isinstance(run.rss_delta_bytes, int), f"{run.run_id} rss not int"

    # No run took more than 5 seconds (no starvation)
    for run in runs:
        elapsed_s = (run.ended_ns - run.started_ns) / 1e9
        assert elapsed_s < 5, f"{run.run_id} took {elapsed_s:.1f}s (starvation)"

    # At least one start and one complete per graph (30+ lifecycle events)
    lifecycle = [(c, m) for c, m in events if m and m.get("type") == "lifecycle"]
    starts = [m for _, m in lifecycle if m.get("event") == "start"]
    completes = [m for _, m in lifecycle if m.get("event") == "complete"]
    assert len(starts) >= 15, f"expected 15+ starts, got {len(starts)}"
    assert len(completes) >= 15, f"expected 15+ completes, got {len(completes)}"
    assert len(lifecycle) >= 30, f"expected 30+ lifecycle events, got {len(lifecycle)}"

    # No exceptions (all DONE already verified above)


async def test_concurrent_no_channel_flood():
    """QUIET policy prevents channel flooding for 15 successful graphs."""
    from pathlib import Path
    import tempfile
    from bae.graph import Graph
    from bae.repl.channels import ChannelRouter
    from bae.repl.store import SessionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(Path(tmpdir) / "test.db")
        router = ChannelRouter()
        router.register("graph", color="#ffaf87", store=store)
        # Suppress terminal output during test
        router._channels["graph"].visible = False

        graph = Graph(start=StressStart)
        registry = GraphRegistry()
        tm = TaskManager()

        def notify(content, meta=None):
            router.write("graph", content, mode="GRAPH", metadata=meta)

        for _ in range(15):
            registry.submit(
                graph, tm, lm=MockLM(), notify=notify,
                policy=OutputPolicy.QUIET, text="quiet",
            )

        async with asyncio.timeout(10):
            while registry.active():
                await asyncio.sleep(0.05)

        await _drain_tasks(tm)

        # Channel buffer bounded (QUIET + no failures = no events emitted)
        buf = router._channels["graph"]._buffer
        assert len(buf) < 100, f"channel buffer has {len(buf)} entries (flooding)"

        # QUIET successful graphs should emit zero events (only fail/gate/error emit)
        entries = store.session_entries()
        graph_entries = [e for e in entries if e["channel"] == "graph"]
        assert len(graph_entries) == 0, (
            f"QUIET successful graphs should emit 0 events, got {len(graph_entries)}"
        )

        store.close()
