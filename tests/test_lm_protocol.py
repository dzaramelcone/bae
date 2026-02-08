"""TDD tests for LM Protocol choose_type/fill methods.

Tests choose_type() and fill() on all three backends:
- DSPyBackend
- PydanticAIBackend
- ClaudeCLIBackend

Uses mocks to avoid real LLM calls.
"""

from __future__ import annotations

from typing import Annotated
from unittest.mock import MagicMock, patch

import dspy
import pytest

from bae.dspy_backend import DSPyBackend
from bae.lm import ClaudeCLIBackend, LM, PydanticAIBackend
from bae.markers import Dep, Recall
from bae.node import Node


# ── Test node types ──────────────────────────────────────────────────────


class Greet(Node):
    """Generate a greeting message."""

    name: str
    greeting: str = ""


class Farewell(Node):
    """Generate a farewell message."""

    name: str
    farewell: str = ""


class Summarize(Node):
    """Summarize content."""

    content: str
    summary: str = ""


def fetch_data() -> str:
    return "fetched"


class WithDeps(Node):
    """Node with dep and recall fields."""

    data: Annotated[str, Dep(fetch_data)]
    prev: Annotated[str, Recall()]
    output: str = ""


# ── LM Protocol shape ───────────────────────────────────────────────────


class TestLMProtocol:
    """LM Protocol defines choose_type and fill."""

    def test_protocol_has_choose_type(self):
        """LM Protocol has a choose_type method."""
        assert hasattr(LM, "choose_type")

    def test_protocol_has_fill(self):
        """LM Protocol has a fill method."""
        assert hasattr(LM, "fill")

    def test_protocol_still_has_make(self):
        """LM Protocol still has make (backward compat)."""
        assert hasattr(LM, "make")

    def test_protocol_still_has_decide(self):
        """LM Protocol still has decide (backward compat)."""
        assert hasattr(LM, "decide")


# ── DSPyBackend choose_type ─────────────────────────────────────────────


class TestDSPyBackendChooseType:
    """DSPyBackend.choose_type picks a type from candidates."""

    def test_single_type_returns_directly(self):
        """choose_type with single candidate skips LLM and returns it."""
        backend = DSPyBackend()
        context = {"name": "Alice"}

        result = backend.choose_type([Greet], context)

        assert result is Greet

    def test_multiple_types_calls_predictor(self):
        """choose_type with multiple types uses dspy.Predict to pick."""
        backend = DSPyBackend()
        context = {"name": "Alice"}

        with patch("dspy.Predict") as mock_predict_cls:
            mock_predictor = MagicMock()
            mock_predict_cls.return_value = mock_predictor
            mock_predictor.return_value = dspy.Prediction(choice="Farewell")

            result = backend.choose_type([Greet, Farewell], context)

            assert result is Farewell
            mock_predict_cls.assert_called_once()

    def test_multiple_types_passes_context(self):
        """choose_type passes context dict values to predictor."""
        backend = DSPyBackend()
        context = {"name": "Bob", "mood": "happy"}

        with patch("dspy.Predict") as mock_predict_cls:
            mock_predictor = MagicMock()
            mock_predict_cls.return_value = mock_predictor
            mock_predictor.return_value = dspy.Prediction(choice="Greet")

            backend.choose_type([Greet, Farewell], context)

            call_kwargs = mock_predictor.call_args[1]
            assert "context" in call_kwargs


# ── DSPyBackend fill ────────────────────────────────────────────────────


class TestDSPyBackendFill:
    """DSPyBackend.fill creates a node instance with LM-generated fields."""

    def test_fill_uses_node_to_signature(self):
        """fill() calls node_to_signature(target, is_start=False)."""
        backend = DSPyBackend()
        context = {"name": "Alice"}

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict_cls:
                mock_predictor = MagicMock()
                mock_predict_cls.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(
                    greeting="Hello Alice"
                )

                backend.fill(Greet, context, "Greet")

                mock_sig.assert_called_once_with(Greet, is_start=False)

    def test_fill_returns_target_instance(self):
        """fill() returns an instance of the target type."""
        backend = DSPyBackend()
        context = {"name": "Alice"}

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict_cls:
                mock_predictor = MagicMock()
                mock_predict_cls.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(
                    greeting="Hello Alice"
                )

                result = backend.fill(Greet, context, "Greet")

                assert isinstance(result, Greet)
                assert result.name == "Alice"
                assert result.greeting == "Hello Alice"

    def test_fill_passes_context_as_inputs(self):
        """fill() passes context dict values as predictor inputs."""
        backend = DSPyBackend()
        context = {"name": "Bob"}

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict_cls:
                mock_predictor = MagicMock()
                mock_predict_cls.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(
                    greeting="Hi Bob"
                )

                backend.fill(Greet, context, "Greet")

                call_kwargs = mock_predictor.call_args[1]
                assert call_kwargs["name"] == "Bob"

    def test_fill_with_instruction_includes_docstring(self):
        """fill() uses instruction parameter (class name + docstring)."""
        backend = DSPyBackend()
        context = {"content": "some text"}

        with patch("bae.dspy_backend.node_to_signature") as mock_sig:
            mock_sig.return_value = MagicMock()

            with patch("dspy.Predict") as mock_predict_cls:
                mock_predictor = MagicMock()
                mock_predict_cls.return_value = mock_predictor
                mock_predictor.return_value = dspy.Prediction(
                    summary="short text"
                )

                result = backend.fill(
                    Summarize, context, "Summarize: Summarize content."
                )

                assert isinstance(result, Summarize)


# ── PydanticAIBackend choose_type ────────────────────────────────────────


class TestPydanticAIBackendChooseType:
    """PydanticAIBackend.choose_type picks from candidates."""

    def test_single_type_returns_directly(self):
        """choose_type with single candidate returns it without LLM call."""
        backend = PydanticAIBackend()

        result = backend.choose_type([Greet], {"name": "Alice"})

        assert result is Greet

    def test_multiple_types_picks_from_candidates(self):
        """choose_type with multiple types asks agent to pick."""
        backend = PydanticAIBackend()

        with patch.object(backend, "_get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent
            mock_result = MagicMock()
            mock_result.output = "Farewell"
            mock_agent.run_sync.return_value = mock_result

            result = backend.choose_type([Greet, Farewell], {"name": "Alice"})

            assert result is Farewell


# ── PydanticAIBackend fill ───────────────────────────────────────────────


class TestPydanticAIBackendFill:
    """PydanticAIBackend.fill returns target instance."""

    def test_fill_returns_target_instance(self):
        """fill() returns an instance of the target type via model_construct."""
        from bae.lm import _build_plain_model

        backend = PydanticAIBackend()
        # Greet has no Dep/Recall fields, so resolved is empty
        # All fields are plain — LLM fills everything
        resolved: dict = {}

        PlainModel = _build_plain_model(Greet)
        plain_output = PlainModel.model_validate(
            {"name": "Alice", "greeting": "Hello Alice"}
        )

        with patch.object(backend, "_get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent
            mock_result = MagicMock()
            mock_result.output = plain_output
            mock_agent.run_sync.return_value = mock_result

            result = backend.fill(Greet, resolved, "Greet")

            assert isinstance(result, Greet)
            assert result.name == "Alice"
            assert result.greeting == "Hello Alice"


# ── ClaudeCLIBackend choose_type ─────────────────────────────────────────


class TestClaudeCLIBackendChooseType:
    """ClaudeCLIBackend.choose_type uses two-step CLI pattern."""

    def test_single_type_returns_directly(self):
        """choose_type with single candidate returns it without CLI call."""
        backend = ClaudeCLIBackend()

        result = backend.choose_type([Greet], {"name": "Alice"})

        assert result is Greet

    def test_multiple_types_uses_cli(self):
        """choose_type with multiple types calls CLI to pick."""
        backend = ClaudeCLIBackend()

        with patch.object(backend, "_run_cli_json") as mock_cli:
            mock_cli.return_value = {"choice": "Farewell"}

            result = backend.choose_type([Greet, Farewell], {"name": "Alice"})

            assert result is Farewell
            mock_cli.assert_called_once()


# ── ClaudeCLIBackend fill ────────────────────────────────────────────────


class TestClaudeCLIBackendFill:
    """ClaudeCLIBackend.fill uses XML next-token completion."""

    def test_fill_returns_target_instance(self):
        """fill() calls CLI in text mode and returns parsed target instance."""
        backend = ClaudeCLIBackend()
        # Greet has all plain fields — resolved is empty
        resolved: dict = {}

        # LLM continues from <name> open tag
        xml_response = """Alice</name>
  <greeting>Hello Alice</greeting>
</Greet>"""

        with patch.object(backend, "_run_cli_text") as mock_cli:
            mock_cli.return_value = xml_response

            result = backend.fill(Greet, resolved, "Greet")

            assert isinstance(result, Greet)
            assert result.name == "Alice"
            assert result.greeting == "Hello Alice"

    def test_fill_calls_cli_text_not_json(self):
        """fill() uses _run_cli_text (text mode), not _run_cli_json."""
        backend = ClaudeCLIBackend()
        resolved: dict = {}

        xml_response = "Alice</name>\n  <greeting>Hi</greeting>\n</Greet>"

        with patch.object(backend, "_run_cli_text") as mock_text:
            mock_text.return_value = xml_response

            with patch.object(backend, "_run_cli_json") as mock_json:
                backend.fill(Greet, resolved, "Greet")

                mock_text.assert_called_once()
                mock_json.assert_not_called()
