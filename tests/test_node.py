"""Tests for Node base class."""

from bae.node import Node


class Start(Node):
    """Starting node - no predecessor."""
    query: str
    intent: str = ""

    def __call__(self, prev: None) -> "Process | Clarify":
        if self.intent == "unclear":
            return Clarify(question="What do you mean?")
        return Process(task=self.intent)


class Clarify(Node):
    """Ask for clarification."""
    question: str
    answer: str = ""

    def __call__(self, prev: Start) -> Start:
        return Start(query=f"{prev.query} - {self.answer}")


class Process(Node):
    """Process the task."""
    task: str
    result: str = ""

    def __call__(self, prev: Start) -> "Review | None":
        if len(self.result) > 100:
            return Review(content=self.result)
        return None


class Review(Node):
    """Review the result."""
    content: str
    approved: bool = False
    feedback: str = ""

    def __call__(self, prev: Process) -> Process | None:
        if self.approved:
            return None
        return Process(task=f"Fix: {self.feedback}")


class TestNodeFields:
    def test_input_fields(self):
        inputs = Start.input_fields()
        assert "query" in inputs
        assert "intent" not in inputs

    def test_output_fields(self):
        outputs = Start.output_fields()
        assert "intent" in outputs
        assert "query" not in outputs


class TestNodeTopology:
    def test_predecessors_none(self):
        """Start node has no predecessors (prev: None)."""
        preds = Start.predecessors()
        assert preds == set()

    def test_predecessors_single(self):
        """Clarify expects Start as predecessor."""
        preds = Clarify.predecessors()
        assert preds == {Start}

    def test_successors_union(self):
        """Start can go to Process or Clarify."""
        succs = Start.successors()
        assert succs == {Process, Clarify}

    def test_successors_with_none(self):
        """Process can go to Review or terminate."""
        succs = Process.successors()
        assert succs == {Review}

    def test_successors_loop(self):
        """Review can loop back to Process or terminate."""
        succs = Review.successors()
        assert succs == {Process}

    def test_is_terminal_true(self):
        """Process can terminate."""
        assert Process.is_terminal() is True

    def test_is_terminal_false(self):
        """Start cannot terminate."""
        assert Start.is_terminal() is False


class TestNodeCall:
    def test_call_returns_next_node(self):
        start = Start(query="test", intent="do something")
        next_node = start(prev=None)

        assert isinstance(next_node, Process)
        assert next_node.task == "do something"

    def test_call_returns_different_branch(self):
        start = Start(query="test", intent="unclear")
        next_node = start(prev=None)

        assert isinstance(next_node, Clarify)
        assert next_node.question == "What do you mean?"

    def test_call_returns_none_terminal(self):
        process = Process(task="test", result="short")
        next_node = process(prev=Start(query="q", intent="i"))

        assert next_node is None
