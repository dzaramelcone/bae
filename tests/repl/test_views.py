"""Tests for view formatters: UserView, DebugView, AISelfView, ViewMode infrastructure."""

import re
from unittest.mock import patch, MagicMock

from prompt_toolkit.formatted_text import ANSI, FormattedText
from rich.text import Text

from bae.repl.channels import ViewFormatter
from bae.repl.ai import _tool_summary
from bae.repl.views import (
    UserView, DebugView, AISelfView,
    ViewMode, VIEW_CYCLE, VIEW_FORMATTERS,
    _rich_to_ansi,
)


@patch("bae.repl.views.print_formatted_text")
def test_user_view_buffers_ai_exec(mock_pft):
    """ai_exec metadata buffers code without printing."""
    view = UserView()
    view.render("py", "#87ff87", "x = 42", metadata={"type": "ai_exec"})
    mock_pft.assert_not_called()
    assert view._pending_code == "x = 42"


@patch("bae.repl.views.print_formatted_text")
def test_user_view_flushes_grouped_panel(mock_pft):
    """ai_exec then ai_exec_result produces exactly one ANSI print."""
    view = UserView()
    view.render("py", "#87ff87", "x = 42", metadata={"type": "ai_exec"})
    mock_pft.assert_not_called()

    view.render("py", "#87ff87", "42", metadata={"type": "ai_exec_result"})
    mock_pft.assert_called_once()
    arg = mock_pft.call_args[0][0]
    assert isinstance(arg, ANSI)


@patch("bae.repl.views.print_formatted_text")
def test_user_view_fallback_for_stdout(mock_pft):
    """stdout metadata renders with [py] prefix via FormattedText."""
    view = UserView()
    view.render("py", "#87ff87", "hello", metadata={"type": "stdout"})
    mock_pft.assert_called_once()
    fragments = list(mock_pft.call_args[0][0])
    assert fragments[0] == ("#87ff87 bold", "[py]")
    assert fragments[2] == ("", "hello")


@patch("bae.repl.views.print_formatted_text")
def test_user_view_fallback_no_metadata(mock_pft):
    """No metadata renders with standard [py] prefix."""
    view = UserView()
    view.render("py", "#87ff87", "hello", metadata=None)
    mock_pft.assert_called_once()
    fragments = list(mock_pft.call_args[0][0])
    assert fragments[0] == ("#87ff87 bold", "[py]")
    assert fragments[2] == ("", "hello")


@patch("bae.repl.views.print_formatted_text")
def test_user_view_stale_buffer_flushed(mock_pft):
    """Second ai_exec flushes stale buffered code as standalone panel."""
    view = UserView()
    view.render("py", "#87ff87", "x = 1", metadata={"type": "ai_exec"})
    mock_pft.assert_not_called()

    # Second ai_exec should flush the first as a code-only panel
    view.render("py", "#87ff87", "x = 2", metadata={"type": "ai_exec"})
    mock_pft.assert_called_once()
    arg = mock_pft.call_args[0][0]
    assert isinstance(arg, ANSI)

    # The new code is now pending
    assert view._pending_code == "x = 2"


@patch("bae.repl.views.print_formatted_text")
def test_user_view_no_output_shows_executed(mock_pft):
    """(no output) result shows dim '(executed)' indicator below code."""
    view = UserView()
    view.render("py", "#87ff87", "x = 42", metadata={"type": "ai_exec"})
    view.render("py", "#87ff87", "(no output)", metadata={"type": "ai_exec_result"})
    mock_pft.assert_called_once()
    ansi_str = mock_pft.call_args[0][0].value
    assert "(no output)" not in ansi_str
    assert "executed" in ansi_str


@patch("bae.repl.views.print_formatted_text")
def test_user_view_label_in_panel_title(mock_pft):
    """Panel title includes the session label from metadata."""
    view = UserView()
    view.render("py", "#87ff87", "x = 42", metadata={"type": "ai_exec", "label": "2"})
    view.render("py", "#87ff87", "42", metadata={"type": "ai_exec_result", "label": "2"})
    mock_pft.assert_called_once()
    ansi_str = mock_pft.call_args[0][0].value
    assert "ai:2" in ansi_str


def test_user_view_satisfies_protocol():
    """UserView satisfies ViewFormatter protocol via structural typing."""
    assert isinstance(UserView(), ViewFormatter)


def test_rich_to_ansi_returns_string():
    """_rich_to_ansi produces a string containing the renderable's text."""
    result = _rich_to_ansi(Text("hello"))
    assert isinstance(result, str)
    assert "hello" in result


@patch("bae.repl.views.os.get_terminal_size")
def test_rich_to_ansi_uses_terminal_width(mock_size):
    """_rich_to_ansi queries terminal width per render."""
    mock_size.return_value = MagicMock(columns=40)
    result = _rich_to_ansi(Text("hello"))
    mock_size.assert_called()
    assert isinstance(result, str)
    assert "hello" in result
    # Verify narrow width is respected: lines should not exceed 40 chars
    for line in result.splitlines():
        clean = re.sub(r"\033\[[^m]*m", "", line)
        assert len(clean) <= 40


# --- Tool call display tests ---


@patch("bae.repl.views.print_formatted_text")
def test_user_view_tool_translated_shows_summary(mock_pft):
    """tool_translated metadata renders concise tool_summary, not raw tag."""
    view = UserView()
    view.render("py", "#87ff87", "<R:foo.py>", metadata={
        "type": "tool_translated",
        "tool_summary": "read foo.py (42 lines)",
    })
    mock_pft.assert_called_once()
    fragments = list(mock_pft.call_args[0][0])
    assert fragments[0] == ("#87ff87 bold", "[py]")
    assert fragments[2] == ("fg:#808080 italic", "read foo.py (42 lines)")


@patch("bae.repl.views.print_formatted_text")
def test_user_view_tool_translated_fallback(mock_pft):
    """tool_translated without tool_summary falls back to raw content."""
    view = UserView()
    view.render("py", "#87ff87", "<R:foo.py>", metadata={
        "type": "tool_translated",
    })
    mock_pft.assert_called_once()
    fragments = list(mock_pft.call_args[0][0])
    assert fragments[2] == ("fg:#808080 italic", "<R:foo.py>")


def test_tool_summary_read():
    """_tool_summary generates 'read path (N lines)' for Read tags."""
    output = "line1\nline2\nline3"
    result = _tool_summary("<R:bae/repl/ai.py>", output)
    assert result == "read bae/repl/ai.py (3 lines)"


def test_tool_summary_glob():
    """_tool_summary generates 'glob pattern (N matches)' for Glob tags."""
    output = "src/a.py\nsrc/b.py\nsrc/c.py"
    result = _tool_summary("<G:src/*.py>", output)
    assert result == "glob src/*.py (3 matches)"


def test_tool_summary_write():
    """_tool_summary passes Write output through as-is."""
    output = "Wrote 42 chars to foo.py"
    result = _tool_summary("<W:foo.py>", output)
    assert result == "Wrote 42 chars to foo.py"


# --- DebugView tests ---


@patch("bae.repl.views.print_formatted_text")
def test_debug_view_shows_metadata(mock_pft):
    """DebugView header includes channel name and sorted metadata key=value pairs."""
    view = DebugView()
    view.render("py", "#87ff87", "x = 42", metadata={"type": "ai_exec", "label": "1"})
    header_call = mock_pft.call_args_list[0]
    header_ft = header_call[0][0]
    header_text = "".join(text for _, text in header_ft)
    assert "[py]" in header_text
    assert "label=1" in header_text
    assert "type=ai_exec" in header_text


@patch("bae.repl.views.print_formatted_text")
def test_debug_view_no_metadata(mock_pft):
    """DebugView header is just [channel] when metadata is None."""
    view = DebugView()
    view.render("py", "#87ff87", "hello", metadata=None)
    header_call = mock_pft.call_args_list[0]
    header_ft = header_call[0][0]
    header_text = "".join(text for _, text in header_ft)
    assert header_text == "[py]"


@patch("bae.repl.views.print_formatted_text")
def test_debug_view_content_lines_indented(mock_pft):
    """DebugView prints 1 header + N content lines, each with indent prefix."""
    view = DebugView()
    view.render("py", "#87ff87", "line1\nline2", metadata=None)
    assert mock_pft.call_count == 3  # 1 header + 2 content lines
    # Check content lines have indent prefix
    for call in mock_pft.call_args_list[1:]:
        ft = call[0][0]
        fragments = list(ft)
        assert fragments[0] == ("fg:#808080", "  ")


def test_debug_view_satisfies_protocol():
    """DebugView satisfies ViewFormatter protocol via structural typing."""
    assert isinstance(DebugView(), ViewFormatter)


# --- AISelfView tests ---


@patch("bae.repl.views.print_formatted_text")
def test_ai_self_view_response_tag(mock_pft):
    """AISelfView maps 'response' type to [ai-output] tag."""
    view = AISelfView()
    view.render("ai", "#87d7ff", "hello", metadata={"type": "response"})
    header_ft = mock_pft.call_args_list[0][0][0]
    header_text = "".join(text for _, text in header_ft)
    assert "[ai-output]" in header_text


@patch("bae.repl.views.print_formatted_text")
def test_ai_self_view_exec_tags(mock_pft):
    """AISelfView maps ai_exec to [exec-code] and ai_exec_result to [exec-result]."""
    view = AISelfView()

    view.render("py", "#87ff87", "x = 1", metadata={"type": "ai_exec"})
    header_text = "".join(text for _, text in mock_pft.call_args_list[0][0][0])
    assert "[exec-code]" in header_text

    mock_pft.reset_mock()
    view.render("py", "#87ff87", "1", metadata={"type": "ai_exec_result"})
    header_text = "".join(text for _, text in mock_pft.call_args_list[0][0][0])
    assert "[exec-result]" in header_text


@patch("bae.repl.views.print_formatted_text")
def test_ai_self_view_tool_tags(mock_pft):
    """AISelfView maps tool_translated to [tool-call] and tool_result to [tool-output]."""
    view = AISelfView()

    view.render("py", "#87ff87", "read('f.py')", metadata={"type": "tool_translated"})
    header_text = "".join(text for _, text in mock_pft.call_args_list[0][0][0])
    assert "[tool-call]" in header_text

    mock_pft.reset_mock()
    view.render("py", "#87ff87", "contents...", metadata={"type": "tool_result"})
    header_text = "".join(text for _, text in mock_pft.call_args_list[0][0][0])
    assert "[tool-output]" in header_text


@patch("bae.repl.views.print_formatted_text")
def test_ai_self_view_label_appended(mock_pft):
    """AISelfView appends :label to the tag when metadata has a label."""
    view = AISelfView()
    view.render("ai", "#87d7ff", "hi", metadata={"type": "response", "label": "3"})
    header_text = "".join(text for _, text in mock_pft.call_args_list[0][0][0])
    assert "[ai-output:3]" in header_text


@patch("bae.repl.views.print_formatted_text")
def test_ai_self_view_unknown_type_uses_channel(mock_pft):
    """AISelfView falls back to channel_name when type is empty/unknown."""
    view = AISelfView()
    view.render("bash", "#d7afff", "ls -la", metadata={})
    header_text = "".join(text for _, text in mock_pft.call_args_list[0][0][0])
    assert "[bash]" in header_text


def test_ai_self_view_satisfies_protocol():
    """AISelfView satisfies ViewFormatter protocol via structural typing."""
    assert isinstance(AISelfView(), ViewFormatter)


# --- ViewMode / infrastructure tests ---


def test_view_mode_values():
    """ViewMode enum has correct string values."""
    assert ViewMode.USER.value == "user"
    assert ViewMode.DEBUG.value == "debug"
    assert ViewMode.AI_SELF.value == "ai-self"


def test_view_cycle_order():
    """VIEW_CYCLE lists modes in toggle order: USER -> DEBUG -> AI_SELF."""
    assert VIEW_CYCLE == [ViewMode.USER, ViewMode.DEBUG, ViewMode.AI_SELF]


def test_view_formatters_maps_all_modes():
    """VIEW_FORMATTERS maps every ViewMode to its correct formatter class."""
    for mode in ViewMode:
        assert mode in VIEW_FORMATTERS
    assert VIEW_FORMATTERS[ViewMode.USER] is UserView
    assert VIEW_FORMATTERS[ViewMode.DEBUG] is DebugView
    assert VIEW_FORMATTERS[ViewMode.AI_SELF] is AISelfView
