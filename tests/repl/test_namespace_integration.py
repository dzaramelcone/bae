"""Integration tests for namespace wiring in CortexShell."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bae.exceptions import BaeError
from bae.graph import Graph
from bae.markers import Dep, Recall
from bae.node import Node
from bae.repl.exec import async_exec
from bae.repl.namespace import NsInspector
from bae.repl.shell import CortexShell, channel_arun
from bae.result import GraphResult


# --- Minimal test graph ---


class Start(Node):
    """Start node for integration tests."""

    msg: str

    async def __call__(self) -> End | None:
        return End(result=self.msg)


class End(Node):
    """Terminal node for integration tests."""

    result: str

    async def __call__(self) -> None:
        ...


# --- Fixtures ---


@pytest.fixture
def shell():
    return CortexShell()


@pytest.fixture
def mock_router():
    r = MagicMock()
    r.write = MagicMock()
    return r


# --- Test 1: Shell namespace contains bae types ---


def test_shell_namespace_has_core_types(shell):
    """CortexShell namespace contains Node, Graph, Dep, Recall from seed()."""
    ns = shell.namespace
    from bae import Node as BaeNode, Graph as BaeGraph, Dep as BaeDep, Recall as BaeRecall

    assert ns["Node"] is BaeNode
    assert ns["Graph"] is BaeGraph
    assert ns["Dep"] is BaeDep
    assert ns["Recall"] is BaeRecall


def test_shell_namespace_has_ns_inspector(shell):
    """CortexShell namespace contains ns as NsInspector."""
    assert isinstance(shell.namespace["ns"], NsInspector)


def test_shell_namespace_has_runtime_objects(shell):
    """CortexShell namespace contains store and channels (runtime objects)."""
    assert "store" in shell.namespace
    assert "channels" in shell.namespace
    assert shell.namespace["store"] is shell.store
    assert shell.namespace["channels"] is shell.router


def test_shell_namespace_has_extras(shell):
    """CortexShell namespace contains GraphResult, LM, NodeConfig, Annotated."""
    assert "GraphResult" in shell.namespace
    assert "LM" in shell.namespace
    assert "NodeConfig" in shell.namespace
    assert "Annotated" in shell.namespace


# --- Test 2: _ capture works via async_exec ---


@pytest.mark.asyncio
async def test_underscore_capture(shell):
    """Evaluating an expression sets _ in the shell namespace."""
    result, captured = await async_exec("42", shell.namespace)
    assert result == 42
    assert shell.namespace["_"] == 42


@pytest.mark.asyncio
async def test_underscore_capture_string(shell):
    """String expressions captured correctly in namespace."""
    result, _ = await async_exec("'hello'", shell.namespace)
    assert result == "hello"
    assert shell.namespace["_"] == "hello"


# --- Test 3: _trace capture on successful graph run ---


@pytest.mark.asyncio
async def test_trace_capture_success(mock_router):
    """channel_arun returns GraphResult with trace accessible for _trace capture."""
    graph = Graph(start=Start)
    start_node = Start(msg="hello")
    result = await channel_arun(graph, start_node, mock_router)

    assert result is not None
    assert result.trace is not None
    assert len(result.trace) == 2
    assert isinstance(result.trace[0], Start)
    assert isinstance(result.trace[1], End)
    assert result.trace[1].result == "hello"


@pytest.mark.asyncio
async def test_trace_capture_sets_namespace(shell):
    """Simulating GRAPH mode: _trace set in namespace after successful run."""
    graph = Graph(start=Start)
    start_node = Start(msg="world")
    result = await channel_arun(graph, start_node, shell.router)

    # Simulate what the GRAPH mode handler does
    if result and result.trace:
        shell.namespace["_trace"] = result.trace

    assert "_trace" in shell.namespace
    assert len(shell.namespace["_trace"]) == 2
    assert isinstance(shell.namespace["_trace"][-1], End)


# --- Test 4: _trace capture on error ---


@pytest.mark.asyncio
async def test_trace_capture_on_error(shell):
    """_trace captured from exception.trace on graph execution error."""
    # Create a mock graph that raises BaeError with .trace
    partial_trace = [Start(msg="before-error")]
    err = BaeError("max iters exceeded")
    err.trace = partial_trace

    mock_graph = MagicMock()
    mock_graph.arun = AsyncMock(side_effect=err)

    # Simulate the GRAPH mode error handler
    try:
        await channel_arun(mock_graph, Start(msg="test"), shell.router)
    except Exception as exc:
        trace = getattr(exc, "trace", None)
        if trace:
            shell.namespace["_trace"] = trace

    assert "_trace" in shell.namespace
    assert shell.namespace["_trace"] is partial_trace
    assert len(shell.namespace["_trace"]) == 1


@pytest.mark.asyncio
async def test_trace_not_set_when_error_has_no_trace(shell):
    """_trace not set if exception has no .trace attribute."""
    mock_graph = MagicMock()
    mock_graph.arun = AsyncMock(side_effect=RuntimeError("unrelated error"))

    try:
        await channel_arun(mock_graph, Start(msg="test"), shell.router)
    except Exception as exc:
        trace = getattr(exc, "trace", None)
        if trace:
            shell.namespace["_trace"] = trace

    assert "_trace" not in shell.namespace


# --- Test 5: ns() callable in namespace ---


def test_ns_callable_lists_namespace(shell, capsys):
    """ns() in shell namespace prints namespace contents including bae types."""
    ns_fn = shell.namespace["ns"]
    ns_fn()
    output = capsys.readouterr().out
    assert "Node" in output
    assert "Graph" in output
    assert "Dep" in output
    assert "Recall" in output
    assert "store" in output
    assert "channels" in output


def test_ns_callable_inspects_object(shell, capsys):
    """ns(obj) inspects an object from the namespace."""
    ns_fn = shell.namespace["ns"]
    ns_fn(42)
    output = capsys.readouterr().out
    assert "int" in output
    assert "42" in output
