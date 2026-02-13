"""Tests for Channel and ChannelRouter output multiplexing."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bae.repl.channels import (
    CHANNEL_DEFAULTS,
    Channel,
    ChannelRouter,
    disable_debug,
    enable_debug,
    toggle_channels,
)


@pytest.fixture
def store():
    """Mock SessionStore with record() method."""
    s = MagicMock()
    s.record = MagicMock()
    return s


@pytest.fixture
def channel(store):
    """A visible channel with a mock store."""
    return Channel(name="py", color="#87ff87", store=store)


@pytest.fixture
def hidden_channel(store):
    """A hidden channel with a mock store."""
    return Channel(name="bash", color="#d7afff", visible=False, store=store)


@pytest.fixture
def router(store):
    """A ChannelRouter with default channels registered."""
    r = ChannelRouter()
    for name, cfg in CHANNEL_DEFAULTS.items():
        r.register(name, cfg["color"], store=store)
    return r


# --- Channel tests ---


def test_channel_write_records_to_store(channel, store):
    """Channel.write() calls store.record() with correct mode/channel/direction."""
    channel.write("hello", mode="PY")
    store.record.assert_called_once_with("PY", "py", "output", "hello", None)


def test_channel_write_default_mode_uppercases_name(channel, store):
    """Channel.write() without mode uses uppercased channel name."""
    channel.write("hello")
    store.record.assert_called_once_with("PY", "py", "output", "hello", None)


def test_channel_write_buffers_content(channel):
    """Channel.write() always appends to _buffer."""
    channel.write("line 1")
    channel.write("line 2")
    assert channel._buffer == ["line 1", "line 2"]


def test_channel_write_visible_calls_display(channel):
    """Channel.write() calls _display when visible=True."""
    with patch.object(channel, "_display") as mock_display:
        channel.write("hello")
        mock_display.assert_called_once_with("hello")


def test_channel_write_hidden_skips_display(hidden_channel):
    """Channel.write() does NOT call _display when visible=False."""
    with patch.object(hidden_channel, "_display") as mock_display:
        hidden_channel.write("hello")
        mock_display.assert_not_called()


def test_channel_write_hidden_still_records(hidden_channel, store):
    """Channel.write() records to store even when hidden."""
    hidden_channel.write("hello", mode="BASH")
    store.record.assert_called_once()


def test_channel_write_hidden_still_buffers(hidden_channel):
    """Channel.write() buffers content even when hidden."""
    hidden_channel.write("hello")
    assert hidden_channel._buffer == ["hello"]


def test_channel_write_with_metadata(channel, store):
    """Channel.write() passes metadata through to store.record()."""
    channel.write("result", mode="PY", metadata={"type": "expr"})
    store.record.assert_called_once_with("PY", "py", "output", "result", {"type": "expr"})


def test_channel_write_with_direction(channel, store):
    """Channel.write() respects direction parameter."""
    channel.write("x = 42", mode="PY", direction="input")
    store.record.assert_called_once_with("PY", "py", "input", "x = 42", None)


def test_channel_write_no_store():
    """Channel.write() works without a store (no error)."""
    ch = Channel(name="py", color="#87ff87")
    ch.write("hello")  # should not raise
    assert ch._buffer == ["hello"]


@patch("bae.repl.channels.print_formatted_text")
def test_channel_display_renders_formatted(mock_pft):
    """Channel._display() renders color-coded prefix via print_formatted_text."""
    ch = Channel(name="py", color="#87ff87")
    ch._display("x = 42")
    mock_pft.assert_called_once()
    call_args = mock_pft.call_args[0][0]
    # FormattedText is a list of (style, text) tuples
    fragments = list(call_args)
    assert fragments[0] == ("#87ff87 bold", "[py]")
    assert fragments[1] == ("", " ")
    assert fragments[2] == ("", "x = 42")


@patch("bae.repl.channels.print_formatted_text")
def test_channel_display_multiline(mock_pft):
    """Channel._display() renders each line with its own prefix."""
    ch = Channel(name="graph", color="#ffaf87")
    ch._display("line 1\nline 2\nline 3")
    assert mock_pft.call_count == 3


def test_channel_label(channel):
    """Channel.label returns '[name]'."""
    assert channel.label == "[py]"


def test_channel_repr(channel):
    """Channel.__repr__ includes name, visibility, and entry count."""
    assert repr(channel) == "Channel('py', visible, 0 entries)"
    channel.write("a")
    assert repr(channel) == "Channel('py', visible, 1 entries)"


def test_channel_repr_hidden(hidden_channel):
    """Channel.__repr__ shows 'hidden' for non-visible channels."""
    assert "hidden" in repr(hidden_channel)


# --- ChannelRouter tests ---


def test_router_register(store):
    """ChannelRouter.register() creates and stores a Channel."""
    r = ChannelRouter()
    ch = r.register("py", "#87ff87", store=store)
    assert isinstance(ch, Channel)
    assert ch.name == "py"
    assert ch.color == "#87ff87"
    assert ch.store is store


def test_router_write_dispatches(router, store):
    """ChannelRouter.write() dispatches to the named channel."""
    router.write("py", "hello", mode="PY")
    store.record.assert_any_call("PY", "py", "output", "hello", None)


def test_router_write_nonexistent_noop(router):
    """ChannelRouter.write() to nonexistent channel is a no-op."""
    router.write("nonexistent", "x")  # should not raise


def test_router_getattr_returns_channel(router):
    """ChannelRouter attribute access returns registered channels."""
    py = router.py
    assert isinstance(py, Channel)
    assert py.name == "py"

    graph = router.graph
    assert isinstance(graph, Channel)
    assert graph.name == "graph"


def test_router_getattr_raises_for_unknown(router):
    """ChannelRouter raises AttributeError for unknown channel names."""
    with pytest.raises(AttributeError, match="No channel 'nonexistent'"):
        router.nonexistent


def test_router_visible(router, store):
    """ChannelRouter.visible returns only visible channel names."""
    router._channels["bash"].visible = False
    visible = router.visible
    assert "bash" not in visible
    assert "py" in visible


def test_router_all(router):
    """ChannelRouter.all returns all channel names."""
    names = router.all
    for name in CHANNEL_DEFAULTS:
        assert name in names


# --- Debug handler tests ---


def test_router_debug_handler_receives_writes(router, tmp_path):
    """Debug handler receives all writes when enabled."""
    enable_debug(router, log_dir=tmp_path)
    router.write("py", "hello debug", mode="PY")
    disable_debug(router)
    log_path = tmp_path / "debug.log"
    assert log_path.exists()
    content = log_path.read_text()
    assert "hello debug" in content


def test_enable_debug_creates_handler(router, tmp_path):
    """enable_debug() attaches a FileHandler to router.debug_handler."""
    enable_debug(router, log_dir=tmp_path)
    assert isinstance(router.debug_handler, logging.FileHandler)
    disable_debug(router)


def test_disable_debug_removes_handler(router, tmp_path):
    """disable_debug() closes and removes the debug_handler."""
    enable_debug(router, log_dir=tmp_path)
    assert router.debug_handler is not None
    disable_debug(router)
    assert router.debug_handler is None


def test_disable_debug_noop_when_not_enabled(router):
    """disable_debug() is safe when no handler exists."""
    disable_debug(router)  # should not raise


# --- CHANNEL_DEFAULTS tests ---


def test_channel_defaults_has_expected_channels():
    """CHANNEL_DEFAULTS contains py, graph, ai, bash, debug."""
    for name in ("py", "graph", "ai", "bash", "debug"):
        assert name in CHANNEL_DEFAULTS


def test_channel_defaults_colors():
    """CHANNEL_DEFAULTS maps channel names to color dicts."""
    assert CHANNEL_DEFAULTS["py"]["color"] == "#87ff87"
    assert CHANNEL_DEFAULTS["graph"]["color"] == "#ffaf87"
    assert CHANNEL_DEFAULTS["ai"]["color"] == "#87d7ff"
    assert CHANNEL_DEFAULTS["bash"]["color"] == "#d7afff"
    assert CHANNEL_DEFAULTS["debug"]["color"] == "#808080"


# --- toggle_channels tests ---


@pytest.mark.asyncio
async def test_toggle_channels_updates_visibility(router):
    """toggle_channels() updates channel visibility from dialog result."""
    # Mock the dialog to return only ["py", "ai"]
    mock_dialog = MagicMock()
    mock_dialog.run_async = AsyncMock(return_value=["py", "ai"])

    with patch("bae.repl.channels.checkboxlist_dialog", return_value=mock_dialog):
        await toggle_channels(router)

    assert router.py.visible is True
    assert router.ai.visible is True
    assert router.graph.visible is False
    assert router.bash.visible is False
    assert router.debug.visible is False


@pytest.mark.asyncio
async def test_toggle_channels_cancelled_no_change(router):
    """toggle_channels() with cancelled dialog (None result) makes no changes."""
    original_visibility = {name: ch.visible for name, ch in router._channels.items()}

    mock_dialog = MagicMock()
    mock_dialog.run_async = AsyncMock(return_value=None)

    with patch("bae.repl.channels.checkboxlist_dialog", return_value=mock_dialog):
        await toggle_channels(router)

    for name, ch in router._channels.items():
        assert ch.visible == original_visibility[name]
