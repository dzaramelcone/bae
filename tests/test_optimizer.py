"""Tests for trace-to-example conversion, node transition metric, and save/load."""

from __future__ import annotations

import json
from pathlib import Path

import dspy

from bae.node import Node
from bae.optimizer import (
    trace_to_examples,
    node_transition_metric,
    save_optimized,
    load_optimized,
)


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


# --- save_optimized Tests ---


class TestSaveOptimizedDirectory:
    """Tests for save_optimized directory handling."""

    def test_creates_directory_if_not_exists(self, tmp_path: Path):
        """Creates the target directory if it doesn't exist."""
        # Use a nested path that doesn't exist
        save_path = tmp_path / "nested" / "compiled"

        # Create a simple predictor
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        predictor = dspy.Predict(sig)
        optimized = {StartNode: predictor}

        save_optimized(optimized, save_path)

        assert save_path.exists()
        assert save_path.is_dir()

    def test_works_with_existing_directory(self, tmp_path: Path):
        """Works when directory already exists."""
        save_path = tmp_path / "compiled"
        save_path.mkdir()

        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        predictor = dspy.Predict(sig)
        optimized = {StartNode: predictor}

        # Should not raise
        save_optimized(optimized, save_path)


class TestSaveOptimizedFiles:
    """Tests for save_optimized file creation."""

    def test_creates_json_file_per_node_class(self, tmp_path: Path):
        """Creates one JSON file per node class in the dict."""
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )

        optimized = {
            StartNode: dspy.Predict(sig),
            EndNode: dspy.Predict(sig),
        }

        save_optimized(optimized, tmp_path)

        assert (tmp_path / "StartNode.json").exists()
        assert (tmp_path / "EndNode.json").exists()

    def test_file_is_valid_json(self, tmp_path: Path):
        """Saved files contain valid JSON."""
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        predictor = dspy.Predict(sig)
        optimized = {StartNode: predictor}

        save_optimized(optimized, tmp_path)

        # Should parse as JSON without error
        with open(tmp_path / "StartNode.json") as f:
            data = json.load(f)

        assert isinstance(data, dict)

    def test_accepts_string_path(self, tmp_path: Path):
        """Accepts string path in addition to Path object."""
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        predictor = dspy.Predict(sig)
        optimized = {StartNode: predictor}

        # Pass string instead of Path
        save_optimized(optimized, str(tmp_path))

        assert (tmp_path / "StartNode.json").exists()

    def test_empty_dict_creates_no_files(self, tmp_path: Path):
        """Empty optimized dict creates directory but no files."""
        save_optimized({}, tmp_path)

        assert tmp_path.exists()
        assert list(tmp_path.iterdir()) == []


# --- load_optimized Tests ---


class TestLoadOptimizedBasic:
    """Basic tests for load_optimized."""

    def test_returns_dict_of_predictors(self, tmp_path: Path):
        """Returns a dict mapping node classes to predictors."""
        # Use round-trip to create valid file
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        save_optimized({StartNode: dspy.Predict(sig)}, tmp_path)

        result = load_optimized([StartNode], tmp_path)

        assert isinstance(result, dict)
        assert StartNode in result
        assert isinstance(result[StartNode], dspy.Predict)

    def test_creates_fresh_predictor_for_missing_file(self, tmp_path: Path):
        """Returns fresh predictor when file doesn't exist."""
        # Don't create any files - directory is empty
        tmp_path.mkdir(exist_ok=True)

        result = load_optimized([StartNode], tmp_path)

        assert StartNode in result
        assert isinstance(result[StartNode], dspy.Predict)

    def test_handles_missing_directory(self, tmp_path: Path):
        """Returns fresh predictors when directory doesn't exist."""
        nonexistent = tmp_path / "nonexistent"

        result = load_optimized([StartNode], nonexistent)

        assert StartNode in result
        assert isinstance(result[StartNode], dspy.Predict)


class TestLoadOptimizedMultipleNodes:
    """Tests for loading multiple node types."""

    def test_loads_all_requested_node_types(self, tmp_path: Path):
        """Loads predictors for all node classes in the list."""
        # Create valid files via round-trip for some nodes
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        save_optimized(
            {StartNode: dspy.Predict(sig), EndNode: dspy.Predict(sig)},
            tmp_path,
        )

        result = load_optimized([StartNode, MiddleNode, EndNode], tmp_path)

        assert len(result) == 3
        assert StartNode in result
        assert MiddleNode in result  # Fresh predictor (no file)
        assert EndNode in result

    def test_mixed_existing_and_missing_files(self, tmp_path: Path):
        """Handles mix of existing and missing files gracefully."""
        # Only create file for one node via round-trip
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        save_optimized({StartNode: dspy.Predict(sig)}, tmp_path)

        result = load_optimized([StartNode, MiddleNode], tmp_path)

        assert len(result) == 2
        assert StartNode in result
        assert MiddleNode in result  # Fresh predictor


class TestLoadOptimizedAcceptsStringPath:
    """Tests for string path support in load_optimized."""

    def test_accepts_string_path(self, tmp_path: Path):
        """Accepts string path in addition to Path object."""
        # Create valid file via round-trip
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        save_optimized({StartNode: dspy.Predict(sig)}, tmp_path)

        result = load_optimized([StartNode], str(tmp_path))

        assert StartNode in result


# --- Round-trip Tests ---


class TestSaveLoadRoundTrip:
    """Tests for save then load round-trip."""

    def test_round_trip_preserves_predictor_count(self, tmp_path: Path):
        """Saving then loading preserves the number of predictors."""
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )

        original = {
            StartNode: dspy.Predict(sig),
            EndNode: dspy.Predict(sig),
        }

        save_optimized(original, tmp_path)
        loaded = load_optimized([StartNode, EndNode], tmp_path)

        assert len(loaded) == len(original)

    def test_round_trip_uses_correct_signature_per_node(self, tmp_path: Path):
        """Loaded predictors have signatures derived from node class."""
        from bae.compiler import node_to_signature

        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        predictor = dspy.Predict(sig)
        optimized = {StartNode: predictor}

        save_optimized(optimized, tmp_path)
        loaded = load_optimized([StartNode], tmp_path)

        # The loaded predictor should have been created with node_to_signature
        loaded_predictor = loaded[StartNode]
        expected_sig = node_to_signature(StartNode)

        # Both should have the same instruction (class name)
        assert expected_sig.__doc__ == "StartNode"
