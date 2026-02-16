"""TDD tests for LM Protocol choose_type/fill methods.

Tests choose_type() and fill() on ClaudeCLIBackend.
Uses mocks to avoid real LLM calls.
"""

from __future__ import annotations

from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bae.lm import ClaudeCLIBackend, LM
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


# ── ClaudeCLIBackend choose_type ─────────────────────────────────────────


class TestClaudeCLIBackendChooseType:
    """ClaudeCLIBackend.choose_type uses two-step CLI pattern."""

    async def test_single_type_returns_directly(self):
        """choose_type with single candidate returns it without CLI call."""
        backend = ClaudeCLIBackend()

        result = await backend.choose_type([Greet], {"name": "Alice"})

        assert result is Greet

    async def test_multiple_types_uses_cli(self):
        """choose_type with multiple types calls CLI to pick."""
        backend = ClaudeCLIBackend()

        with patch.object(backend, "_run_cli_json", new_callable=AsyncMock) as mock_cli:
            mock_cli.return_value = {"choice": "Farewell"}

            result = await backend.choose_type([Greet, Farewell], {"name": "Alice"})

            assert result is Farewell
            mock_cli.assert_called_once()


# ── ClaudeCLIBackend fill ────────────────────────────────────────────────


class TestClaudeCLIBackendFill:
    """ClaudeCLIBackend.fill uses JSON structured output."""

    async def test_fill_returns_target_instance(self):
        """fill() calls CLI with JSON schema and returns parsed target instance."""
        backend = ClaudeCLIBackend()
        resolved: dict = {}

        with patch.object(backend, "_run_cli_json", new_callable=AsyncMock) as mock_cli:
            mock_cli.return_value = {"name": "Alice", "greeting": "Hello Alice"}

            result = await backend.fill(Greet, resolved, "Greet")

            assert isinstance(result, Greet)
            assert result.name == "Alice"
            assert result.greeting == "Hello Alice"

    async def test_fill_uses_json_schema(self):
        """fill() calls _run_cli_json with JSON schema from plain model."""
        backend = ClaudeCLIBackend()
        resolved: dict = {}

        captured_schema = {}

        async def capture(prompt, schema, **kwargs):
            captured_schema.update(schema)
            return {"name": "Alice", "greeting": "Hi"}

        with patch.object(backend, "_run_cli_json", side_effect=capture):
            await backend.fill(Greet, resolved, "Greet")

        assert "properties" in captured_schema
        assert "name" in captured_schema["properties"]
        assert "greeting" in captured_schema["properties"]
