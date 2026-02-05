"""TDD tests for OptimizedLM backend.

Tests the optimized LM backend that uses pre-loaded predictors when available,
with graceful fallback to naive (fresh) predictors.
"""

from typing import Annotated
from unittest.mock import MagicMock, patch

import dspy
import pytest

from bae.markers import Context
from bae.node import Node


# Test node classes
class OptimizedNode(Node):
    """A node with optimization available."""

    content: Annotated[str, Context(description="The content")]


class UnoptimizedNode(Node):
    """A node without optimization."""

    data: Annotated[str, Context(description="The data")]


class ResultNode(Node):
    """Target node for make() tests."""

    result: str
    score: int = 0


class TestOptimizedLMPredicatorSelection:
    """Test that OptimizedLM selects the correct predictor."""

    def test_uses_optimized_predictor_when_available(self):
        """OptimizedLM uses pre-loaded predictor when target in optimized dict."""
        from bae.optimized_lm import OptimizedLM

        # Create an optimized predictor mock
        optimized_predictor = MagicMock(spec=dspy.Predict)
        optimized_predictor.return_value = dspy.Prediction(
            output='{"result": "from optimized", "score": 10}'
        )

        # Create OptimizedLM with pre-loaded predictor
        backend = OptimizedLM(optimized={ResultNode: optimized_predictor})

        # Get predictor for target
        predictor = backend._get_predictor_for_target(ResultNode)

        # Should return the optimized predictor
        assert predictor is optimized_predictor
        assert backend.stats["optimized"] == 1
        assert backend.stats["naive"] == 0

    def test_falls_back_to_naive_when_not_available(self):
        """OptimizedLM creates fresh predictor when target not in optimized dict."""
        from bae.optimized_lm import OptimizedLM

        # Create OptimizedLM with no optimized predictor for ResultNode
        backend = OptimizedLM(optimized={})

        with patch("bae.optimized_lm.node_to_signature") as mock_sig:
            mock_sig_class = MagicMock()
            mock_sig.return_value = mock_sig_class

            with patch("dspy.Predict") as mock_predict:
                fresh_predictor = MagicMock()
                mock_predict.return_value = fresh_predictor

                predictor = backend._get_predictor_for_target(ResultNode)

                # Should have created fresh predictor
                mock_sig.assert_called_once_with(ResultNode)
                mock_predict.assert_called_once_with(mock_sig_class)
                assert predictor is fresh_predictor
                assert backend.stats["naive"] == 1
                assert backend.stats["optimized"] == 0


class TestOptimizedLMStats:
    """Test usage statistics tracking."""

    def test_stats_track_optimized_calls(self):
        """get_stats() returns accurate count of optimized predictor uses."""
        from bae.optimized_lm import OptimizedLM

        optimized_predictor = MagicMock(spec=dspy.Predict)
        backend = OptimizedLM(optimized={ResultNode: optimized_predictor})

        # Multiple calls to get optimized predictor
        backend._get_predictor_for_target(ResultNode)
        backend._get_predictor_for_target(ResultNode)
        backend._get_predictor_for_target(ResultNode)

        stats = backend.get_stats()
        assert stats["optimized"] == 3
        assert stats["naive"] == 0

    def test_stats_track_naive_calls(self):
        """get_stats() returns accurate count of naive predictor uses."""
        from bae.optimized_lm import OptimizedLM

        backend = OptimizedLM(optimized={})

        with patch("bae.optimized_lm.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()
            with patch("dspy.Predict"):
                # Multiple calls for unoptimized targets
                backend._get_predictor_for_target(ResultNode)
                backend._get_predictor_for_target(OptimizedNode)

        stats = backend.get_stats()
        assert stats["naive"] == 2
        assert stats["optimized"] == 0

    def test_mixed_optimized_and_naive_in_same_session(self):
        """Stats track both optimized and naive calls correctly."""
        from bae.optimized_lm import OptimizedLM

        optimized_predictor = MagicMock(spec=dspy.Predict)
        backend = OptimizedLM(optimized={ResultNode: optimized_predictor})

        with patch("bae.optimized_lm.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()
            with patch("dspy.Predict"):
                # Mix of optimized and naive
                backend._get_predictor_for_target(ResultNode)  # optimized
                backend._get_predictor_for_target(OptimizedNode)  # naive
                backend._get_predictor_for_target(ResultNode)  # optimized
                backend._get_predictor_for_target(UnoptimizedNode)  # naive

        stats = backend.get_stats()
        assert stats["optimized"] == 2
        assert stats["naive"] == 2

    def test_get_stats_returns_copy(self):
        """get_stats() returns a copy, not the internal dict."""
        from bae.optimized_lm import OptimizedLM

        backend = OptimizedLM(optimized={})
        stats = backend.get_stats()

        # Modifying returned dict shouldn't affect internal state
        stats["optimized"] = 999

        assert backend.get_stats()["optimized"] == 0


class TestOptimizedLMMake:
    """Test OptimizedLM.make() override."""

    def test_make_uses_optimized_predictor(self):
        """make() uses pre-loaded predictor when available."""
        from bae.optimized_lm import OptimizedLM

        optimized_predictor = MagicMock(spec=dspy.Predict)
        optimized_predictor.return_value = dspy.Prediction(
            output='{"result": "optimized output", "score": 42}'
        )

        backend = OptimizedLM(optimized={ResultNode: optimized_predictor})
        node = OptimizedNode(content="test input")

        result = backend.make(node, ResultNode)

        # Should use optimized predictor
        assert isinstance(result, ResultNode)
        assert result.result == "optimized output"
        assert result.score == 42
        optimized_predictor.assert_called()
        assert backend.stats["optimized"] == 1

    def test_make_falls_back_to_naive(self):
        """make() creates fresh predictor when target not in optimized dict."""
        from bae.optimized_lm import OptimizedLM

        backend = OptimizedLM(optimized={})
        node = OptimizedNode(content="test input")

        with patch("bae.optimized_lm.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict:
                mock_predictor = MagicMock()
                mock_predict.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(
                    output='{"result": "naive output", "score": 1}'
                )

                result = backend.make(node, ResultNode)

                assert isinstance(result, ResultNode)
                assert result.result == "naive output"
                assert backend.stats["naive"] == 1

    def test_preserves_retry_behavior_on_parse_error(self):
        """make() retries with error hint on parse failure (DSPyBackend behavior)."""
        from bae.exceptions import BaeParseError
        from bae.optimized_lm import OptimizedLM

        call_count = 0

        def mock_call(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return dspy.Prediction(output="not valid json")
            return dspy.Prediction(output='{"result": "fixed", "score": 1}')

        optimized_predictor = MagicMock(side_effect=mock_call)

        backend = OptimizedLM(
            optimized={ResultNode: optimized_predictor},
            max_retries=1,
        )
        node = OptimizedNode(content="test")

        result = backend.make(node, ResultNode)

        # Should have retried
        assert call_count == 2
        assert result.result == "fixed"

    def test_raises_bae_parse_error_after_retry_exhausted(self):
        """make() raises BaeParseError if retry also fails."""
        from bae.exceptions import BaeParseError
        from bae.optimized_lm import OptimizedLM

        optimized_predictor = MagicMock()
        optimized_predictor.return_value = dspy.Prediction(output="invalid json")

        backend = OptimizedLM(
            optimized={ResultNode: optimized_predictor},
            max_retries=1,
        )
        node = OptimizedNode(content="test")

        with pytest.raises(BaeParseError):
            backend.make(node, ResultNode)


class TestOptimizedLMEmptyOptimized:
    """Test behavior with empty optimized dict."""

    def test_empty_optimized_dict_uses_all_naive(self):
        """With no optimized predictors, all calls use naive."""
        from bae.optimized_lm import OptimizedLM

        backend = OptimizedLM(optimized={})

        with patch("bae.optimized_lm.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()
            with patch("dspy.Predict"):
                backend._get_predictor_for_target(ResultNode)
                backend._get_predictor_for_target(OptimizedNode)
                backend._get_predictor_for_target(UnoptimizedNode)

        assert backend.stats["naive"] == 3
        assert backend.stats["optimized"] == 0

    def test_none_optimized_same_as_empty(self):
        """Passing None for optimized is same as empty dict."""
        from bae.optimized_lm import OptimizedLM

        backend = OptimizedLM(optimized=None)

        with patch("bae.optimized_lm.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()
            with patch("dspy.Predict"):
                backend._get_predictor_for_target(ResultNode)

        assert backend.stats["naive"] == 1
        assert backend.optimized == {}


class TestOptimizedLMInheritance:
    """Test that OptimizedLM properly inherits from DSPyBackend."""

    def test_inherits_from_dspy_backend(self):
        """OptimizedLM is a subclass of DSPyBackend."""
        from bae.dspy_backend import DSPyBackend
        from bae.optimized_lm import OptimizedLM

        assert issubclass(OptimizedLM, DSPyBackend)

    def test_has_max_retries_from_parent(self):
        """OptimizedLM inherits max_retries from DSPyBackend."""
        from bae.optimized_lm import OptimizedLM

        backend = OptimizedLM(optimized={}, max_retries=3)
        assert backend.max_retries == 3

    def test_decide_inherits_from_parent(self):
        """decide() is inherited from DSPyBackend and uses our make()."""
        from bae.optimized_lm import OptimizedLM

        optimized_predictor = MagicMock(spec=dspy.Predict)
        optimized_predictor.return_value = dspy.Prediction(
            output='{"result": "from decide", "score": 5}'
        )

        backend = OptimizedLM(optimized={ResultNode: optimized_predictor})

        # Create a node that returns single type
        class SingleReturnNode(Node):
            data: Annotated[str, Context(description="data")]

            def __call__(self, lm) -> ResultNode:
                ...

        node = SingleReturnNode(data="test")

        result = backend.decide(node)

        # Should use our make() which uses optimized predictor
        assert isinstance(result, ResultNode)
        assert backend.stats["optimized"] == 1
