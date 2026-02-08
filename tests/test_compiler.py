"""TDD tests for node_to_signature conversion.

Tests the conversion of bae Node classes to DSPy Signature classes.
"""

import dspy

from bae.node import Node


class TestNodeToSignature:
    """Test node_to_signature() function."""

    def test_class_name_becomes_instruction(self):
        """Case 1: Class name becomes the Signature instruction."""
        from bae.compiler import node_to_signature

        class AnalyzeUserIntent(Node):
            pass

        sig = node_to_signature(AnalyzeUserIntent)
        assert sig.instructions == "AnalyzeUserIntent"

    def test_plain_field_becomes_output_field_on_non_start(self):
        """Case 2: Plain field -> OutputField on non-start node."""
        from bae.compiler import node_to_signature

        class ProcessRequest(Node):
            request: str

        sig = node_to_signature(ProcessRequest)
        assert "request" in sig.output_fields

    def test_all_fields_included_in_signature(self):
        """Case 3: All fields are included in signature (v2 change)."""
        from bae.compiler import node_to_signature

        class ProcessRequest(Node):
            request: str
            internal_counter: int = 0

        sig = node_to_signature(ProcessRequest)
        assert "request" in sig.output_fields
        assert "internal_counter" in sig.output_fields

    def test_multiple_plain_fields(self):
        """Case 4: Multiple plain fields become OutputFields on non-start."""
        from bae.compiler import node_to_signature

        class ChatNode(Node):
            history: str
            user_input: str

        sig = node_to_signature(ChatNode)
        assert "history" in sig.output_fields
        assert "user_input" in sig.output_fields

    def test_no_generic_output_field(self):
        """Case 5: v2 does not add a generic 'output' OutputField.

        The old behavior added output=(str, OutputField()). The new behavior
        creates OutputFields from the node's actual plain fields.
        """
        from bae.compiler import node_to_signature

        class Decider(Node):
            choice: str

        sig = node_to_signature(Decider)
        # No generic "output" field, just the actual field
        assert "output" not in sig.output_fields
        assert "choice" in sig.output_fields

    def test_node_with_internal_field_becomes_output(self):
        """Case 6: Node with internal fields -> they become OutputFields on non-start."""
        from bae.compiler import node_to_signature

        class EmptyNode(Node):
            internal: int = 0

        sig = node_to_signature(EmptyNode)
        assert len(sig.input_fields) == 0
        assert "internal" in sig.output_fields

    def test_result_is_dspy_signature_subclass(self):
        """Case 7: Result is a valid dspy.Signature subclass."""
        from bae.compiler import node_to_signature

        class SomeNode(Node):
            data: str

        sig = node_to_signature(SomeNode)
        assert issubclass(sig, dspy.Signature)


# --- CompiledGraph.run() Integration Tests ---


from unittest.mock import MagicMock, patch
from bae.lm import LM
from bae.result import GraphResult


class RunResultNode(Node):
    """Terminal node for run() tests."""

    result: str

    def __call__(self, lm: LM) -> None:
        ...


class RunStartNode(Node):
    """Starting node for run() tests."""

    text: str

    def __call__(self, lm: LM) -> RunResultNode:
        ...


class TestCompiledGraphRunUsesOptimizedLM:
    """Tests that CompiledGraph.run() uses OptimizedLM."""

    def test_compiled_graph_run_uses_optimized_lm(self):
        """run() creates OptimizedLM from self.optimized dict."""
        from bae.compiler import compile_graph
        from bae.graph import Graph

        graph = Graph(start=RunStartNode)
        compiled = compile_graph(graph)

        # Create a mock optimized predictor
        mock_predictor = MagicMock(spec=dspy.Predict)
        mock_predictor.return_value = dspy.Prediction(output='{"result": "optimized"}')

        # Add it to compiled.optimized
        compiled.optimized[RunResultNode] = mock_predictor

        # Mock Graph.run to verify lm parameter
        with patch.object(
            graph, "run", wraps=graph.run
        ) as mock_run:
            # Patch OptimizedLM at its source module (lazy imported in run())
            with patch("bae.optimized_lm.OptimizedLM") as mock_lm_class:
                mock_lm_instance = MagicMock()
                mock_lm_class.return_value = mock_lm_instance
                # Make the mock graph.run return a valid result
                mock_run.return_value = GraphResult(node=None, trace=[])

                start_node = RunStartNode(text="test input")
                result = compiled.run(start_node)

                # Verify OptimizedLM was created with compiled.optimized
                mock_lm_class.assert_called_once_with(optimized=compiled.optimized)

                # Verify graph.run was called with the OptimizedLM
                mock_run.assert_called_once()
                call_kwargs = mock_run.call_args.kwargs
                assert call_kwargs["lm"] is mock_lm_instance


class TestCompiledGraphRunReturnsGraphResult:
    """Tests that CompiledGraph.run() returns GraphResult."""

    def test_compiled_graph_run_returns_graph_result(self):
        """run() returns GraphResult with final node and trace."""
        from bae.compiler import compile_graph
        from bae.graph import Graph

        graph = Graph(start=RunResultNode)  # Single terminal node
        compiled = compile_graph(graph)

        # No optimized predictors - empty dict
        # Run with a terminal node
        start_node = RunResultNode(result="test")
        result = compiled.run(start_node)

        # Should return GraphResult
        assert isinstance(result, GraphResult)
        assert hasattr(result, "node")
        assert hasattr(result, "trace")

    def test_compiled_graph_run_result_has_trace(self):
        """run() result includes execution trace."""
        from bae.compiler import compile_graph
        from bae.graph import Graph

        graph = Graph(start=RunResultNode)
        compiled = compile_graph(graph)

        start_node = RunResultNode(result="traced")
        result = compiled.run(start_node)

        # Trace should contain the start node
        assert len(result.trace) >= 1
        assert result.trace[0] is start_node


class TestCreateOptimizedLmFactory:
    """Tests for create_optimized_lm() factory function."""

    def test_create_optimized_lm_loads_predictors(self, tmp_path):
        """create_optimized_lm() loads predictors from disk."""
        from bae.compiler import create_optimized_lm, compile_graph
        from bae.graph import Graph
        from bae.optimizer import save_optimized

        # Create a graph and save optimized predictors
        graph = Graph(start=RunResultNode)
        compiled = compile_graph(graph)

        # Create signature and predictor
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        predictor = dspy.Predict(sig)
        save_optimized({RunResultNode: predictor}, tmp_path)

        # Call the factory
        lm = create_optimized_lm(graph, tmp_path)

        # Verify it's an OptimizedLM with loaded predictors
        from bae.optimized_lm import OptimizedLM

        assert isinstance(lm, OptimizedLM)
        assert RunResultNode in lm.optimized

    def test_create_optimized_lm_handles_missing_files(self, tmp_path):
        """create_optimized_lm() handles missing predictor files gracefully."""
        from bae.compiler import create_optimized_lm
        from bae.graph import Graph

        # Create empty directory (no predictor files)
        tmp_path.mkdir(exist_ok=True)

        graph = Graph(start=RunResultNode)

        # Should not raise - creates fresh predictors
        lm = create_optimized_lm(graph, tmp_path)

        # Should have predictor (fresh one) for the node
        from bae.optimized_lm import OptimizedLM

        assert isinstance(lm, OptimizedLM)
        assert RunResultNode in lm.optimized

    def test_create_optimized_lm_accepts_string_path(self, tmp_path):
        """create_optimized_lm() accepts string path."""
        from bae.compiler import create_optimized_lm
        from bae.graph import Graph
        from bae.optimizer import save_optimized

        graph = Graph(start=RunResultNode)

        # Create signature and predictor
        sig = dspy.make_signature(
            {"input": (str, dspy.InputField()), "output": (str, dspy.OutputField())},
            "Test",
        )
        predictor = dspy.Predict(sig)
        save_optimized({RunResultNode: predictor}, tmp_path)

        # Pass string path instead of Path object
        lm = create_optimized_lm(graph, str(tmp_path))

        from bae.optimized_lm import OptimizedLM

        assert isinstance(lm, OptimizedLM)
