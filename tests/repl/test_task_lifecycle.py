"""Tests for task tracking, interrupt routing, subprocess cleanup, and toolbar wiring."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bae.repl.modes import Mode
from bae.repl.shell import CortexShell, DOUBLE_PRESS_THRESHOLD, _build_key_bindings, _show_kill_menu
from bae.repl.toolbar import ToolbarConfig


# --- Fixtures ---

@pytest.fixture
def shell():
    """A CortexShell constructed with mocked externals."""
    with patch("bae.repl.shell.SessionStore"), \
         patch("bae.repl.shell.PromptSession"), \
         patch("bae.repl.shell.NamespaceCompleter"), \
         patch("bae.lm.ClaudeCLIBackend"):
        s = CortexShell()
    return s


def _mock_event(shell):
    """Build a mock prompt_toolkit event for key binding tests."""
    event = MagicMock()
    event.app.exit = MagicMock()
    event.app.invalidate = MagicMock()
    event.current_buffer.reset = MagicMock()

    # Wrap create_background_task: track calls AND close coroutines to suppress warnings
    _calls = []

    def _create_bg_task(coro):
        _calls.append(coro)
        coro.close()

    event.app.create_background_task = _create_bg_task
    event.app.create_background_task._calls = _calls
    return event


# --- TestTrackTask ---

class TestTrackTask:
    """_track_task: register, auto-remove, naming."""

    @pytest.mark.asyncio
    async def test_track_task_adds_to_set(self, shell):
        """Tracked task appears in shell.tasks immediately."""
        async def noop():
            await asyncio.sleep(10)

        task = shell._track_task(noop(), name="test:add")
        assert task in shell.tasks
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_track_task_removes_on_completion(self, shell):
        """Task removed from shell.tasks after it completes."""
        async def quick():
            return 42

        task = shell._track_task(quick(), name="test:done")
        await task
        # done_callback fires synchronously after await
        assert task not in shell.tasks

    @pytest.mark.asyncio
    async def test_track_task_sets_name(self, shell):
        """Task gets the name passed to _track_task."""
        async def noop():
            await asyncio.sleep(10)

        task = shell._track_task(noop(), name="test:foo")
        assert task.get_name() == "test:foo"
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# --- TestInterruptHandler ---

class TestInterruptHandler:
    """Ctrl-C key binding: exit, kill menu, double-press kill all."""

    def test_ctrl_c_no_tasks_exits(self, shell):
        """Ctrl-C with no tasks exits the REPL (preserves REPL-12)."""
        kb = _build_key_bindings(shell)
        event = _mock_event(shell)
        shell.tasks = set()

        # Find and call the c-c handler
        handler = _get_handler(kb, "c-c")
        handler(event)

        event.app.exit.assert_called_once()
        args, kwargs = event.app.exit.call_args
        assert isinstance(kwargs.get("exception") or args[0] if args else None, KeyboardInterrupt) or \
               isinstance(kwargs.get("exception"), KeyboardInterrupt)

    def test_ctrl_c_with_tasks_shows_menu(self, shell):
        """Ctrl-C with running tasks opens kill menu dialog."""
        kb = _build_key_bindings(shell)
        event = _mock_event(shell)
        shell.tasks = {MagicMock()}

        handler = _get_handler(kb, "c-c")
        handler(event)

        assert len(event.app.create_background_task._calls) == 1

    @pytest.mark.asyncio
    async def test_double_ctrl_c_kills_all(self, shell):
        """Double Ctrl-C within threshold cancels all tracked tasks."""
        async def sleepy():
            await asyncio.sleep(100)

        t1 = shell._track_task(sleepy(), name="t1")
        t2 = shell._track_task(sleepy(), name="t2")

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        handler = _get_handler(kb, "c-c")
        # First press -- opens menu (or sets timestamp)
        handler(event)
        # Second press within threshold -- kills all
        handler(event)

        # Let event loop process cancellations
        await asyncio.sleep(0)

        assert t1.cancelled()
        assert t2.cancelled()
        # Clean up
        for t in [t1, t2]:
            try:
                await t
            except asyncio.CancelledError:
                pass


# --- TestBackgroundDispatch ---

class TestBackgroundDispatch:
    """NL/GRAPH/BASH dispatch as fire-and-forget background tasks; PY blocks."""

    @pytest.mark.asyncio
    async def test_dispatch_nl_returns_immediately(self, shell):
        """NL dispatch creates tracked task and returns without awaiting it."""
        started = asyncio.Event()
        hold = asyncio.Event()

        async def slow_ai(prompt):
            started.set()
            await hold.wait()

        shell.ai = slow_ai
        shell.mode = Mode.NL
        await shell._dispatch("hello world")

        # _dispatch returned but the task hasn't finished
        assert len(shell.tasks) == 1
        task = next(iter(shell.tasks))
        assert not task.done()
        # Let it finish
        hold.set()
        await task

    @pytest.mark.asyncio
    async def test_dispatch_py_blocks(self, shell):
        """PY dispatch blocks until execution completes."""
        shell.mode = Mode.PY
        with patch("bae.repl.shell.async_exec", new_callable=AsyncMock, return_value=(42, "")) as mock_exec:
            await shell._dispatch("1+1")
            mock_exec.assert_awaited_once()
        # PY mode does NOT create tracked tasks
        assert len(shell.tasks) == 0

    @pytest.mark.asyncio
    async def test_dispatch_bash_returns_immediately(self, shell):
        """BASH dispatch creates tracked task and returns without awaiting it."""
        hold = asyncio.Event()

        async def slow_bash(text):
            await hold.wait()
            return ("out", "")

        shell.mode = Mode.BASH
        with patch("bae.repl.shell.dispatch_bash", side_effect=slow_bash):
            await shell._dispatch("sleep 10")

        assert len(shell.tasks) == 1
        task = next(iter(shell.tasks))
        assert not task.done()
        hold.set()
        await task


# --- TestSubprocessCleanup ---

class TestSubprocessCleanup:
    """CancelledError kills child processes instead of orphaning them."""

    @pytest.mark.asyncio
    async def test_ai_kills_process_on_cancel(self):
        """AI.__call__ kills subprocess when cancelled."""
        from bae.repl.ai import AI

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.CancelledError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        router = MagicMock()
        ns = {}
        ai = AI(lm=MagicMock(), router=router, namespace=ns)

        with patch("bae.repl.ai.asyncio.create_subprocess_exec", return_value=mock_proc):
            task = asyncio.create_task(ai("test"))
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        mock_proc.kill.assert_called()

    @pytest.mark.asyncio
    async def test_ai_cancellation_checkpoint(self):
        """AI response suppressed when task cancelled during subprocess completion race."""
        from bae.repl.ai import AI

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"response text", b""))
        mock_proc.returncode = 0

        router = MagicMock()
        ns = {}
        ai = AI(lm=MagicMock(), router=router, namespace=ns)

        with patch("bae.repl.ai.asyncio.create_subprocess_exec", return_value=mock_proc):
            task = asyncio.create_task(ai("test"))
            # Let communicate() complete, then cancel before sleep(0) checkpoint
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        # Router.write should NOT have been called with response metadata
        for call in router.write.call_args_list:
            _, kwargs = call
            meta = kwargs.get("metadata", {})
            assert meta.get("type") != "response", "Response was written despite cancellation"

    @pytest.mark.asyncio
    async def test_bash_kills_process_on_cancel(self):
        """dispatch_bash kills subprocess when cancelled."""
        from bae.repl.bash import dispatch_bash

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.CancelledError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("bae.repl.bash.asyncio.create_subprocess_shell", return_value=mock_proc):
            task = asyncio.create_task(dispatch_bash("sleep 100"))
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        mock_proc.kill.assert_called()


# --- TestShellToolbar ---

class TestShellToolbar:
    """Toolbar integration in CortexShell."""

    def test_shell_has_toolbar_in_namespace(self, shell):
        """CortexShell seeds namespace with toolbar as ToolbarConfig."""
        assert "toolbar" in shell.namespace
        assert isinstance(shell.namespace["toolbar"], ToolbarConfig)

    def test_toolbar_has_builtin_widgets(self, shell):
        """Toolbar has mode, tasks, and cwd widgets registered."""
        assert "mode" in shell.toolbar.widgets
        assert "tasks" in shell.toolbar.widgets
        assert "cwd" in shell.toolbar.widgets

    def test_toolbar_is_toolbar_config(self, shell):
        """shell.toolbar is ToolbarConfig instance."""
        assert isinstance(shell.toolbar, ToolbarConfig)


# --- TestKillMenu ---

class TestKillMenu:
    """_show_kill_menu async dialog."""

    @pytest.mark.asyncio
    async def test_kill_menu_empty_tasks_returns_early(self, shell):
        """Kill menu with no tasks returns without showing dialog."""
        shell.tasks = set()
        # Should not raise or hang
        await _show_kill_menu(shell)

    @pytest.mark.asyncio
    async def test_kill_menu_cancelled_dialog_no_crash(self, shell):
        """Kill menu handles cancelled dialog (None result)."""
        async def sleepy():
            await asyncio.sleep(100)

        task = shell._track_task(sleepy(), name="test:menu")

        with patch("prompt_toolkit.shortcuts.checkboxlist_dialog") as mock_dialog:
            mock_dialog.return_value.run_async = AsyncMock(return_value=None)
            await _show_kill_menu(shell)

        # Task should NOT be cancelled (dialog was dismissed)
        assert not task.cancelled()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# --- Helpers ---

def _get_handler(kb, key):
    """Extract the handler for a key from a KeyBindings object."""
    for binding in kb.bindings:
        if any(k.value == key if hasattr(k, 'value') else str(k) == key for k in binding.keys):
            return binding.handler
    raise ValueError(f"No binding for {key!r}")
