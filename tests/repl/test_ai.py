"""Tests for AI callable class, context builder, and code extractor."""

from __future__ import annotations

from typing import Annotated
from unittest.mock import MagicMock

import pytest

from bae.graph import Graph
from bae.markers import Dep
from bae.node import Node
from bae.repl.ai import AI, _build_context, _load_prompt, _PROMPT_FILE


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
    """Tests for AI.__repr__ session display."""

    def test_repr_fresh(self, ai):
        """AI with no calls shows session ID prefix and 0 calls."""
        r = repr(ai)
        assert "await ai('question')" in r
        assert "0 calls" in r
        assert "session " in r

    def test_repr_after_calls(self, ai):
        """AI with calls shows correct count."""
        ai._call_count = 3
        assert "3 calls" in repr(ai)


# --- TestAIInit ---


class TestAIInit:
    """Tests for AI construction."""

    def test_session_id_is_uuid(self, ai):
        """Session ID is a valid UUID string."""
        import uuid

        uuid.UUID(ai._session_id)  # raises if invalid

    def test_call_count_starts_zero(self, ai):
        """Call count starts at zero."""
        assert ai._call_count == 0

    def test_stores_references(self, mock_lm, mock_router):
        """AI stores lm, router, namespace references."""
        ns = {"x": 1}
        ai = AI(lm=mock_lm, router=mock_router, namespace=ns)
        assert ai._lm is mock_lm
        assert ai._router is mock_router
        assert ai._namespace is ns


# --- TestPromptFile ---


class TestPromptFile:
    """Tests for system prompt loading."""

    def test_prompt_file_exists(self):
        """ai_prompt.md exists next to ai.py."""
        assert _PROMPT_FILE.exists()

    def test_prompt_loads(self):
        """System prompt loads as non-empty string."""
        prompt = _load_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_prompt_mentions_bae(self):
        """System prompt references bae API."""
        prompt = _load_prompt()
        assert "bae" in prompt
        assert "Node" in prompt
        assert "Graph" in prompt
