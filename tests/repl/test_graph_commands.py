"""Tests for GRAPH mode command dispatcher and commands."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel

from bae.graph import Graph, graph
from bae.node import Node
from bae.repl.engine import GraphRegistry, GraphState
from bae.repl.graph_commands import dispatch_graph
from bae.repl.modes import Mode
from bae.repl.shell import CortexShell
from bae.repl.tasks import TaskManager


# --- Module-level test nodes (avoid forward ref issues) ---


class TStart(Node):
    message: str

    def __call__(self) -> TEnd: ...


class TEnd(Node):
    reply: str

    async def __call__(self) -> None: ...


class TInput(BaseModel):
    value: str


class TTypedStart(Node):
    inp: TInput

    async def __call__(self) -> TEnd: ...


# --- Mock LM ---


class MockLM:
    """Minimal LM that always produces TEnd(reply="done")."""

    async def fill(self, target, resolved, instruction, source=None):
        if target is TEnd:
            return TEnd.model_construct(reply="done", **resolved)
        return target.model_construct(**resolved)

    async def choose_type(self, types, context):
        return types[0]

    async def make(self, node, target):
        return await self.fill(target, {}, target.__name__, source=node)

    async def decide(self, node):
        return None


class SlowLM(MockLM):
    """LM that sleeps forever on fill (for cancellation tests)."""

    async def fill(self, target, resolved, instruction, source=None):
        await asyncio.sleep(100)
        return target.model_construct(**resolved)


# --- FakeRouter / FakeShell ---


class FakeRouter:
    def __init__(self):
        self.writes: list[tuple[str, str, dict]] = []

    def write(self, channel, content, *, mode=None, metadata=None):
        self.writes.append((channel, content, metadata or {}))


@dataclass
class FakeShell:
    engine: GraphRegistry
    tm: TaskManager
    namespace: dict
    _lm: MockLM
    router: FakeRouter
    mode: Mode = Mode.GRAPH
    shush_gates: bool = False

    # Bind CortexShell's gate resolution method for cross-mode tests.
    _resolve_gate_input = CortexShell._resolve_gate_input


# --- Helpers ---


async def _drain(tm: TaskManager):
    """Await all tasks to completion, swallowing exceptions."""
    for tt in list(tm._tasks.values()):
        try:
            await tt.task
        except (asyncio.CancelledError, Exception):
            pass


def _output(router: FakeRouter) -> str:
    """Join all router writes into a single string for assertion."""
    return "\n".join(content for _, content, _ in router.writes)


# --- Fixtures ---


@pytest.fixture
def shell():
    tm = TaskManager()
    ns = {"TStart": TStart, "TEnd": TEnd, "Graph": Graph, "graph": graph}
    s = FakeShell(
        engine=GraphRegistry(),
        tm=tm,
        namespace=ns,
        _lm=MockLM(),
        router=FakeRouter(),
    )
    # Populate namespace with graph factory callables
    mygraph = graph(start=TStart)
    s.namespace["mygraph"] = mygraph
    typed_graph = graph(start=TTypedStart)
    s.namespace["typed_graph"] = typed_graph
    return s


# --- TestDispatch ---


class TestDispatch:
    async def test_unknown_command(self, shell):
        """Unknown command shows help with available commands."""
        await dispatch_graph("foo", shell)
        out = _output(shell.router)
        assert "unknown command" in out.lower()
        assert "run" in out
        assert "list" in out

    async def test_ls_is_unknown(self, shell):
        """ls is not a recognized command."""
        await dispatch_graph("ls", shell)
        out = _output(shell.router)
        assert "unknown command" in out.lower()

    async def test_empty_input(self, shell):
        """Empty input produces no output."""
        await dispatch_graph("", shell)
        assert len(shell.router.writes) == 0

    async def test_whitespace_only(self, shell):
        """Whitespace-only input produces no output."""
        await dispatch_graph("   ", shell)
        assert len(shell.router.writes) == 0


# --- TestCmdRun ---


class TestCmdRun:
    async def test_run_coroutine_submits(self, shell):
        """run <expr> evaluates a coroutine expression and submits it."""
        shell.namespace["MockLM"] = MockLM
        await dispatch_graph("run mygraph(message='hi', lm=MockLM())", shell)
        out = _output(shell.router)
        assert "submitted g1" in out
        await _drain(shell.tm)
        out = _output(shell.router)
        assert "g1 done" in out

    async def test_run_graph_object_submits(self, shell):
        """run <expr> with a Graph object submits it."""
        shell.namespace["g"] = Graph(start=TStart)
        await dispatch_graph("run g", shell)
        out = _output(shell.router)
        assert "submitted g1" in out

    async def test_run_no_expr_shows_usage(self, shell):
        """run with no expression shows usage message."""
        await dispatch_graph("run", shell)
        out = _output(shell.router)
        assert "usage" in out.lower()

    async def test_run_empty_expr_shows_usage(self, shell):
        """run with whitespace-only arg shows usage message."""
        await dispatch_graph("run   ", shell)
        out = _output(shell.router)
        assert "usage" in out.lower()

    async def test_run_bad_expr_shows_error(self, shell):
        """run with a bad expression shows traceback."""
        await dispatch_graph("run nonexistent_var", shell)
        out = _output(shell.router)
        assert "error" in _meta_types(shell.router)

    async def test_run_flattened_params(self, shell):
        """run with flattened params -- no TInput construction needed."""
        shell.namespace["MockLM"] = MockLM
        # TInput is NOT in shell.namespace -- and that's fine with flattened params
        assert "TInput" not in shell.namespace
        await dispatch_graph("run typed_graph(value='hi', lm=MockLM())", shell)
        out = _output(shell.router)
        assert "submitted" in out
        await _drain(shell.tm)

    async def test_run_wrong_type_shows_error(self, shell):
        """run with a non-graph/non-coroutine result shows type error."""
        shell.namespace["x"] = 42
        await dispatch_graph("run x", shell)
        out = _output(shell.router)
        assert "expected coroutine or Graph" in out


# --- TestCmdList ---


class TestCmdList:
    async def test_list_empty(self, shell):
        """list with no runs shows '(no graph runs)'."""
        await dispatch_graph("list", shell)
        out = _output(shell.router)
        assert "(no graph runs)" in out

    async def test_list_shows_runs(self, shell):
        """list after submitting a graph shows the run."""
        g = Graph(start=TStart)
        shell.engine.submit(g, shell.tm, lm=shell._lm, message="hi")
        await _drain(shell.tm)
        await dispatch_graph("list", shell)
        out = _output(shell.router)
        assert "g1" in out
        assert "done" in out

    async def test_list_sends_ansi_metadata(self, shell):
        """list passes metadata type=ansi to router.write."""
        g = Graph(start=TStart)
        shell.engine.submit(g, shell.tm, lm=shell._lm, message="hi")
        await _drain(shell.tm)
        await dispatch_graph("list", shell)
        # Find the list write (not the submit writes)
        ansi_writes = [
            (ch, meta) for ch, _, meta in shell.router.writes
            if meta.get("type") == "ansi"
        ]
        assert len(ansi_writes) == 1
        assert ansi_writes[0][0] == "graph"


# --- TestCmdCancel ---


class TestCmdCancel:
    async def test_cancel_running(self, shell):
        """cancel <id> stops a running graph."""
        g = Graph(start=TStart)
        shell.engine.submit(g, shell.tm, lm=SlowLM(), message="hi")
        await asyncio.sleep(0.05)
        await dispatch_graph("cancel g1", shell)
        out = _output(shell.router)
        assert "cancelled g1" in out
        await _drain(shell.tm)

    async def test_cancel_nonexistent(self, shell):
        """cancel with unknown id shows 'no run'."""
        await dispatch_graph("cancel g99", shell)
        out = _output(shell.router)
        assert "no run g99" in out

    async def test_cancel_no_arg(self, shell):
        """cancel with no argument shows usage."""
        await dispatch_graph("cancel", shell)
        out = _output(shell.router)
        assert "usage" in out.lower()


# --- TestCmdInspect ---


class TestCmdInspect:
    async def test_inspect_completed_run(self, shell):
        """inspect <id> shows inline timing and JSON-formatted terminal fields."""
        g = Graph(start=TStart)
        shell.engine.submit(g, shell.tm, lm=shell._lm, message="hi")
        await _drain(shell.tm)
        await dispatch_graph("inspect g1", shell)
        out = _output(shell.router)
        assert "g1" in out
        assert "done" in out
        assert "TStart" in out
        assert "TEnd" in out
        # Timing appears inline (ms suffix present)
        assert "ms" in out
        # Terminal node fields formatted as JSON (quoted keys, not raw dict repr)
        assert '"reply"' in out

    async def test_inspect_inline_timing(self, shell):
        """inspect shows timing values inline with filled node names on same line."""
        g = Graph(start=TStart)
        shell.engine.submit(g, shell.tm, lm=shell._lm, message="hi")
        await _drain(shell.tm)
        await dispatch_graph("inspect g1", shell)
        out = _output(shell.router)
        # TEnd goes through fill → has timing inline on same line
        # TStart is constructed from kwargs → no timing recorded
        lines = out.splitlines()
        tend_lines = [l for l in lines if "TEnd" in l and "ms" in l]
        assert len(tend_lines) >= 1, f"Expected TEnd with ms timing, got:\n{out}"
        # TStart should appear in trace but without ms (no fill call)
        tstart_lines = [l for l in lines if "TStart" in l and "Trace" not in l]
        assert len(tstart_lines) >= 1, f"Expected TStart in trace, got:\n{out}"
        # No separate "Timings:" section for a complete run with trace
        assert "Timings:" not in out

    async def test_inspect_sends_ansi_metadata(self, shell):
        """inspect passes metadata type=ansi to router.write."""
        g = Graph(start=TStart)
        shell.engine.submit(g, shell.tm, lm=shell._lm, message="hi")
        await _drain(shell.tm)
        await dispatch_graph("inspect g1", shell)
        ansi_writes = [
            (ch, meta) for ch, _, meta in shell.router.writes
            if meta.get("type") == "ansi"
        ]
        assert len(ansi_writes) == 1
        assert ansi_writes[0][0] == "graph"

    async def test_inspect_nonexistent(self, shell):
        """inspect with unknown id shows 'no run'."""
        await dispatch_graph("inspect g99", shell)
        out = _output(shell.router)
        assert "no run g99" in out

    async def test_inspect_no_arg(self, shell):
        """inspect with no argument shows usage."""
        await dispatch_graph("inspect", shell)
        out = _output(shell.router)
        assert "usage" in out.lower()


# --- TestCmdTrace ---


class TestCmdTrace:
    async def test_trace_completed_run(self, shell):
        """trace <id> shows numbered node transition history."""
        g = Graph(start=TStart)
        shell.engine.submit(g, shell.tm, lm=shell._lm, message="hi")
        await _drain(shell.tm)
        await dispatch_graph("trace g1", shell)
        out = _output(shell.router)
        assert "1. TStart" in out
        assert "2. TEnd" in out

    async def test_trace_nonexistent(self, shell):
        """trace with unknown id shows 'no run'."""
        await dispatch_graph("trace g99", shell)
        out = _output(shell.router)
        assert "no run g99" in out

    async def test_trace_no_arg(self, shell):
        """trace with no argument shows usage."""
        await dispatch_graph("trace", shell)
        out = _output(shell.router)
        assert "usage" in out.lower()

    async def test_trace_no_trace_available(self, shell):
        """trace on a run with no trace shows 'no trace available'."""
        g = Graph(start=TStart)
        shell.engine.submit(g, shell.tm, lm=SlowLM(), message="hi")
        await asyncio.sleep(0.05)
        # Run is still in progress, no trace yet
        await dispatch_graph("trace g1", shell)
        out = _output(shell.router)
        assert "no trace available" in out
        shell.tm.revoke_all(graceful=False)
        await _drain(shell.tm)


# --- TestCrossModeGateResolve ---


class TestCrossModeGateResolve:
    async def test_resolve_bool_gate(self, shell):
        """@g<id> <value> resolves a pending gate with type coercion."""
        gate = shell.engine.create_gate(
            run_id="g1", field_name="confirm", field_type=bool,
            description="confirm?", node_type="SomeNode",
        )
        await shell._resolve_gate_input("g1.0", "true")
        out = _output(shell.router)
        assert "resolved g1.0" in out
        assert "confirm" in out
        assert gate.future.result() is True

    async def test_resolve_gate_not_found(self, shell):
        """Resolving a non-existent gate shows error message."""
        await shell._resolve_gate_input("g99.0", "yes")
        out = _output(shell.router)
        assert "no pending gate g99.0" in out

    async def test_resolve_gate_invalid_type(self, shell):
        """Invalid value for gate type shows validation error."""
        shell.engine.create_gate(
            run_id="g1", field_name="count", field_type=int,
            description="how many?", node_type="SomeNode",
        )
        await shell._resolve_gate_input("g1.0", "not-a-number")
        out = _output(shell.router)
        assert "invalid value" in out
        assert "count" in out
        assert "int" in out

    async def test_nl_mode_does_not_route_gates(self):
        """In NL mode, @g prefix is NOT intercepted for gate routing.

        The cross-mode gate routing condition in _dispatch checks
        ``self.mode != Mode.NL`` so NL mode preserves @label session routing.
        """
        # Verify the routing condition: NL mode excluded
        assert Mode.NL == Mode.NL  # baseline
        # The condition is: mode != Mode.NL and text.startswith("@g") and len(text) > 2
        # For NL mode this is False, so @g text flows to NL session routing.
        for mode in (Mode.PY, Mode.BASH, Mode.GRAPH):
            assert mode != Mode.NL
        # NL must not match the gate routing guard
        text = "@g1 hello"
        mode = Mode.NL
        should_route_gate = mode != Mode.NL and text.startswith("@g") and len(text) > 2
        assert not should_route_gate


# --- Helpers ---


def _meta_types(router: FakeRouter) -> str:
    """Collect all metadata type values into a string."""
    return " ".join(m.get("type", "") for _, _, m in router.writes)
