"""Tests for Node base class."""

from bae.node import Node
from bae.lm import LM


# Mock LM for testing
class MockLM:
    """Mock LM that returns predefined nodes."""

    def __init__(self, return_value: Node | None = None):
        self.return_value = return_value
        self.calls: list[Node] = []

    def make(self, node: Node, target: type) -> Node:
        self.calls.append(node)
        return self.return_value

    def decide(self, node: Node) -> Node | None:
        self.calls.append(node)
        return self.return_value


class Start(Node):
    """Starting node."""
    query: str

    def __call__(self, lm: LM) -> Process | Clarify:
        if "unclear" in self.query:
            return lm.make(self, Clarify)
        return lm.make(self, Process)


class Clarify(Node):
    """Ask for clarification."""
    question: str


class Process(Node):
    """Process the task."""
    task: str

    def __call__(self, lm: LM) -> Review | None:
        return lm.decide(self)


class Review(Node):
    """Review the result."""
    content: str

    def __call__(self, lm: LM) -> Process | None:
        return lm.decide(self)


class TestNodeTopology:
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
    def test_call_with_lm_make(self):
        """Node can use lm.make to produce specific type."""
        expected = Process(task="do it")
        lm = MockLM(return_value=expected)

        start = Start(query="test")
        result = start(lm=lm)

        assert result is expected
        assert lm.calls == [start]

    def test_call_branches_on_condition(self):
        """Node can branch based on its own state."""
        clarify = Clarify(question="what?")
        lm = MockLM(return_value=clarify)

        start = Start(query="unclear request")
        result = start(lm=lm)

        assert result is clarify

    def test_call_with_lm_decide(self):
        """Node can use lm.decide to let LLM choose."""
        review = Review(content="looks good")
        lm = MockLM(return_value=review)

        process = Process(task="test")
        result = process(lm=lm)

        assert result is review
        assert lm.calls == [process]
