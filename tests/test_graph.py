"""Tests for Graph class."""

import pytest
from bae.graph import Graph
from bae.node import Node


# Test nodes for main graph tests
class Start(Node):
    query: str
    intent: str = ""

    def __call__(self, prev: None) -> Process | Clarify:
        if self.intent == "unclear":
            return Clarify(question="What?")
        return Process(task=self.intent)


class Clarify(Node):
    question: str
    answer: str = ""

    def __call__(self, prev: Start) -> Start:
        return Start(query=f"{prev.query} - {self.answer}")


class Process(Node):
    task: str
    result: str = ""

    def __call__(self, prev: Start) -> Review | None:
        if self.result:
            return Review(content=self.result)
        return None


class Review(Node):
    content: str
    approved: bool = False

    def __call__(self, prev: Process) -> Process | None:
        if self.approved:
            return None
        return Process(task="retry")


# Nodes for infinite loop test
class LoopA(Node):
    x: str = ""

    def __call__(self, prev: None) -> LoopB:
        return LoopB()


class LoopB(Node):
    x: str = ""

    def __call__(self, prev: LoopA) -> LoopA:
        return LoopA()


# Node for max steps test
class Infinite(Node):
    x: int = 0

    def __call__(self, prev: None) -> Infinite:
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
        # Clarify has no terminal path (loops forever via Start)
        # but Start can reach Process which is terminal
        # Actually: Start -> Clarify -> Start -> Process -> None (terminal)
        # So all nodes have a terminal path
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
    @pytest.mark.asyncio
    async def test_run_simple_path(self):
        graph = Graph(start=Start)

        # Create start node with outputs pre-filled (simulating LLM)
        start = Start(query="hello", intent="greet")
        start_with_outputs = Start(query="hello", intent="greet")

        # Process needs result to terminate
        # For now, manually testing the flow
        result = await graph.run(start_with_outputs, max_steps=5)

        # Should have gone Start -> Process (terminated because result empty)
        assert isinstance(result, Process)

    @pytest.mark.asyncio
    async def test_run_max_steps(self):
        graph = Graph(start=Infinite)

        with pytest.raises(RuntimeError, match="exceeded"):
            await graph.run(Infinite(), max_steps=10)
