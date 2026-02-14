"""Tests for UserView formatter: buffering, panel rendering, fallback, edge cases."""

import re
from unittest.mock import patch, MagicMock

from prompt_toolkit.formatted_text import ANSI, FormattedText
from rich.text import Text

from bae.repl.channels import ViewFormatter
from bae.repl.views import UserView, _rich_to_ansi


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
