"""Tests for Graph class."""

from __future__ import annotations

import asyncio
import inspect
from typing import Annotated
from unittest.mock import AsyncMock, patch

import pytest

from pydantic import BaseModel

from bae.exceptions import BaeError
from bae.graph import Graph, graph
from bae.markers import Dep
from bae.node import Node
from bae.lm import LM
from bae.result import GraphResult


# Mock LM for testing
class MockLM:
    """Mock LM that returns nodes from a sequence.

    Supports v1 methods (make/decide) for custom __call__ nodes that invoke
    them directly, plus v2 stubs (choose_type/fill) for Protocol shape.
    """

    def __init__(self, sequence: list[Node | None]):
        self.sequence = sequence
        self.index = 0

    async def make(self, node: Node, target: type) -> Node:
        result = self.sequence[self.index]
        self.index += 1
        return result

    async def decide(self, node: Node) -> Node | None:
        result = self.sequence[self.index]
        self.index += 1
        return result

    async def choose_type(self, types, context):
        raise NotImplementedError("v1 test mock -- custom nodes don't use choose_type")

    async def fill(self, target, resolved, instruction, source=None):
        raise NotImplementedError("v1 test mock -- custom nodes don't use fill")


# Test nodes
class Start(Node):
    query: str

    async def __call__(self, lm: LM) -> Process | Clarify:
        return await lm.decide(self)


class Clarify(Node):
    question: str

    async def __call__(self, lm: LM) -> Start:
        return await lm.make(self, Start)


class Process(Node):
    task: str

    async def __call__(self, lm: LM) -> Review | None:
        return await lm.decide(self)


class Review(Node):
    content: str

    async def __call__(self, lm: LM) -> Process | None:
        return await lm.decide(self)


# Nodes for infinite loop test
class LoopA(Node):
    x: str = ""

    async def __call__(self, lm: LM) -> LoopB:
        return await lm.make(self, LoopB)


class LoopB(Node):
    x: str = ""

    async def __call__(self, lm: LM) -> LoopA:
        return await lm.make(self, LoopA)


# Node for max steps test
class Infinite(Node):
    x: int = 0

    async def __call__(self, lm: LM) -> Infinite:
        return Infinite(x=self.x + 1)


class TestGraphDiscovery:
    def test_discovers_all_nodes(self):
        graph = Graph(start=Start)
        assert graph.nodes == {Start, Clarify, Process, Review}

    def test_edges(self):
        graph = Graph(start=Start)
        edges = graph.edges

        assert edges[Start] == {Process, Clarify}
        assert edges[Clarify] == {Start}
        assert edges[Process] == {Review}
        assert edges[Review] == {Process}

    def test_terminal_nodes(self):
        graph = Graph(start=Start)
        # Process and Review can both return None
        assert graph.terminal_nodes == {Process, Review}


class TestGraphValidation:
    def test_valid_graph(self):
        graph = Graph(start=Start)
        issues = graph.validate()
        assert issues == []

    def test_detects_infinite_loop(self):
        graph = Graph(start=LoopA)
        issues = graph.validate()

        assert len(issues) == 2
        assert any("no path to a terminal" in i for i in issues)


class TestGraphInstanceGuard:
    def test_graph_rejects_instance(self):
        """Graph(start=instance) raises TypeError with helpful message."""
        instance = Start(query="hello")
        with pytest.raises(TypeError, match="expects a Node class, got an instance"):
            Graph(start=instance)

    def test_graph_rejects_instance_message_suggests_fix(self):
        """Error message tells user to pass the class instead."""
        instance = Start(query="hello")
        with pytest.raises(TypeError, match=r"Use Graph\(start=Start\)"):
            Graph(start=instance)


class TestGraphMermaid:
    def test_mermaid_output(self):
        graph = Graph(start=Start)
        mermaid = graph.to_mermaid()

        assert "graph TD" in mermaid
        assert "Start --> Process" in mermaid
        assert "Start --> Clarify" in mermaid


class TestGraphRun:
    async def test_run_simple_path(self):
        graph = Graph(start=Start)

        # LM returns: Process -> None (terminal)
        lm = MockLM(sequence=[
            Process(task="do it"),
            None,
        ])

        result = await graph.arun(query="hello", lm=lm)

        # Returns GraphResult with node=None (terminated)
        assert isinstance(result, GraphResult)
        assert result.node is None
        assert len(result.trace) == 2  # Start, Process

    async def test_run_multiple_steps(self):
        graph = Graph(start=Start)

        # LM returns: Process -> Review -> None
        lm = MockLM(sequence=[
            Process(task="do it"),
            Review(content="looks good"),
            None,
        ])

        result = await graph.arun(query="hello", lm=lm)
        assert isinstance(result, GraphResult)
        assert result.node is None
        assert len(result.trace) == 3  # Start, Process, Review

    async def test_run_max_iters(self):
        graph = Graph(start=Infinite)

        # Infinite doesn't use LM, just returns new Infinite
        lm = MockLM(sequence=[])

        with pytest.raises(BaeError, match="exceeded"):
            await graph.arun(lm=lm, max_iters=10)


# =============================================================================
# dep_cache injection tests
# =============================================================================


dep_call_count = 0


def get_greeting() -> str:
    """Dep function that tracks calls."""
    global dep_call_count
    dep_call_count += 1
    return "hello from dep"


class DepStart(Node):
    """Start node with a Dep field for dep_cache tests."""
    greeting: Annotated[str, Dep(get_greeting)]

    async def __call__(self) -> None:
        ...


class MockV2LM:
    """Mock LM implementing v2 API for dep_cache tests."""

    def __init__(self):
        self.fill_calls: list = []

    async def choose_type(self, types, context):
        return types[0]

    async def fill(self, target, resolved, instruction, source=None):
        self.fill_calls.append((target, resolved, instruction))
        return target.model_construct(**resolved)

    async def make(self, node, target):
        raise NotImplementedError

    async def decide(self, node):
        raise NotImplementedError


class TestDepCache:
    async def test_dep_cache_seeds_resolver(self):
        """dep_cache pre-seeds resolver -- dep function not called."""
        global dep_call_count
        dep_call_count = 0

        graph = Graph(start=DepStart)
        lm = MockV2LM()

        result = await graph.arun(
            lm=lm, dep_cache={get_greeting: "preseeded"}
        )

        assert dep_call_count == 0, "dep function should not be called when pre-seeded"
        assert result.trace[0].greeting == "preseeded"

    async def test_dep_cache_none_is_default(self):
        """arun() without dep_cache works exactly as before."""
        global dep_call_count
        dep_call_count = 0

        graph = Graph(start=DepStart)
        lm = MockV2LM()

        result = await graph.arun(lm=lm)

        assert dep_call_count == 1, "dep function should be called normally"
        assert result.trace[0].greeting == "hello from dep"

    async def test_dep_cache_does_not_shadow_lm(self):
        """dep_cache doesn't clobber LM_KEY unless explicitly set."""
        graph = Graph(start=DepStart)
        lm = MockV2LM()

        result = await graph.arun(
            lm=lm, dep_cache={get_greeting: "preseeded"}
        )

        # The LM should still be the one we passed, not overwritten by dep_cache
        # DepStart is terminal (returns None), so LM isn't called for fill.
        # But verify the graph used our LM by checking it completed normally.
        assert isinstance(result, GraphResult)
        assert len(result.trace) == 1

    async def test_arun_yields_to_event_loop(self):
        """asyncio.sleep(0) is called during graph execution."""
        graph = Graph(start=DepStart)
        lm = MockV2LM()

        with patch("bae.graph.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await graph.arun(lm=lm)

        mock_sleep.assert_called_with(0)


# =============================================================================
# graph() factory tests
# =============================================================================


class FactoryStart(Node):
    message: str

    def __call__(self) -> FactoryEnd: ...


class FactoryEnd(Node):
    reply: str

    async def __call__(self) -> None: ...


class TInput(BaseModel):
    value: str
    label: str = "default"


class CompositeStart(Node):
    inp: TInput
    extra: str

    def __call__(self) -> FactoryEnd: ...


class TraceA(Node):
    msg: str
    def __call__(self) -> TraceB: ...


class TraceB(Node):
    reply: str
    def __call__(self) -> TraceC: ...


class TraceC(Node):
    final: str
    async def __call__(self) -> None: ...


class TestArunPartialTrace:
    async def test_runtime_error_carries_trace(self):
        """RuntimeError from LM timeout carries .trace with partial execution."""

        class TraceMockLM:
            """LM that succeeds on first fill then raises RuntimeError."""

            def __init__(self):
                self.calls = 0

            async def choose_type(self, types, context):
                return types[0]

            async def fill(self, target, resolved, instruction, source=None):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("Claude CLI timed out after 120s")
                return target.model_construct(**resolved)

            async def make(self, node, target):
                raise NotImplementedError

            async def decide(self, node):
                raise NotImplementedError

        graph_obj = Graph(start=TraceA)
        lm = TraceMockLM()
        with pytest.raises(RuntimeError, match="timed out") as exc_info:
            await graph_obj.arun(msg="hi", lm=lm)
        assert hasattr(exc_info.value, "trace")
        assert isinstance(exc_info.value.trace, list)
        # TraceA was traced, TraceB fill succeeded, then TraceC fill raised
        assert len(exc_info.value.trace) >= 2
        assert type(exc_info.value.trace[0]).__name__ == "TraceA"
        assert type(exc_info.value.trace[1]).__name__ == "TraceB"

    async def test_bae_error_trace_not_overwritten(self):
        """BaeError from max_iters already has .trace -- outer catch doesn't overwrite."""
        graph_obj = Graph(start=Infinite)
        lm = MockLM(sequence=[])
        with pytest.raises(BaeError, match="exceeded") as exc_info:
            await graph_obj.arun(lm=lm, max_iters=5)
        assert hasattr(exc_info.value, "trace")
        assert len(exc_info.value.trace) == 5


class TestGraphFactory:
    def test_graph_factory_returns_callable(self):
        """graph() returns an async callable."""
        fn = graph(start=FactoryStart)
        assert callable(fn)
        assert inspect.iscoroutinefunction(fn)

    def test_graph_factory_signature(self):
        """graph() callable has typed signature from start node fields."""
        fn = graph(start=FactoryStart)
        sig = inspect.signature(fn)
        assert "message" in sig.parameters
        p = sig.parameters["message"]
        assert p.kind == inspect.Parameter.KEYWORD_ONLY
        assert p.annotation is str

    async def test_graph_factory_executes(self):
        """graph() callable executes the graph and returns GraphResult."""
        fn = graph(start=FactoryStart)
        lm = MockV2LM()
        result = await fn(message="hi", lm=lm)
        assert isinstance(result, GraphResult)
        assert len(result.trace) == 2

    def test_graph_factory_has_name(self):
        """graph() callable has _name display string, not a leaked Graph."""
        fn = graph(start=FactoryStart)
        assert fn._name == "FactoryStart"
        assert not hasattr(fn, "_graph")

    async def test_graph_factory_missing_field_raises(self):
        """graph() callable raises TypeError for missing required fields."""
        fn = graph(start=FactoryStart)
        lm = MockV2LM()
        with pytest.raises(TypeError, match="message"):
            await fn(lm=lm)

    def test_graph_factory_name(self):
        """graph() callable has __name__ set to start class name."""
        fn = graph(start=FactoryStart)
        assert fn.__name__ == "FactoryStart"

    def test_graph_factory_signature_includes_lm_and_dep_cache(self):
        """graph() callable signature includes lm and dep_cache with defaults."""
        fn = graph(start=FactoryStart)
        sig = inspect.signature(fn)
        assert "lm" in sig.parameters
        assert sig.parameters["lm"].default is None
        assert "dep_cache" in sig.parameters
        assert sig.parameters["dep_cache"].default is None

    def test_graph_factory_flattens_basemodel_params(self):
        """graph() flattens BaseModel fields into simple params."""
        fn = graph(start=CompositeStart)
        sig = inspect.signature(fn)
        # BaseModel TInput fields are flattened
        assert "value" in sig.parameters
        assert sig.parameters["value"].annotation is str
        assert "label" in sig.parameters
        assert sig.parameters["label"].default == "default"
        # Original BaseModel field name is NOT in signature
        assert "inp" not in sig.parameters
        # Simple field is still present
        assert "extra" in sig.parameters

    async def test_graph_factory_flattened_call(self):
        """graph() callable accepts flat kwargs and reconstructs BaseModel."""
        fn = graph(start=CompositeStart)
        lm = MockV2LM()
        result = await fn(value="hello", extra="world", lm=lm)
        assert isinstance(result, GraphResult)
        # Verify TInput was reconstructed: start node has inp field
        start_node = result.trace[0]
        assert hasattr(start_node, "inp")
        assert isinstance(start_node.inp, TInput)
        assert start_node.inp.value == "hello"
        assert start_node.inp.label == "default"

    def test_graph_factory_no_param_types(self):
        """graph() wrapper no longer has _param_types attribute."""
        fn = graph(start=CompositeStart)
        assert not hasattr(fn, "_param_types")
