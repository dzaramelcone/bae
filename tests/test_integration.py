"""Integration tests with real LLM backends.

These tests make actual API calls - run with:
    uv run pytest tests/test_integration.py -v -s

For Claude CLI tests, just have claude CLI available.
"""

from __future__ import annotations

import pytest
from bae.node import Node
from bae.graph import Graph
from bae.lm import LM, ClaudeCLIBackend
from bae.result import GraphResult


# Simple task decomposition graph
class Task(Node):
    """A task to be processed."""

    description: str

    async def __call__(self, lm: LM) -> SubTasks | Result:
        """Decide whether to break down into subtasks or produce result directly."""
        return await lm.decide(self)


class SubTasks(Node):
    """A task broken into subtasks."""

    original: str
    subtasks: list[str]

    async def __call__(self, lm: LM) -> Result:
        """Process subtasks and produce final result."""
        return await lm.make(self, Result)


class Result(Node):
    """Final result of task processing."""

    summary: str
    steps_taken: list[str]

    async def __call__(self, lm: LM) -> None:
        """Terminal node."""
        return None


# Simple Q&A graph
class Question(Node):
    """A question to answer."""

    text: str

    async def __call__(self, lm: LM) -> Answer | Clarification:
        """Answer directly or ask for clarification."""
        return await lm.decide(self)


class Clarification(Node):
    """Request for clarification."""

    original_question: str
    clarifying_question: str

    async def __call__(self, lm: LM) -> Answer:
        """After clarification, produce answer."""
        return await lm.make(self, Answer)


class Answer(Node):
    """An answer to a question."""

    text: str
    confidence: float

    async def __call__(self, lm: LM) -> None:
        """Terminal node."""
        return None


class TestClaudeCLIBackend:
    """Tests using Claude CLI."""

    @pytest.fixture
    def lm(self):
        return ClaudeCLIBackend(model="claude-opus-4-6")

    async def test_make_produces_typed_output(self, lm):
        """lm.make should produce an instance of the target type."""
        task = Task(description="Add 2+2")
        result = await lm.make(task, Result)

        assert isinstance(result, Result)
        assert isinstance(result.summary, str)
        assert isinstance(result.steps_taken, list)

    async def test_decide_picks_from_options(self, lm):
        """lm.decide should pick one of the valid successor types."""
        task = Task(description="Calculate 2 + 2")
        next_node = await lm.decide(task)

        assert isinstance(next_node, (SubTasks, Result, type(None)))

    async def test_graph_run_simple(self, lm):
        """Run a simple graph to completion."""
        graph = Graph(start=Question)

        result = await graph.arun(text="What is the capital of France?", lm=lm, max_iters=5)

        assert isinstance(result, GraphResult)
        assert result.node is None  # Terminated successfully

    async def test_decide_can_return_none_for_terminal(self, lm):
        """lm.decide should be able to return None for terminal nodes."""
        result = Result(summary="Done", steps_taken=["step 1"])
        next_node = await lm.decide(result)

        # Result's only option is None (terminal)
        assert next_node is None

    async def test_graph_run_task_decomposition(self):
        """Run task decomposition graph."""
        # Use longer timeout for multi-step graph
        lm = ClaudeCLIBackend(model="claude-opus-4-6", timeout=60)
        graph = Graph(start=Task)

        result = await graph.arun(description="Make a peanut butter sandwich", lm=lm, max_iters=10)

        assert isinstance(result, GraphResult)
        assert result.node is None  # Terminated successfully


class TestGraphTopology:
    """Test that graph topology is correctly discovered."""

    def test_task_graph_topology(self):
        graph = Graph(start=Task)

        assert graph.nodes == {Task, SubTasks, Result}
        assert graph.edges[Task] == {SubTasks, Result}
        assert graph.edges[SubTasks] == {Result}
        assert graph.edges[Result] == set()
        assert graph.terminal_nodes == {Result}

    def test_qa_graph_topology(self):
        graph = Graph(start=Question)

        assert graph.nodes == {Question, Clarification, Answer}
        assert graph.edges[Question] == {Answer, Clarification}
        assert graph.edges[Clarification] == {Answer}
        assert graph.edges[Answer] == set()
        assert graph.terminal_nodes == {Answer}
