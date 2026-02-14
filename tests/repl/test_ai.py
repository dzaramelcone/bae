"""Tests for AI callable class, context builder, code extractor, and eval loop."""

from __future__ import annotations

import asyncio
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bae.graph import Graph
from bae.markers import Dep
from bae.node import Node
from bae.repl.ai import (
    AI, _build_context, _load_prompt, _PROMPT_FILE, run_tool_calls,
)


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


# --- TestExtractExecutable ---


class TestExtractExecutable:
    """Tests for AI.extract_executable static method."""

    def test_single_executable_block(self):
        """Single <run> block extracts code with zero extras."""
        text = "Here is the result:\n<run>\nx = 42\n</run>\nDone."
        code, extra = AI.extract_executable(text)
        assert code == "x = 42"
        assert extra == 0

    def test_illustrative_block_ignored(self):
        """Text with only markdown fences returns (None, 0)."""
        text = "Here's an example:\n```python\nx = 42\n```\nThat's how it works."
        code, extra = AI.extract_executable(text)
        assert code is None
        assert extra == 0

    def test_mixed_blocks(self):
        """One <run> and one illustrative fence returns (exec_code, 0)."""
        text = (
            "Here's an example:\n```python\n# illustrative\nx = 1\n```\n"
            "Let me run it:\n<run>\nresult = 2 + 2\n</run>"
        )
        code, extra = AI.extract_executable(text)
        assert code == "result = 2 + 2"
        assert extra == 0

    def test_multiple_executable_blocks(self):
        """Two <run> blocks returns (first_code, 1)."""
        text = (
            "First:\n<run>\na = 1\n</run>\n"
            "Second:\n<run>\nb = 2\n</run>"
        )
        code, extra = AI.extract_executable(text)
        assert code == "a = 1"
        assert extra == 1

    def test_no_code_blocks(self):
        """Plain text returns (None, 0)."""
        text = "Just some plain text without any code."
        code, extra = AI.extract_executable(text)
        assert code is None
        assert extra == 0

    def test_bare_fence_not_extracted(self):
        """Bare ``` fence is not treated as executable."""
        text = "Code:\n```\nprint('hi')\n```"
        code, extra = AI.extract_executable(text)
        assert code is None
        assert extra == 0


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
        """System prompt references bae API and convention."""
        prompt = _load_prompt()
        assert "bae" in prompt
        assert "Node" in prompt
        assert "Graph" in prompt
        assert "<run>" in prompt

    def test_prompt_mentions_convention(self):
        """System prompt contains the Code execution convention section."""
        prompt = _load_prompt()
        assert "Code execution convention" in prompt

    def test_prompt_mentions_tool_tags(self):
        """System prompt contains all 5 tool tag formats."""
        prompt = _load_prompt()
        assert "<R:" in prompt
        assert "<W:" in prompt
        assert "<E:" in prompt
        assert "<G:" in prompt
        assert "<Grep:" in prompt


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


# --- TestEvalLoop ---


class TestEvalLoop:
    """Tests for AI.__call__ eval loop: extract <run> blocks -> execute -> feed back."""

    @pytest.fixture
    def eval_ai(self, mock_lm, mock_router):
        """AI instance with mocked _send for eval loop testing."""
        ai = AI(lm=mock_lm, router=mock_router, namespace={}, max_eval_iters=3)
        ai._send = AsyncMock()
        return ai

    @pytest.mark.asyncio
    async def test_eval_loop_no_code_returns_response(self, eval_ai):
        """Plain text response returns without looping."""
        eval_ai._send.return_value = "Just a plain answer, no code."
        result = await eval_ai("hello")
        assert result == "Just a plain answer, no code."
        assert eval_ai._send.call_count == 1

    @pytest.mark.asyncio
    async def test_eval_loop_extracts_and_executes(self, eval_ai):
        """<run> block in response triggers async_exec, second response has no code."""
        eval_ai._send.side_effect = [
            "Try this:\n<run>\nx = 42\n</run>",
            "Done, x is 42.",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (42, "")
            result = await eval_ai("do something")
        assert result == "Done, x is 42."
        mock_exec.assert_called_once_with("x = 42", eval_ai._namespace)

    @pytest.mark.asyncio
    async def test_eval_loop_feeds_back_output(self, eval_ai):
        """Execution output is fed back to AI as next prompt."""
        eval_ai._send.side_effect = [
            "<run>\nx = 42\n</run>",
            "Got it.",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (42, "")
            await eval_ai("compute")
        # Second _send call receives the feedback with the result
        feedback = eval_ai._send.call_args_list[1][0][0]
        assert "[Output]" in feedback
        assert "42" in feedback

    @pytest.mark.asyncio
    async def test_eval_loop_iteration_limit(self, eval_ai):
        """Loop stops after max_eval_iters even if AI keeps producing <run> blocks."""
        eval_ai._send.return_value = "<run>\nx = 1\n</run>"
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (1, "")
            await eval_ai("loop forever")
        # 1 initial + 3 feedback rounds (max_eval_iters=3)
        assert eval_ai._send.call_count == 4

    @pytest.mark.asyncio
    async def test_eval_loop_no_output_skips_feedback(self, eval_ai):
        """No-output execution breaks the loop without prompting AI again."""
        eval_ai._send.side_effect = [
            "<run>\nx = 42\n</run>",
            "should not reach this",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (None, "")
            result = await eval_ai("assign x")
        # Only 1 send (initial), no feedback round
        assert eval_ai._send.call_count == 1
        assert result == "<run>\nx = 42\n</run>"

    @pytest.mark.asyncio
    async def test_eval_loop_awaits_coroutine(self, eval_ai):
        """Coroutine from async_exec is awaited inline and result fed back."""
        eval_ai._send.side_effect = [
            "<run>\nawait something()\n</run>",
            "Got the result.",
        ]

        async def fake_coro():
            return "async_result"

        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (fake_coro(), "")
            await eval_ai("run async")
        feedback = eval_ai._send.call_args_list[1][0][0]
        assert "async_result" in feedback

    @pytest.mark.asyncio
    async def test_eval_loop_catches_exec_error(self, eval_ai):
        """Execution errors are caught and fed back as traceback, not raised."""
        eval_ai._send.side_effect = [
            "<run>\nraise ValueError('oops')\n</run>",
            "I see the error.",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = ValueError("oops")
            result = await eval_ai("break it")
        assert result == "I see the error."
        feedback = eval_ai._send.call_args_list[1][0][0]
        assert "ValueError" in feedback
        assert "oops" in feedback

    @pytest.mark.asyncio
    async def test_eval_loop_tees_output(self, eval_ai):
        """Eval loop writes both code AND execution output to [py] channel."""
        eval_ai._send.side_effect = [
            "<run>\nx = 42\n</run>",
            "Done.",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (42, "printed stuff\n")
            await eval_ai("compute")

        # Collect all router.write calls for the "py" channel
        py_writes = [
            c for c in eval_ai._router.write.call_args_list
            if c[0][0] == "py"
        ]
        assert len(py_writes) == 2
        # First write: the code
        assert py_writes[0].kwargs["metadata"]["type"] == "ai_exec"
        assert py_writes[0][0][1] == "x = 42"
        # Second write: the execution output
        assert py_writes[1].kwargs["metadata"]["type"] == "ai_exec_result"
        assert "printed stuff" in py_writes[1][0][1]
        assert "42" in py_writes[1][0][1]

    @pytest.mark.asyncio
    async def test_eval_loop_tees_error_output(self, eval_ai):
        """Eval loop writes traceback output to [py] channel on execution error."""
        eval_ai._send.side_effect = [
            "<run>\nraise ValueError('boom')\n</run>",
            "I see the error.",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = ValueError("boom")
            await eval_ai("break it")

        py_writes = [
            c for c in eval_ai._router.write.call_args_list
            if c[0][0] == "py"
        ]
        assert len(py_writes) == 2
        # Second write should be the traceback
        assert py_writes[1].kwargs["metadata"]["type"] == "ai_exec_result"
        assert "ValueError" in py_writes[1][0][1]

    @pytest.mark.asyncio
    async def test_eval_loop_cancellation_propagates(self, eval_ai):
        """CancelledError from async_exec propagates out of eval loop."""
        eval_ai._send.side_effect = [
            "<run>\nawait something()\n</run>",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = asyncio.CancelledError()
            with pytest.raises(asyncio.CancelledError):
                await eval_ai("cancel me")

    @pytest.mark.asyncio
    async def test_eval_loop_multi_block_notice(self, eval_ai):
        """Two <run> blocks: only first executed, debug channel gets notice, feedback includes notice."""
        eval_ai._send.side_effect = [
            "First:\n<run>\na = 1\n</run>\nSecond:\n<run>\nb = 2\n</run>",
            "Got it.",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (None, "")
            await eval_ai("multi block")

        # Only first block executed
        mock_exec.assert_called_once_with("a = 1", eval_ai._namespace)

        # Debug channel received notice
        debug_writes = [
            c for c in eval_ai._router.write.call_args_list
            if c[0][0] == "debug"
        ]
        assert len(debug_writes) == 1
        assert "1 additional block was ignored" in debug_writes[0][0][1]
        assert debug_writes[0].kwargs["metadata"]["type"] == "exec_notice"

        # AI feedback includes notice
        feedback = eval_ai._send.call_args_list[1][0][0]
        assert "1 additional block was ignored" in feedback

    @pytest.mark.asyncio
    async def test_eval_loop_illustrative_not_executed(self, eval_ai):
        """Response with only illustrative code (markdown fences) does not execute anything."""
        eval_ai._send.side_effect = [
            "Here's an example:\n```python\nx = 42\n```\nThat's how it works.",
        ]
        with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
            result = await eval_ai("show example")

        # No execution
        mock_exec.assert_not_called()
        assert result == "Here's an example:\n```python\nx = 42\n```\nThat's how it works."


# --- TestRunToolCalls ---


class TestRunToolCalls:
    """Tests for run_tool_calls(): detect tags, execute directly, return (tag, output) pairs."""

    @pytest.fixture
    def sample_file(self, tmp_path):
        """Create a sample .py file for read/edit/grep tests."""
        f = tmp_path / "sample.py"
        f.write_text("line1\nline2\nline3\nline4\nline5\n")
        return f

    def test_read_tag(self, sample_file):
        """<R:filepath> reads the file and returns contents."""
        result = run_tool_calls(f"<R:{sample_file}>")
        assert len(result) == 1
        tag, output = result[0]
        assert "line1" in output
        assert "line5" in output

    def test_write_tag(self, tmp_path):
        """<W:filepath>content</W> writes file and returns confirmation."""
        out = tmp_path / "out.txt"
        result = run_tool_calls(f"<W:{out}>\nhello world\n</W>")
        assert len(result) == 1
        tag, output = result[0]
        assert "Wrote" in output
        assert out.read_text() == "hello world"

    def test_edit_read_tag(self, sample_file):
        """<E:filepath:start-end> returns numbered lines from the file."""
        result = run_tool_calls(f"<E:{sample_file}:2-4>")
        assert len(result) == 1
        tag, output = result[0]
        assert "line2" in output
        assert "line4" in output

    def test_edit_replace_tag(self, sample_file):
        """<E:filepath:start-end>content</E> replaces lines in the file."""
        result = run_tool_calls(f"<E:{sample_file}:2-3>\nreplaced\n</E>")
        assert len(result) == 1
        tag, output = result[0]
        assert "Replaced" in output
        content = sample_file.read_text()
        assert "replaced" in content
        assert "line2" not in content

    def test_glob_tag(self, sample_file):
        """<G:pattern> returns matching file paths."""
        result = run_tool_calls(f"<G:{sample_file.parent}/*.py>")
        assert len(result) == 1
        tag, output = result[0]
        assert "sample.py" in output

    def test_grep_tag(self, sample_file):
        """<Grep:pattern path> searches files for matching lines."""
        result = run_tool_calls(f"<Grep:line3 {sample_file.parent}>")
        assert len(result) == 1
        tag, output = result[0]
        assert "line3" in output

    def test_grep_with_file_path(self, sample_file):
        """<Grep:pattern filepath> restricts search to a single file."""
        result = run_tool_calls(f"<Grep:line2 {sample_file}>")
        assert len(result) == 1
        assert "line2" in result[0][1]

    def test_grep_strips_quotes(self, sample_file):
        """<Grep:"pattern" path> strips surrounding quotes from pattern."""
        result = run_tool_calls(f'<Grep:"line4" {sample_file.parent}>')
        assert len(result) == 1
        assert "line4" in result[0][1]

    def test_no_tags_returns_empty(self):
        """Plain prose with no tool tags returns empty list."""
        assert run_tool_calls("Just some plain text.") == []

    def test_illustrative_fence_ignored(self):
        """Tool tag inside a markdown fence returns empty list."""
        text = "Example:\n```\n<R:foo.py>\n```\nThat's how it works."
        assert run_tool_calls(text) == []

    def test_run_block_ignored(self):
        """Tool tag inside a <run>...</run> block returns empty list."""
        text = "Running:\n<run>\n<R:foo.py>\n</run>\nDone."
        assert run_tool_calls(text) == []

    def test_multiple_tags(self, sample_file, tmp_path):
        """Multiple tags all execute and return results in order."""
        f2 = tmp_path / "other.py"
        f2.write_text("other content\n")
        text = f"<R:{sample_file}>\n<R:{f2}>"
        result = run_tool_calls(text)
        assert len(result) == 2
        assert "line1" in result[0][1]
        assert "other content" in result[1][1]

    def test_tag_must_be_on_own_line(self):
        """Tag embedded in prose (not on its own line) returns empty list."""
        text = "some text <R:foo.py> more text"
        assert run_tool_calls(text) == []

    def test_write_without_closing_tag(self):
        """<W:filepath> with no </W> closing returns empty list."""
        text = "<W:foo.txt>\nsome content but no closing tag"
        assert run_tool_calls(text) == []

    def test_case_insensitive_tags(self, sample_file):
        """Tags are case-insensitive: <read:>, <GLOB:>, <grep:> all work."""
        assert len(run_tool_calls(f"<read:{sample_file}>")) == 1
        assert len(run_tool_calls(f"<GLOB:{sample_file.parent}/*.py>")) == 1

    def test_full_word_variants(self, sample_file, tmp_path):
        """Full word tags work: <Read:>, <Write:>, <Glob:>."""
        assert len(run_tool_calls(f"<Read:{sample_file}>")) == 1
        assert len(run_tool_calls(f"<Glob:{sample_file.parent}/*.py>")) == 1
        out = tmp_path / "word.txt"
        result = run_tool_calls(f"<Write:{out}>\nhello\n</Write>")
        assert len(result) == 1
        assert out.read_text() == "hello"

    def test_read_with_line_range_dash(self, sample_file):
        """<R:path:start-end> reads specific lines."""
        result = run_tool_calls(f"<R:{sample_file}:2-4>")
        assert len(result) == 1
        assert "line2" in result[0][1]
        assert "line4" in result[0][1]

    def test_read_with_line_range_colon(self, sample_file):
        """<R:path:start:end> reads specific lines (colon separator)."""
        result = run_tool_calls(f"<R:{sample_file}:2:4>")
        assert len(result) == 1
        assert "line2" in result[0][1]

    def test_osc8_tool_call(self, sample_file):
        """OSC 8 hyperlink-wrapped tool calls are detected and executed."""
        text = f"\033]8;id=123;Glob:{sample_file.parent}/*.py\033\\\\"
        result = run_tool_calls(text)
        assert len(result) == 1
        assert "sample.py" in result[0][1]

    def test_read_missing_file(self):
        """Read of nonexistent file returns error string."""
        result = run_tool_calls("<R:/nonexistent/path/file.py>")
        assert len(result) == 1
        assert "FileNotFoundError" in result[0][1] or "No such file" in result[0][1]


# --- TestEvalLoopToolCalls ---


class TestEvalLoopToolCalls:
    """Tests for tool call execution in the eval loop: detect tags -> execute -> feed back."""

    @pytest.fixture
    def eval_ai(self, mock_lm, mock_router):
        """AI instance with mocked _send for eval loop testing."""
        ai = AI(lm=mock_lm, router=mock_router, namespace={}, max_eval_iters=3)
        ai._send = AsyncMock()
        return ai

    @pytest.mark.asyncio
    async def test_tool_call_executes(self, eval_ai):
        """Response with tool tag triggers run_tool_calls, results fed back."""
        eval_ai._send.side_effect = [
            "<R:foo.py>",
            "Here are the contents.",
        ]
        with patch("bae.repl.ai.run_tool_calls") as mock_run:
            mock_run.side_effect = [
                [("<R:foo.py>", "file contents here")],
                [],
            ]
            result = await eval_ai("read foo.py")
        assert result == "Here are the contents."

    @pytest.mark.asyncio
    async def test_tool_call_feeds_back_output(self, eval_ai):
        """Tool output fed back to AI with [Tool output] prefix."""
        eval_ai._send.side_effect = ["<R:foo.py>", "Got it."]
        with patch("bae.repl.ai.run_tool_calls") as mock_run:
            mock_run.side_effect = [[("<R:foo.py>", "file data")], []]
            await eval_ai("read")
        feedback = eval_ai._send.call_args_list[1][0][0]
        assert feedback.startswith("[Tool output]")
        assert "file data" in feedback

    @pytest.mark.asyncio
    async def test_tool_call_metadata_type(self, eval_ai):
        """Router writes use tool_translated and tool_result metadata types."""
        eval_ai._send.side_effect = ["<R:foo.py>", "Done."]
        with patch("bae.repl.ai.run_tool_calls") as mock_run:
            mock_run.side_effect = [[("<R:foo.py>", "output")], []]
            await eval_ai("read")
        py_writes = [
            c for c in eval_ai._router.write.call_args_list
            if c[0][0] == "py"
        ]
        assert len(py_writes) == 2
        assert py_writes[0].kwargs["metadata"]["type"] == "tool_translated"
        assert py_writes[1].kwargs["metadata"]["type"] == "tool_result"

    @pytest.mark.asyncio
    async def test_tool_call_before_run_block(self, eval_ai):
        """Tool tags take precedence over <run> blocks."""
        eval_ai._send.side_effect = [
            "<R:foo.py>\n<run>\nx = 1\n</run>",
            "Done.",
        ]
        with patch("bae.repl.ai.run_tool_calls") as mock_run:
            mock_run.side_effect = [[("<R:foo.py>", "file data")], []]
            with patch("bae.repl.ai.async_exec", new_callable=AsyncMock) as mock_exec:
                await eval_ai("read and run")
        # async_exec NOT called (tool calls take precedence)
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_call_counts_against_iters(self, eval_ai):
        """Tool calls count against max_eval_iters (loop stops at limit)."""
        eval_ai._send.return_value = "<R:foo.py>"
        with patch("bae.repl.ai.run_tool_calls") as mock_run:
            mock_run.return_value = [("<R:foo.py>", "output")]
            await eval_ai("loop tool calls")
        # 1 initial + 3 feedback rounds (max_eval_iters=3)
        assert eval_ai._send.call_count == 4

    @pytest.mark.asyncio
    async def test_tool_call_error_in_output(self, eval_ai):
        """Errors from tool execution appear in output (caught inside run_tool_calls)."""
        eval_ai._send.side_effect = [
            "<R:foo.py>",
            "I see the error.",
        ]
        with patch("bae.repl.ai.run_tool_calls") as mock_run:
            mock_run.side_effect = [
                [("<R:foo.py>", "FileNotFoundError: No such file: foo.py")],
                [],
            ]
            result = await eval_ai("read missing")
        assert result == "I see the error."
        feedback = eval_ai._send.call_args_list[1][0][0]
        assert "FileNotFoundError" in feedback
        assert "foo.py" in feedback

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_all_executed(self, eval_ai):
        """Multiple tool results combined with --- separator in single feedback."""
        eval_ai._send.side_effect = ["<R:a.py>\n<R:b.py>", "Got both."]
        with patch("bae.repl.ai.run_tool_calls") as mock_run:
            mock_run.side_effect = [
                [("<R:a.py>", "contents of a"), ("<R:b.py>", "contents of b")],
                [],
            ]
            result = await eval_ai("read both")
        assert result == "Got both."
        feedback = eval_ai._send.call_args_list[1][0][0]
        assert "[Tool output]" in feedback
        assert "contents of a" in feedback
        assert "---" in feedback
        assert "contents of b" in feedback
