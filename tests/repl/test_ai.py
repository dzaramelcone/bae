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
        """Namespace with user vars produces REPL-style ns() output."""
        ns = {"__builtins__": __builtins__, "x": 42, "name": "hello"}
        result = _build_context(ns)
        assert ">>> ns()" in result
        assert "42" in result
        assert "'hello'" in result

    def test_graph_topology(self):
        """Namespace with a Graph produces REPL-style ns(graph) output."""
        graph = Graph(start=AlphaNode)
        ns = {"__builtins__": __builtins__, "graph": graph}
        result = _build_context(ns)
        assert ">>> ns(graph)" in result
        assert "AlphaNode ->" in result
        assert "BetaNode" in result

    def test_trace_summary(self):
        """Namespace with _trace list produces REPL-style trace output."""
        trace = [AlphaNode(query="q1"), BetaNode(answer="a", info="i")]
        ns = {"__builtins__": __builtins__, "_trace": trace}
        result = _build_context(ns)
        assert ">>> _trace" in result
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

    def test_repl_state_header(self):
        """Context starts with [REPL state] header."""
        ns = {"__builtins__": __builtins__, "x": 1}
        result = _build_context(ns)
        assert result.startswith("[REPL state]")


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


# --- TestAILabel ---


class TestAILabel:
    """Tests for AI label support."""

    def test_ai_label_default(self, mock_lm, mock_router):
        """AI label defaults to '1'."""
        ai = AI(lm=mock_lm, router=mock_router, namespace={})
        assert ai._label == "1"

    def test_ai_label_custom(self, mock_lm, mock_router):
        """AI with explicit label stores it."""
        ai = AI(lm=mock_lm, router=mock_router, namespace={}, label="2")
        assert ai._label == "2"

    def test_ai_repr_with_label(self, mock_lm, mock_router):
        """repr includes label prefix."""
        ai = AI(lm=mock_lm, router=mock_router, namespace={}, label="3")
        r = repr(ai)
        assert r.startswith("ai:3")
        assert "await ai('question')" in r


# --- TestCrossSessionContext ---


class TestCrossSessionContext:
    """Tests for SessionStore.cross_session_context."""

    @pytest.fixture
    def store(self, tmp_path):
        from bae.repl.store import SessionStore
        s = SessionStore(tmp_path / "ctx.db")
        yield s
        s.close()

    def test_cross_session_context_empty(self, store):
        """No previous sessions returns empty string."""
        assert store.cross_session_context() == ""

    def test_cross_session_context_excludes_current(self, store):
        """Entries from current session are excluded."""
        store.record("PY", "repl", "input", "x = 1")
        assert store.cross_session_context() == ""

    def test_cross_session_context_excludes_debug(self, store):
        """Debug channel entries are filtered out."""
        # Insert a previous-session entry on debug channel
        store._conn.execute(
            "INSERT INTO entries(session_id, timestamp, mode, channel, direction, content, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-session", 1.0, "DEBUG", "debug", "output", "debug msg", "{}"),
        )
        store._conn.commit()
        assert store.cross_session_context() == ""

    def test_cross_session_context_budget(self, store):
        """Output truncated to budget."""
        for i in range(30):
            store._conn.execute(
                "INSERT INTO entries(session_id, timestamp, mode, channel, direction, content, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("old-session", float(i), "PY", "repl", "input", "x" * 200, "{}"),
            )
        store._conn.commit()
        result = store.cross_session_context(budget=500)
        assert len(result) <= 500

    def test_cross_session_context_format(self, store):
        """Output starts with [Previous session context]."""
        store._conn.execute(
            "INSERT INTO entries(session_id, timestamp, mode, channel, direction, content, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-session", 1.0, "PY", "repl", "input", "hello world", "{}"),
        )
        store._conn.commit()
        result = store.cross_session_context()
        assert result.startswith("[Previous session context]")
        assert "[PY:repl]" in result
        assert "hello world" in result
