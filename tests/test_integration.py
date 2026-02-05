"""Integration tests with real LLM backends.

These tests make actual API calls - run with:
    uv run pytest tests/test_integration.py -v -s

For pydantic-ai tests, set ANTHROPIC_API_KEY.
For Claude CLI tests, just have claude CLI available.
"""

import os
import pytest
from bae.node import Node
from bae.graph import Graph
from bae.lm import LM, PydanticAIBackend, ClaudeCLIBackend
from bae.result import GraphResult


# Simple task decomposition graph
class Task(Node):
    """A task to be processed."""
    description: str

    def __call__(self, lm: LM) -> SubTasks | Result:
        """Decide whether to break down into subtasks or produce result directly."""
        return lm.decide(self)


class SubTasks(Node):
    """A task broken into subtasks."""
    original: str
    subtasks: list[str]

    def __call__(self, lm: LM) -> Result:
        """Process subtasks and produce final result."""
        return lm.make(self, Result)


class Result(Node):
    """Final result of task processing."""
    summary: str
    steps_taken: list[str]

    def __call__(self, lm: LM) -> None:
        """Terminal node."""
        return None


# Simple Q&A graph
class Question(Node):
    """A question to answer."""
    text: str

    def __call__(self, lm: LM) -> Answer | Clarification:
        """Answer directly or ask for clarification."""
        return lm.decide(self)


class Clarification(Node):
    """Request for clarification."""
    original_question: str
    clarifying_question: str

    def __call__(self, lm: LM) -> Answer:
        """After clarification, produce answer."""
        return lm.make(self, Answer)


class Answer(Node):
    """An answer to a question."""
    text: str
    confidence: float

    def __call__(self, lm: LM) -> None:
        """Terminal node."""
        return None


# Skip condition for API-based tests
requires_anthropic_key = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)


@requires_anthropic_key
class TestPydanticAIBackend:
    """Tests using pydantic-ai with real LLM calls."""

    @pytest.fixture
    def lm(self):
        return PydanticAIBackend(model="anthropic:claude-sonnet-4-20250514")

    def test_make_produces_typed_output(self, lm):
        """lm.make should produce an instance of the target type."""
        task = Task(description="Write a hello world program")
        result = lm.make(task, Result)

        assert isinstance(result, Result)
        assert isinstance(result.summary, str)
        assert isinstance(result.steps_taken, list)
        assert len(result.summary) > 0

    def test_decide_picks_from_options(self, lm):
        """lm.decide should pick one of the valid successor types."""
        task = Task(description="Calculate 2 + 2")
        next_node = lm.decide(task)

        # Should be either SubTasks or Result
        assert isinstance(next_node, (SubTasks, Result))

    def test_decide_can_return_none_for_terminal(self, lm):
        """lm.decide should be able to return None for terminal nodes."""
        result = Result(summary="Done", steps_taken=["step 1"])
        next_node = lm.decide(result)

        # Result's only option is None (terminal)
        assert next_node is None

    def test_graph_run_simple(self, lm):
        """Run a simple graph to completion."""
        graph = Graph(start=Question)

        question = Question(text="What is 2 + 2?")
        result = graph.run(question, lm=lm, max_steps=5)

        assert isinstance(result, GraphResult)
        assert result.node is None  # Terminated successfully

    def test_graph_run_task_decomposition(self, lm):
        """Run task decomposition graph."""
        graph = Graph(start=Task)

        task = Task(description="Make a peanut butter sandwich")
        result = graph.run(task, lm=lm, max_steps=10)

        assert isinstance(result, GraphResult)
        assert result.node is None  # Terminated successfully


class TestClaudeCLIBackend:
    """Tests using Claude CLI."""

    @pytest.fixture
    def lm(self):
        return ClaudeCLIBackend(model="claude-sonnet-4-20250514")

    def test_make_produces_typed_output(self, lm):
        """lm.make should produce an instance of the target type."""
        task = Task(description="Add 2+2")
        result = lm.make(task, Result)

        assert isinstance(result, Result)
        assert isinstance(result.summary, str)
        assert isinstance(result.steps_taken, list)

    def test_decide_picks_from_options(self, lm):
        """lm.decide should pick one of the valid successor types."""
        task = Task(description="Calculate 2 + 2")
        next_node = lm.decide(task)

        assert isinstance(next_node, (SubTasks, Result, type(None)))

    def test_graph_run_simple(self, lm):
        """Run a simple graph to completion."""
        graph = Graph(start=Question)

        question = Question(text="What is the capital of France?")
        result = graph.run(question, lm=lm, max_steps=5)

        assert isinstance(result, GraphResult)
        assert result.node is None  # Terminated successfully

    def test_decide_can_return_none_for_terminal(self, lm):
        """lm.decide should be able to return None for terminal nodes."""
        result = Result(summary="Done", steps_taken=["step 1"])
        next_node = lm.decide(result)

        # Result's only option is None (terminal)
        assert next_node is None

    def test_graph_run_task_decomposition(self):
        """Run task decomposition graph."""
        # Use longer timeout for multi-step graph
        lm = ClaudeCLIBackend(model="claude-sonnet-4-20250514", timeout=60)
        graph = Graph(start=Task)

        task = Task(description="Make a peanut butter sandwich")
        result = graph.run(task, lm=lm, max_steps=10)

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
