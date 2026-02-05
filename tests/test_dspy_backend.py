"""TDD tests for DSPyBackend.

Tests the DSPy-based LM backend that uses dspy.Predict with generated Signatures.
"""

import time
from typing import Annotated
from unittest.mock import MagicMock, patch

import dspy
import pytest
from pydantic import BaseModel, ValidationError

from bae.dspy_backend import DSPyBackend
from bae.exceptions import BaeLMError, BaeParseError
from bae.markers import Context, Dep
from bae.node import Node


# Test node classes
class SimpleNode(Node):
    """A simple test node."""

    content: Annotated[str, Context(description="The content to process")]


class TargetNode(Node):
    """Target node for make() tests."""

    result: str
    score: int = 0


class AlternativeNode(Node):
    """Alternative target for decide() tests."""

    option: str


class NodeWithDep(Node):
    """Node with Dep-annotated call param."""

    query: Annotated[str, Context(description="The query")]

    def __call__(
        self,
        lm,
        db: Annotated[str, Dep(description="Database connection")],
    ) -> TargetNode | None:
        ...


class UnionReturnNode(Node):
    """Node with union return type."""

    content: Annotated[str, Context(description="Content to analyze")]

    def __call__(self, lm) -> TargetNode | AlternativeNode | None:
        ...


class SingleReturnNode(Node):
    """Node with single return type (no union)."""

    data: Annotated[str, Context(description="Data to process")]

    def __call__(self, lm) -> TargetNode:
        ...


class TestDSPyBackendMake:
    """Test DSPyBackend.make() using dspy.Predict."""

    def test_make_uses_node_to_signature(self):
        """make() uses node_to_signature to create dspy.Signature."""
        backend = DSPyBackend()
        node = SimpleNode(content="test input")

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            # Create a mock signature class
            mock_sig_class = MagicMock()
            mock_sig.return_value = mock_sig_class

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock()
                mock_predict.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(output='{"result": "test", "score": 5}')

                try:
                    backend.make(node, TargetNode)
                except Exception:
                    pass  # May fail on parse, but we're testing signature call

                mock_sig.assert_called_once_with(TargetNode)

    def test_make_creates_predict_with_signature(self):
        """make() creates dspy.Predict with the generated Signature."""
        backend = DSPyBackend()
        node = SimpleNode(content="test input")

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig_class = MagicMock()
            mock_sig.return_value = mock_sig_class

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock()
                mock_predict.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(output='{"result": "ok", "score": 1}')

                try:
                    backend.make(node, TargetNode)
                except Exception:
                    pass

                mock_predict.assert_called_with(mock_sig_class)

    def test_make_passes_context_fields_as_inputs(self):
        """make() passes Context-annotated fields to predict."""
        backend = DSPyBackend()
        node = SimpleNode(content="my content")

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock()
                mock_predict.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(output='{"result": "x", "score": 0}')

                try:
                    backend.make(node, TargetNode)
                except Exception:
                    pass

                # Check that content was passed
                call_kwargs = mock_predictor.call_args[1]
                assert "content" in call_kwargs
                assert call_kwargs["content"] == "my content"

    def test_make_parses_output_to_pydantic_model(self):
        """make() parses dspy.Predict output into target Pydantic model."""
        backend = DSPyBackend()
        node = SimpleNode(content="input")

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock()
                mock_predict.return_value = mock_predictor
                # Return valid JSON for TargetNode
                mock_predictor.return_value = dspy.Prediction(
                    output='{"result": "parsed correctly", "score": 42}'
                )

                result = backend.make(node, TargetNode)

                assert isinstance(result, TargetNode)
                assert result.result == "parsed correctly"
                assert result.score == 42

    def test_make_retries_on_parse_failure_with_hint(self):
        """make() retries with error hint on parse failure."""
        backend = DSPyBackend()
        node = SimpleNode(content="input")

        call_count = 0

        def mock_call(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: return invalid JSON
                return dspy.Prediction(output="not valid json")
            else:
                # Second call: return valid JSON
                return dspy.Prediction(output='{"result": "fixed", "score": 1}')

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock(side_effect=mock_call)
                mock_predict.return_value = mock_predictor

                result = backend.make(node, TargetNode)

                assert call_count == 2
                assert result.result == "fixed"

    def test_make_raises_bae_parse_error_after_retry_fails(self):
        """make() raises BaeParseError if retry also fails."""
        backend = DSPyBackend()
        node = SimpleNode(content="input")

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock()
                mock_predict.return_value = mock_predictor
                # Both calls return invalid JSON
                mock_predictor.return_value = dspy.Prediction(output="invalid json")

                with pytest.raises(BaeParseError) as exc_info:
                    backend.make(node, TargetNode)

                # Should have original error as cause
                assert exc_info.value.__cause__ is not None


class TestDSPyBackendDecide:
    """Test DSPyBackend.decide() with two-step pattern."""

    def test_decide_returns_none_for_none_choice(self):
        """decide() returns None when LLM picks None."""
        backend = DSPyBackend()
        node = UnionReturnNode(content="test")

        with patch.object(backend, "_predict_choice") as mock_choice:
            mock_choice.return_value = "None"

            result = backend.decide(node)

            assert result is None

    def test_decide_calls_make_for_chosen_type(self):
        """decide() calls make() for the type LLM picks."""
        backend = DSPyBackend()
        node = UnionReturnNode(content="test")

        with patch.object(backend, "_predict_choice") as mock_choice:
            mock_choice.return_value = "TargetNode"

            with patch.object(backend, "make") as mock_make:
                mock_make.return_value = TargetNode(result="from make")

                result = backend.decide(node)

                mock_make.assert_called_once()
                call_args = mock_make.call_args
                assert call_args[0][0] is node
                assert call_args[0][1] is TargetNode

    def test_decide_bypasses_choice_for_single_type(self):
        """decide() skips choice step for single return type."""
        backend = DSPyBackend()
        node = SingleReturnNode(data="test")

        with patch.object(backend, "_predict_choice") as mock_choice:
            with patch.object(backend, "make") as mock_make:
                mock_make.return_value = TargetNode(result="direct")

                result = backend.decide(node)

                # Choice should NOT be called for single type
                mock_choice.assert_not_called()
                mock_make.assert_called_once()

    def test_decide_builds_choice_enum_from_return_types(self):
        """decide() builds choice signature with type names as enum."""
        backend = DSPyBackend()
        node = UnionReturnNode(content="analyze this")

        # We'll capture the choice prediction call
        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                # First predict for choice
                choice_predictor = MagicMock()
                choice_predictor.return_value = dspy.Prediction(choice="AlternativeNode")

                # Second predict for make
                make_predictor = MagicMock()
                make_predictor.return_value = dspy.Prediction(output='{"option": "chosen"}')

                mock_predict.side_effect = [choice_predictor, make_predictor]

                try:
                    result = backend.decide(node)
                except Exception:
                    pass

                # First call should be for choice signature
                first_call = mock_predict.call_args_list[0]
                # The signature should have 'choice' field


class TestDSPyBackendAPIFailures:
    """Test API failure handling with retry."""

    def test_api_timeout_retries_once(self):
        """API timeout triggers single retry."""
        from litellm.exceptions import Timeout

        backend = DSPyBackend()
        node = SimpleNode(content="test")

        call_count = 0

        def mock_call(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Timeout("API timeout")
            return dspy.Prediction(output='{"result": "ok", "score": 1}')

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock(side_effect=mock_call)
                mock_predict.return_value = mock_predictor

                result = backend.make(node, TargetNode)

                assert call_count == 2
                assert result.result == "ok"

    def test_api_rate_limit_retries_once(self):
        """Rate limit triggers single retry."""
        from litellm.exceptions import RateLimitError

        backend = DSPyBackend()
        node = SimpleNode(content="test")

        call_count = 0

        def mock_call(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError(
                    message="Rate limited",
                    llm_provider="test",
                    model="test",
                    response=MagicMock(),
                )
            return dspy.Prediction(output='{"result": "ok", "score": 1}')

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock(side_effect=mock_call)
                mock_predict.return_value = mock_predictor

                result = backend.make(node, TargetNode)

                assert call_count == 2

    def test_api_error_raises_bae_lm_error_after_retry(self):
        """Persistent API error raises BaeLMError after retry."""
        from litellm.exceptions import APIError

        backend = DSPyBackend()
        node = SimpleNode(content="test")

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock()
                mock_predict.return_value = mock_predictor
                mock_predictor.side_effect = APIError(
                    message="Server error",
                    llm_provider="test",
                    model="test",
                    status_code=500,
                )

                with pytest.raises(BaeLMError) as exc_info:
                    backend.make(node, TargetNode)

                # Should have original error as cause
                assert exc_info.value.__cause__ is not None

    def test_api_retry_waits_before_retry(self):
        """API retry waits 1 second before retrying."""
        from litellm.exceptions import Timeout

        backend = DSPyBackend()
        node = SimpleNode(content="test")

        call_times = []

        def mock_call(**kwargs):
            call_times.append(time.time())
            if len(call_times) == 1:
                raise Timeout("API timeout")
            return dspy.Prediction(output='{"result": "ok", "score": 1}')

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock(side_effect=mock_call)
                mock_predict.return_value = mock_predictor

                backend.make(node, TargetNode)

                # Should have waited ~1 second between calls
                assert len(call_times) == 2
                elapsed = call_times[1] - call_times[0]
                assert elapsed >= 0.9  # Allow small timing variance


class TestDSPyBackendDepFields:
    """Test handling of Dep-annotated fields."""

    def test_make_includes_dep_values_in_inputs(self):
        """make() passes Dep field values as inputs."""
        backend = DSPyBackend()
        node = NodeWithDep(query="SELECT *")

        # Simulate deps being passed
        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock()
                mock_predict.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(output='{"result": "ok", "score": 1}')

                # Pass deps via kwargs
                try:
                    backend.make(node, TargetNode, db="postgres://localhost")
                except Exception:
                    pass

                call_kwargs = mock_predictor.call_args[1]
                assert "query" in call_kwargs
                assert call_kwargs["query"] == "SELECT *"
                # db should also be passed if provided
                assert "db" in call_kwargs
                assert call_kwargs["db"] == "postgres://localhost"
