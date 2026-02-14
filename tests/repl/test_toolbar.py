"""Tests for ToolbarConfig and built-in toolbar widgets."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from bae.repl.toolbar import (
    ToolbarConfig,
    make_cwd_widget,
    make_mode_widget,
    make_tasks_widget,
)
from bae.repl.modes import Mode


# --- ToolbarConfig tests ---


class TestToolbarConfig:
    """ToolbarConfig: add/remove/render/widgets/repr."""

    def test_add_registers_widget(self):
        cfg = ToolbarConfig()
        fn = lambda: [("", "x")]
        cfg.add("x", fn)
        assert "x" in cfg.widgets

    def test_add_replaces_existing(self):
        cfg = ToolbarConfig()
        fn1 = lambda: [("", "a")]
        fn2 = lambda: [("", "b")]
        cfg.add("x", fn1)
        cfg.add("x", fn2)
        assert cfg.render() == [("", "b")]
        assert cfg.widgets == ["x"]  # order unchanged, not duplicated

    def test_remove_unregisters(self):
        cfg = ToolbarConfig()
        cfg.add("x", lambda: [("", "x")])
        cfg.remove("x")
        assert "x" not in cfg.widgets

    def test_remove_nonexistent_noop(self):
        cfg = ToolbarConfig()
        cfg.remove("x")  # should not raise

    def test_render_returns_flat_tuples(self):
        cfg = ToolbarConfig()
        cfg.add("a", lambda: [("", "a")])
        cfg.add("b", lambda: [("", "b")])
        assert cfg.render() == [("", "a"), ("", "b")]

    def test_render_preserves_order(self):
        cfg = ToolbarConfig()
        cfg.add("a", lambda: [("s1", "first")])
        cfg.add("b", lambda: [("s2", "second")])
        result = cfg.render()
        assert result == [("s1", "first"), ("s2", "second")]

    def test_render_catches_exception(self):
        cfg = ToolbarConfig()

        def bad():
            raise ValueError("boom")

        cfg.add("bad", bad)
        result = cfg.render()
        assert result == [("fg:red", " [bad:err] ")]

    def test_render_empty(self):
        cfg = ToolbarConfig()
        assert cfg.render() == []

    def test_widgets_property(self):
        cfg = ToolbarConfig()
        cfg.add("a", lambda: [])
        cfg.add("b", lambda: [])
        assert cfg.widgets == ["a", "b"]

    def test_repr(self):
        cfg = ToolbarConfig()
        cfg.add("mode", lambda: [])
        cfg.add("cwd", lambda: [])
        r = repr(cfg)
        assert "mode" in r
        assert "cwd" in r


# --- Built-in widget tests ---


class TestBuiltinWidgets:
    """Factory functions that produce toolbar widgets."""

    def test_make_mode_widget(self):
        shell = MagicMock()
        shell.mode = Mode.PY
        widget = make_mode_widget(shell)
        assert widget() == [("class:toolbar.mode", " PY ")]

    def test_make_tasks_widget_empty(self):
        shell = MagicMock()
        shell.tasks = set()
        widget = make_tasks_widget(shell)
        assert widget() == []

    def test_make_tasks_widget_with_tasks(self):
        shell = MagicMock()
        shell.tasks = {MagicMock(), MagicMock()}
        widget = make_tasks_widget(shell)
        assert widget() == [("class:toolbar.tasks", " 2 tasks ")]

    def test_make_tasks_widget_singular(self):
        shell = MagicMock()
        shell.tasks = {MagicMock()}
        widget = make_tasks_widget(shell)
        assert widget() == [("class:toolbar.tasks", " 1 task ")]

    def test_make_cwd_widget(self):
        widget = make_cwd_widget()
        with patch("bae.repl.toolbar.os.getcwd", return_value="/Users/dz/lab/bae"), \
             patch("bae.repl.toolbar.os.path.expanduser", return_value="/Users/dz"):
            assert widget() == [("class:toolbar.cwd", " ~/lab/bae ")]
