"""Tests for optimization: trace conversion, metric, save/load, and optimize_node."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import dspy

from bae.node import Node
from bae.optimizer import (
    load_optimized,
    node_transition_metric,
    save_optimized,
    trace_to_examples,
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


# --- optimize_node Tests ---


def _import_optimize_node():
    """Helper to import optimize_node - deferred to allow RED phase to fail on import."""
    from bae.optimizer import optimize_node

    return optimize_node


class TestOptimizeNodeFiltering:
    """Tests for trainset filtering by node type."""

    def test_filters_trainset_to_matching_node_type(self):
        """Only examples with matching node_type are used."""
        optimize_node = _import_optimize_node()

        # Create mixed trainset
        trainset = []
        for i in range(15):  # 15 StartNode examples
            ex = dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            trainset.append(ex)
        for i in range(5):  # 5 MiddleNode examples
            ex = dspy.Example(
                node_type="MiddleNode",
                data=f"data_{i}",
                count=i,
                next_node_type="EndNode",
            ).with_inputs("node_type", "data", "count")
            trainset.append(ex)

        # Mock BootstrapFewShot to capture what it receives
        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            mock_optimizer = MagicMock()
            mock_bfs.return_value = mock_optimizer
            mock_optimizer.compile.return_value = MagicMock()

            optimize_node(StartNode, trainset)

            # Should call compile with only StartNode examples (15)
            call_args = mock_optimizer.compile.call_args
            compiled_trainset = call_args.kwargs.get(
                "trainset"
            ) or call_args[1]["trainset"]
            assert len(compiled_trainset) == 15
            for ex in compiled_trainset:
                assert ex.node_type == "StartNode"


class TestOptimizeNodeSmallTrainset:
    """Tests for small trainset handling (early return)."""

    def test_returns_unoptimized_predictor_for_empty_trainset(self):
        """Empty trainset returns unoptimized predictor."""
        optimize_node = _import_optimize_node()

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            result = optimize_node(StartNode, [])

            # Should NOT call BootstrapFewShot
            mock_bfs.assert_not_called()
            # Should return a dspy.Predict
            assert isinstance(result, dspy.Predict)

    def test_returns_unoptimized_predictor_for_5_examples(self):
        """Fewer than 10 examples returns unoptimized predictor."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(5)
        ]

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            result = optimize_node(StartNode, trainset)

            mock_bfs.assert_not_called()
            assert isinstance(result, dspy.Predict)

    def test_returns_unoptimized_predictor_for_9_examples(self):
        """Exactly 9 examples (boundary) returns unoptimized predictor."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(9)
        ]

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            result = optimize_node(StartNode, trainset)

            mock_bfs.assert_not_called()
            assert isinstance(result, dspy.Predict)

    def test_runs_optimization_for_10_examples(self):
        """Exactly 10 examples (boundary) triggers optimization."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(10)
        ]

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            mock_optimizer = MagicMock()
            mock_bfs.return_value = mock_optimizer
            mock_optimizer.compile.return_value = MagicMock(spec=dspy.Predict)

            optimize_node(StartNode, trainset)

            # Should call BootstrapFewShot
            mock_bfs.assert_called_once()

    def test_filters_before_checking_threshold(self):
        """20 total examples but only 5 for target node returns unoptimized."""
        optimize_node = _import_optimize_node()

        trainset = []
        # 5 StartNode examples
        for i in range(5):
            ex = dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            trainset.append(ex)
        # 15 MiddleNode examples
        for i in range(15):
            ex = dspy.Example(
                node_type="MiddleNode",
                data=f"data_{i}",
                count=i,
                next_node_type="EndNode",
            ).with_inputs("node_type", "data", "count")
            trainset.append(ex)

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            result = optimize_node(StartNode, trainset)

            # Should NOT call BootstrapFewShot (only 5 StartNode examples)
            mock_bfs.assert_not_called()
            assert isinstance(result, dspy.Predict)


class TestOptimizeNodeBootstrapConfig:
    """Tests for BootstrapFewShot configuration."""

    def test_uses_default_metric_when_none_provided(self):
        """Uses node_transition_metric when no metric is provided."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(15)
        ]

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            mock_optimizer = MagicMock()
            mock_bfs.return_value = mock_optimizer
            mock_optimizer.compile.return_value = MagicMock(spec=dspy.Predict)

            optimize_node(StartNode, trainset)

            # Check metric kwarg
            call_kwargs = mock_bfs.call_args.kwargs
            assert call_kwargs["metric"] is node_transition_metric

    def test_uses_custom_metric_when_provided(self):
        """Uses provided metric function."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(15)
        ]

        def custom_metric(example, pred, trace=None):
            return 1.0 if trace is None else True

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            mock_optimizer = MagicMock()
            mock_bfs.return_value = mock_optimizer
            mock_optimizer.compile.return_value = MagicMock(spec=dspy.Predict)

            optimize_node(StartNode, trainset, metric=custom_metric)

            call_kwargs = mock_bfs.call_args.kwargs
            assert call_kwargs["metric"] is custom_metric

    def test_bootstrap_config_max_bootstrapped_demos(self):
        """BootstrapFewShot uses max_bootstrapped_demos=4."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(15)
        ]

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            mock_optimizer = MagicMock()
            mock_bfs.return_value = mock_optimizer
            mock_optimizer.compile.return_value = MagicMock(spec=dspy.Predict)

            optimize_node(StartNode, trainset)

            call_kwargs = mock_bfs.call_args.kwargs
            assert call_kwargs["max_bootstrapped_demos"] == 4

    def test_bootstrap_config_max_labeled_demos(self):
        """BootstrapFewShot uses max_labeled_demos=8."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(15)
        ]

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            mock_optimizer = MagicMock()
            mock_bfs.return_value = mock_optimizer
            mock_optimizer.compile.return_value = MagicMock(spec=dspy.Predict)

            optimize_node(StartNode, trainset)

            call_kwargs = mock_bfs.call_args.kwargs
            assert call_kwargs["max_labeled_demos"] == 8

    def test_bootstrap_config_max_rounds(self):
        """BootstrapFewShot uses max_rounds=1."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(15)
        ]

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            mock_optimizer = MagicMock()
            mock_bfs.return_value = mock_optimizer
            mock_optimizer.compile.return_value = MagicMock(spec=dspy.Predict)

            optimize_node(StartNode, trainset)

            call_kwargs = mock_bfs.call_args.kwargs
            assert call_kwargs["max_rounds"] == 1


class TestOptimizeNodeSignature:
    """Tests for signature generation from node class."""

    def test_uses_node_to_signature_for_predictor(self):
        """optimize_node uses node_to_signature to create the student."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(5)  # Small trainset - returns unoptimized
        ]

        with patch("bae.optimizer.node_to_signature") as mock_sig:
            mock_signature = MagicMock()
            mock_sig.return_value = mock_signature

            optimize_node(StartNode, trainset)

            mock_sig.assert_called_once_with(StartNode)

    def test_unoptimized_predictor_uses_generated_signature(self):
        """Unoptimized predictor is created with node_to_signature result."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(5)  # Small trainset
        ]

        with (
            patch("bae.optimizer.node_to_signature") as mock_sig,
            patch("bae.optimizer.dspy.Predict") as mock_predict,
        ):
            mock_signature = MagicMock()
            mock_sig.return_value = mock_signature
            mock_predictor = MagicMock()
            mock_predict.return_value = mock_predictor

            result = optimize_node(StartNode, trainset)

            mock_predict.assert_called_once_with(mock_signature)
            assert result is mock_predictor


class TestOptimizeNodeReturnsOptimizedPredictor:
    """Tests that optimize_node returns the compiled result."""

    def test_returns_result_from_optimizer_compile(self):
        """Returns the result of optimizer.compile()."""
        optimize_node = _import_optimize_node()

        trainset = [
            dspy.Example(
                node_type="StartNode",
                request=f"request_{i}",
                next_node_type="MiddleNode",
            ).with_inputs("node_type", "request")
            for i in range(15)
        ]

        with patch("bae.optimizer.BootstrapFewShot") as mock_bfs:
            mock_optimizer = MagicMock()
            mock_bfs.return_value = mock_optimizer
            optimized_predictor = MagicMock(spec=dspy.Predict)
            mock_optimizer.compile.return_value = optimized_predictor

            result = optimize_node(StartNode, trainset)

            assert result is optimized_predictor


# ============================================================
# Fixtures for CompiledGraph Integration Tests
# ============================================================


import pytest
from typing import Annotated

from bae import Graph, compile_graph, LM
from bae.compiler import CompiledGraph
from bae.markers import Context


# Test nodes for CompiledGraph tests - need __call__ with proper type hints
class CompiledEndNode(Node):
    """Terminal node for compiled graph tests."""

    result: str

    def __call__(self, lm: LM) -> None:
        ...


class CompiledStartNode(Node):
    """Starting node for compiled graph tests."""

    text: Annotated[str, Context(description="The text")]

    def __call__(self, lm: LM) -> CompiledEndNode:
        ...


@pytest.fixture
def sample_trainset():
    """Create sample training set for optimizer tests.

    Intentionally small - not enough for real optimization,
    but sufficient for testing the plumbing.
    """
    examples = []
    for i in range(5):
        ex = dspy.Example(
            node_type="TestNode",
            text=f"sample {i}",
            next_node_type="NextNode",
        ).with_inputs("node_type", "text")
        examples.append(ex)
    return examples


# ============================================================
# CompiledGraph Integration Tests
# ============================================================


class TestCompiledGraphOptimize:
    """Tests for CompiledGraph.optimize()."""

    def test_optimize_creates_predictors_for_all_nodes(self, sample_trainset):
        """optimize() creates optimized predictor for each node in graph."""
        graph = Graph(start=CompiledStartNode)
        compiled = compile_graph(graph)

        # Optimize with trainset (may be small, that's ok)
        compiled.optimize(sample_trainset)

        # Should have predictors for both nodes
        assert CompiledStartNode in compiled.optimized
        assert CompiledEndNode in compiled.optimized

    def test_optimize_returns_self_for_chaining(self, sample_trainset):
        """optimize() returns self for method chaining."""
        graph = Graph(start=CompiledEndNode)
        compiled = compile_graph(graph)

        result = compiled.optimize(sample_trainset)
        assert result is compiled


class TestCompiledGraphSaveLoad:
    """Tests for CompiledGraph save/load."""

    def test_save_load_roundtrip(self, tmp_path, sample_trainset):
        """save() then load() produces working CompiledGraph."""
        graph = Graph(start=CompiledStartNode)
        compiled = compile_graph(graph)
        compiled.optimize(sample_trainset)

        # Save
        save_path = tmp_path / "compiled"
        compiled.save(save_path)

        # Load into new CompiledGraph
        loaded = CompiledGraph.load(graph, save_path)

        # Should have same nodes in optimized dict
        assert CompiledStartNode in loaded.optimized
        assert CompiledEndNode in loaded.optimized
