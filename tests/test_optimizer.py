"""Tests for trace-to-example conversion and node transition metric."""

import dspy

from bae.node import Node
from bae.optimizer import trace_to_examples, node_transition_metric


# --- Test Node Types ---


class StartNode(Node):
    """A starting node."""

    request: str


class MiddleNode(Node):
    """An intermediate node."""

    data: str
    count: int


class EndNode(Node):
    """A terminal node."""

    result: str


# --- trace_to_examples Tests ---


class TestTraceToExamplesEmpty:
    """Tests for empty and single-node traces."""

    def test_empty_trace_returns_empty_list(self):
        """Empty trace produces no examples."""
        examples = trace_to_examples([])
        assert examples == []

    def test_single_node_trace_returns_empty_list(self):
        """Single node has no transitions, so no examples."""
        node = StartNode(request="hello")
        examples = trace_to_examples([node])
        assert examples == []


class TestTraceToExamplesTwoNodes:
    """Tests for two-node traces."""

    def test_two_node_trace_produces_one_example(self):
        """Two nodes produce one transition example."""
        start = StartNode(request="do something")
        end = EndNode(result="done")

        examples = trace_to_examples([start, end])

        assert len(examples) == 1

    def test_example_has_input_node_fields(self):
        """Example contains all fields from input node."""
        start = StartNode(request="process this")
        end = EndNode(result="processed")

        examples = trace_to_examples([start, end])
        ex = examples[0]

        assert ex.request == "process this"

    def test_example_has_node_type(self):
        """Example includes the input node's type name."""
        start = StartNode(request="test")
        end = EndNode(result="done")

        examples = trace_to_examples([start, end])
        ex = examples[0]

        assert ex.node_type == "StartNode"

    def test_example_has_next_node_type(self):
        """Example includes the output node's type name as label."""
        start = StartNode(request="test")
        end = EndNode(result="done")

        examples = trace_to_examples([start, end])
        ex = examples[0]

        assert ex.next_node_type == "EndNode"

    def test_example_inputs_marked_correctly(self):
        """Example has input fields marked as inputs via with_inputs()."""
        start = StartNode(request="test")
        end = EndNode(result="done")

        examples = trace_to_examples([start, end])
        ex = examples[0]

        # DSPy Example tracks which fields are inputs
        # The inputs should be the node's fields + node_type
        assert "request" in ex.inputs()
        assert "node_type" in ex.inputs()
        assert "next_node_type" not in ex.inputs()


class TestTraceToExamplesMultiNode:
    """Tests for multi-node traces."""

    def test_three_node_trace_produces_two_examples(self):
        """Three nodes produce two transition examples."""
        start = StartNode(request="begin")
        middle = MiddleNode(data="processing", count=5)
        end = EndNode(result="finished")

        examples = trace_to_examples([start, middle, end])

        assert len(examples) == 2

    def test_first_example_is_first_transition(self):
        """First example is StartNode -> MiddleNode."""
        start = StartNode(request="begin")
        middle = MiddleNode(data="processing", count=5)
        end = EndNode(result="finished")

        examples = trace_to_examples([start, middle, end])
        ex = examples[0]

        assert ex.node_type == "StartNode"
        assert ex.next_node_type == "MiddleNode"
        assert ex.request == "begin"

    def test_second_example_is_second_transition(self):
        """Second example is MiddleNode -> EndNode."""
        start = StartNode(request="begin")
        middle = MiddleNode(data="processing", count=5)
        end = EndNode(result="finished")

        examples = trace_to_examples([start, middle, end])
        ex = examples[1]

        assert ex.node_type == "MiddleNode"
        assert ex.next_node_type == "EndNode"
        assert ex.data == "processing"
        assert ex.count == 5

    def test_multi_field_node_all_fields_included(self):
        """All fields from multi-field node are included in example."""
        middle = MiddleNode(data="test", count=42)
        end = EndNode(result="done")

        examples = trace_to_examples([middle, end])
        ex = examples[0]

        assert ex.data == "test"
        assert ex.count == 42
        assert ex.node_type == "MiddleNode"


# --- node_transition_metric Tests ---


class MockPrediction:
    """Mock prediction object for testing metric."""

    def __init__(self, next_node_type: str | None = None, output: str | None = None):
        if next_node_type is not None:
            self.next_node_type = next_node_type
        if output is not None:
            self.output = output


class TestMetricEvaluationMode:
    """Tests for metric in evaluation mode (trace=None)."""

    def test_exact_match_returns_1(self):
        """Exact type name match returns 1.0."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="EndNode")

        score = node_transition_metric(ex, pred, trace=None)

        assert score == 1.0

    def test_mismatch_returns_0(self):
        """Type mismatch returns 0.0."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="MiddleNode")

        score = node_transition_metric(ex, pred, trace=None)

        assert score == 0.0

    def test_case_insensitive_match(self):
        """Matching is case-insensitive."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="endnode")

        score = node_transition_metric(ex, pred, trace=None)

        assert score == 1.0

    def test_substring_match_predicted_contains_expected(self):
        """Match when predicted contains expected (flexible LLM output)."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="The next node should be EndNode")

        score = node_transition_metric(ex, pred, trace=None)

        assert score == 1.0

    def test_substring_match_expected_contains_predicted(self):
        """Match when expected contains predicted."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="End")

        score = node_transition_metric(ex, pred, trace=None)

        assert score == 1.0

    def test_whitespace_stripped(self):
        """Whitespace is stripped before comparison."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="  EndNode  ")

        score = node_transition_metric(ex, pred, trace=None)

        assert score == 1.0


class TestMetricBootstrapMode:
    """Tests for metric in bootstrap mode (trace is not None)."""

    def test_match_returns_true(self):
        """Match returns True in bootstrap mode."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="EndNode")

        result = node_transition_metric(ex, pred, trace=[])

        assert result is True

    def test_mismatch_returns_false(self):
        """Mismatch returns False in bootstrap mode."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="MiddleNode")

        result = node_transition_metric(ex, pred, trace=[])

        assert result is False

    def test_non_empty_trace_still_returns_bool(self):
        """Any non-None trace triggers bootstrap mode."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="EndNode")

        result = node_transition_metric(ex, pred, trace=["something"])

        assert result is True


class TestMetricOutputAttribute:
    """Tests for metric using pred.output instead of pred.next_node_type."""

    def test_uses_output_attribute_when_no_next_node_type(self):
        """Falls back to pred.output if no next_node_type."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(output="EndNode")

        score = node_transition_metric(ex, pred, trace=None)

        assert score == 1.0

    def test_prefers_next_node_type_over_output(self):
        """Uses next_node_type when both attributes exist."""
        ex = dspy.Example(next_node_type="EndNode")
        pred = MockPrediction(next_node_type="EndNode", output="WrongNode")

        score = node_transition_metric(ex, pred, trace=None)

        assert score == 1.0
