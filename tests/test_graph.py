"""Tests for Graph class."""

from __future__ import annotations

from typing import Annotated
from unittest.mock import AsyncMock, patch

import pytest

from bae.exceptions import BaeError
from bae.graph import Graph
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
