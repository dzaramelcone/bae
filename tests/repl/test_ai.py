"""Tests for AI callable class, context builder, and code extractor."""

from __future__ import annotations

from typing import Annotated
from unittest.mock import MagicMock

import pytest

from bae.graph import Graph
from bae.markers import Dep
from bae.node import Node
from bae.repl.ai import AI, _build_context


# --- Test fixtures ---


def fetch_data() -> str:
    return "data"


class AlphaNode(Node):
    """First node."""

    query: str

    async def __call__(self) -> BetaNode | None:
        ...


class BetaNode(Node):
    """Second node."""

    answer: str
    info: Annotated[str, Dep(fetch_data)]

    async def __call__(self) -> None:
        ...


@pytest.fixture
def mock_lm():
    """Minimal LM stub."""
    return MagicMock()


@pytest.fixture
def mock_router():
    """Minimal ChannelRouter stub."""
    return MagicMock()


@pytest.fixture
def ai(mock_lm, mock_router):
    """AI instance with mocked dependencies."""
    return AI(lm=mock_lm, router=mock_router, namespace={})


# --- TestExtractCode ---


class TestExtractCode:
    """Tests for AI.extract_code static method."""

    def test_single_python_block(self):
        """Extracts a single ```python block."""
        text = "Here is code:\n```python\nx = 42\n```\nDone."
        result = AI.extract_code(text)
        assert result == ["x = 42"]

    def test_multiple_blocks(self):
        """Extracts multiple code blocks from one response."""
        text = "First:\n```python\na = 1\n```\nSecond:\n```python\nb = 2\n```"
        result = AI.extract_code(text)
        assert result == ["a = 1", "b = 2"]

    def test_bare_backticks(self):
        """Extracts code from bare ``` blocks (no language tag)."""
        text = "Code:\n```\nprint('hi')\n```"
        result = AI.extract_code(text)
        assert result == ["print('hi')"]

    def test_py_shorthand(self):
        """Extracts code from ```py blocks."""
        text = "Code:\n```py\ny = 99\n```"
        result = AI.extract_code(text)
        assert result == ["y = 99"]

    def test_no_code_blocks(self):
        """Returns empty list when no code blocks present."""
        text = "Just some plain text without any code."
        result = AI.extract_code(text)
        assert result == []

    def test_nested_text(self):
        """Handles code block containing backtick strings."""
        text = '```python\ns = "triple `tick` test"\nprint(s)\n```'
        result = AI.extract_code(text)
        assert len(result) == 1
        assert "triple `tick` test" in result[0]


# --- TestBuildContext ---


class TestBuildContext:
    """Tests for _build_context namespace summarizer."""

    def test_empty_namespace(self):
        """Namespace with only __builtins__ returns empty string."""
        ns = {"__builtins__": __builtins__}
        assert _build_context(ns) == ""

    def test_user_variables(self):
        """Namespace with user vars produces Variables section."""
        ns = {"__builtins__": __builtins__, "x": 42, "name": "hello"}
        result = _build_context(ns)
        assert "Variables:" in result
        assert "x = 42" in result
        assert "name = 'hello'" in result

    def test_graph_topology(self):
        """Namespace with a Graph produces Graph section with edges."""
        graph = Graph(start=AlphaNode)
        ns = {"__builtins__": __builtins__, "graph": graph}
        result = _build_context(ns)
        assert "Graph:" in result
        assert "AlphaNode ->" in result
        assert "BetaNode" in result

    def test_trace_summary(self):
        """Namespace with _trace list produces Trace section."""
        trace = [AlphaNode(query="q1"), BetaNode(answer="a", info="i")]
        ns = {"__builtins__": __builtins__, "_trace": trace}
        result = _build_context(ns)
        assert "Trace:" in result
        assert "AlphaNode" in result
        assert "BetaNode" in result

    def test_skips_internals(self):
        """Known bae names and underscore keys do not appear in output."""
        ns = {
            "__builtins__": __builtins__,
            "ai": MagicMock(),
            "ns": MagicMock(),
            "store": MagicMock(),
            "Node": Node,
            "_private": "hidden",
        }
        result = _build_context(ns)
        assert result == ""

    def test_truncation(self):
        """Output exceeding MAX_CONTEXT_CHARS gets truncated."""
        ns = {"__builtins__": __builtins__}
        # Create many large variables to exceed 2000 chars
        for i in range(100):
            ns[f"var_{i:03d}"] = "x" * 50
        result = _build_context(ns)
        assert "... (truncated)" in result
        # The truncated result should not exceed MAX_CONTEXT_CHARS + the suffix
        assert len(result) <= 2000 + len("\n  ... (truncated)") + 1


# --- TestAIRepr ---


class TestAIRepr:
    """Tests for AI.__repr__ history display."""

    def test_repr_no_history(self, ai):
        """AI with empty history shows 0 messages."""
        assert repr(ai) == "ai -- await ai('question'). 0 messages in history."

    def test_repr_with_history(self, ai):
        """AI with history items shows correct count."""
        ai._history = ["msg"] * 5
        assert repr(ai) == "ai -- await ai('question'). 5 messages in history."


# --- TestAILazyInit ---


class TestAILazyInit:
    """Tests for lazy Agent construction."""

    def test_agent_none_at_construction(self, mock_lm, mock_router):
        """Agent is None immediately after AI construction."""
        ai = AI(lm=mock_lm, router=mock_router, namespace={})
        assert ai._agent is None
