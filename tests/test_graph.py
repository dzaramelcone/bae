"""Tests for Graph class."""

from __future__ import annotations

import pytest
from bae.graph import Graph
from bae.node import Node
from bae.lm import LM
from bae.result import GraphResult


# Mock LM for testing
class MockLM:
    """Mock LM that returns nodes from a sequence."""

    def __init__(self, sequence: list[Node | None]):
        self.sequence = sequence
        self.index = 0

    def make(self, node: Node, target: type) -> Node:
        result = self.sequence[self.index]
        self.index += 1
        return result

    def decide(self, node: Node) -> Node | None:
        result = self.sequence[self.index]
        self.index += 1
        return result


# Test nodes
class Start(Node):
    query: str

    def __call__(self, lm: LM) -> Process | Clarify:
        return lm.decide(self)


class Clarify(Node):
    question: str

    def __call__(self, lm: LM) -> Start:
        return lm.make(self, Start)


class Process(Node):
    task: str

    def __call__(self, lm: LM) -> Review | None:
        return lm.decide(self)


class Review(Node):
    content: str

    def __call__(self, lm: LM) -> Process | None:
        return lm.decide(self)


# Nodes for infinite loop test
class LoopA(Node):
    x: str = ""

    def __call__(self, lm: LM) -> LoopB:
        return lm.make(self, LoopB)


class LoopB(Node):
    x: str = ""

    def __call__(self, lm: LM) -> LoopA:
        return lm.make(self, LoopA)


# Node for max steps test
class Infinite(Node):
    x: int = 0

    def __call__(self, lm: LM) -> Infinite:
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
    def test_run_simple_path(self):
        graph = Graph(start=Start)

        # LM returns: Process -> None (terminal)
        lm = MockLM(sequence=[
            Process(task="do it"),
            None,
        ])

        result = graph.run(Start(query="hello"), lm=lm)

        # Returns GraphResult with node=None (terminated)
        assert isinstance(result, GraphResult)
        assert result.node is None
        assert len(result.trace) == 2  # Start, Process

    def test_run_multiple_steps(self):
        graph = Graph(start=Start)

        # LM returns: Process -> Review -> None
        lm = MockLM(sequence=[
            Process(task="do it"),
            Review(content="looks good"),
            None,
        ])

        result = graph.run(Start(query="hello"), lm=lm)
        assert isinstance(result, GraphResult)
        assert result.node is None
        assert len(result.trace) == 3  # Start, Process, Review

    def test_run_max_steps(self):
        graph = Graph(start=Infinite)

        # Infinite doesn't use LM, just returns new Infinite
        lm = MockLM(sequence=[])

        with pytest.raises(RuntimeError, match="exceeded"):
            graph.run(Infinite(), lm=lm, max_steps=10)
