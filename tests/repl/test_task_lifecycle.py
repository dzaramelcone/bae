"""Tests for TaskManager wiring, task menu UX, subprocess cleanup, and toolbar integration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bae.repl.modes import Mode
from bae.repl.shell import CortexShell, _build_key_bindings, _print_task_menu
from bae.repl.tasks import TaskManager
from bae.repl.toolbar import TASKS_PER_PAGE, ToolbarConfig, render_task_menu


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

    _calls = []

    def _create_bg_task(coro):
        _calls.append(coro)
        coro.close()

    event.app.create_background_task = _create_bg_task
    event.app.create_background_task._calls = _calls
    return event


# --- TestSubmit ---

class TestSubmit:
    """TaskManager.submit via CortexShell.tm."""

    @pytest.mark.asyncio
    async def test_submit_creates_tracked_task(self, shell):
        """tm.submit() returns TrackedTask with RUNNING state."""
        async def noop():
            await asyncio.sleep(10)

        tt = shell.tm.submit(noop(), name="test:add", mode="nl")
        assert tt.state.value == "running"
        assert len(shell.tm.active()) == 1
        shell.tm.revoke(tt.task_id)
        try:
            await tt.task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_submit_removes_on_completion(self, shell):
        """After task completes, tm.active() is empty."""
        async def quick():
            return 42

        tt = shell.tm.submit(quick(), name="test:done", mode="nl")
        await tt.task
        # done_callback fires synchronously after await
        assert len(shell.tm.active()) == 0

    @pytest.mark.asyncio
    async def test_submit_sets_name(self, shell):
        """TrackedTask.name matches what was passed to submit."""
        async def noop():
            await asyncio.sleep(10)

        tt = shell.tm.submit(noop(), name="test:foo", mode="nl")
        assert tt.name == "test:foo"
        shell.tm.revoke(tt.task_id)
        try:
            await tt.task
        except asyncio.CancelledError:
            pass


# --- TestInterruptHandler ---

class TestInterruptHandler:
    """Ctrl-C key binding: exit, task menu, kill all."""

    def test_ctrl_c_no_tasks_exits(self, shell):
        """Ctrl-C with no tasks exits the REPL."""
        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        handler = _get_handler(kb, "c-c")
        handler(event)

        event.app.exit.assert_called_once()
        args, kwargs = event.app.exit.call_args
        assert isinstance(kwargs.get("exception") or args[0] if args else None, KeyboardInterrupt) or \
               isinstance(kwargs.get("exception"), KeyboardInterrupt)

    @pytest.mark.asyncio
    async def test_ctrl_c_opens_task_menu(self, shell):
        """Ctrl-C with running tasks sets _task_menu = True."""
        async def sleepy():
            await asyncio.sleep(100)

        shell.tm.submit(sleepy(), name="t1", mode="nl")

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        handler = _get_handler(kb, "c-c")
        handler(event)

        assert shell._task_menu is True
        event.app.invalidate.assert_called()

        # cleanup
        shell.tm.revoke_all(graceful=False)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_ctrl_c_in_menu_kills_all(self, shell):
        """Ctrl-C while task menu open calls tm.revoke_all() and closes menu."""
        async def sleepy():
            await asyncio.sleep(100)

        shell.tm.submit(sleepy(), name="t1", mode="nl")
        shell.tm.submit(sleepy(), name="t2", mode="nl")

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        # Open task menu first
        shell._task_menu = True

        handler = _get_handler(kb, "c-c")
        handler(event)

        assert shell._task_menu is False
        assert len(shell.tm.active()) == 0
        await asyncio.sleep(0)


# --- TestTaskMenu ---

class TestTaskMenu:
    """Task menu rendering, digit cancel, esc dismiss, pagination."""

    def test_toolbar_renders_normal_even_in_menu_mode(self, shell):
        """_task_menu=True -> _toolbar() still returns normal toolbar (menu prints to scrollback)."""
        shell._task_menu = True
        result = shell._toolbar()
        # Normal toolbar always rendered, no "no tasks running" -- that's in scrollback now
        assert len(result) > 0

    def test_toolbar_renders_normal(self, shell):
        """_task_menu=False -> _toolbar() returns normal toolbar."""
        shell._task_menu = False
        result = shell._toolbar()
        # Normal toolbar has mode widget
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_digit_cancels_task(self, shell):
        """With task menu open, digit '1' cancels the first task."""
        async def sleepy():
            await asyncio.sleep(100)

        tt = shell.tm.submit(sleepy(), name="target", mode="nl")
        shell._task_menu = True

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        handler = _get_handler(kb, "1")
        handler(event)

        assert tt.state.value == "revoked"
        # Menu auto-closes when no tasks left
        assert shell._task_menu is False
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_esc_dismisses_menu(self, shell):
        """Esc closes task menu, returns to normal toolbar."""
        shell._task_menu = True

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        handler = _get_handler(kb, "escape")
        handler(event)

        assert shell._task_menu is False

    @pytest.mark.asyncio
    async def test_pagination_left_right(self, shell):
        """With >5 tasks, right increments page, left decrements."""
        async def sleepy():
            await asyncio.sleep(100)

        for i in range(7):
            shell.tm.submit(sleepy(), name=f"t{i}", mode="nl")

        shell._task_menu = True
        shell._task_menu_page = 0

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        # Right arrow -> page 1
        right_handler = _get_handler(kb, "right")
        right_handler(event)
        assert shell._task_menu_page == 1

        # Left arrow -> page 0
        left_handler = _get_handler(kb, "left")
        left_handler(event)
        assert shell._task_menu_page == 0

        # Left at page 0 stays at 0
        left_handler(event)
        assert shell._task_menu_page == 0

        # cleanup
        shell.tm.revoke_all(graceful=False)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    @patch("bae.repl.shell.print_formatted_text")
    async def test_ctrl_c_prints_task_list_to_scrollback(self, mock_pft, shell):
        """Ctrl-C with tasks prints numbered list to scrollback via _print_task_menu."""
        async def sleepy():
            await asyncio.sleep(100)

        shell.tm.submit(sleepy(), name="alpha", mode="nl")
        shell.tm.submit(sleepy(), name="beta", mode="nl")

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        handler = _get_handler(kb, "c-c")
        handler(event)

        # _print_task_menu prints 2 task lines + 1 hint = 3 calls
        assert mock_pft.call_count == 3
        assert shell._task_menu is True

        shell.tm.revoke_all(graceful=False)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    @patch("bae.repl.shell.print_formatted_text")
    async def test_digit_cancel_reprints_remaining(self, mock_pft, shell):
        """After cancelling a task, remaining tasks are reprinted to scrollback."""
        async def sleepy():
            await asyncio.sleep(100)

        shell.tm.submit(sleepy(), name="first", mode="nl")
        shell.tm.submit(sleepy(), name="second", mode="nl")
        shell._task_menu = True

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        handler = _get_handler(kb, "1")
        handler(event)

        # One task cancelled, one remaining -> reprinted (1 task line + 1 hint = 2 calls)
        assert mock_pft.call_count == 2
        assert shell._task_menu is True  # still open, one task left

        shell.tm.revoke_all(graceful=False)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_menu_closes_when_empty(self, shell):
        """After cancelling last task, _task_menu auto-closes."""
        async def sleepy():
            await asyncio.sleep(100)

        shell.tm.submit(sleepy(), name="only", mode="nl")
        shell._task_menu = True

        kb = _build_key_bindings(shell)
        event = _mock_event(shell)

        handler = _get_handler(kb, "1")
        handler(event)

        assert shell._task_menu is False
        assert len(shell.tm.active()) == 0
        await asyncio.sleep(0)


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

        assert len(shell.tm.active()) == 1
        tt = shell.tm.active()[0]
        assert not tt.task.done()
        hold.set()
        await tt.task

    @pytest.mark.asyncio
    async def test_dispatch_py_blocks(self, shell):
        """PY dispatch blocks until execution completes (sync expressions)."""
        shell.mode = Mode.PY
        with patch("bae.repl.shell.async_exec", new_callable=AsyncMock, return_value=(42, "")) as mock_exec:
            await shell._dispatch("1+1")
            mock_exec.assert_awaited_once()
        # Sync PY mode does NOT create tracked tasks
        assert len(shell.tm.active()) == 0

    @pytest.mark.asyncio
    async def test_dispatch_bash_returns_immediately(self, shell):
        """BASH dispatch creates tracked task and returns without awaiting it."""
        hold = asyncio.Event()

        async def slow_bash(text, **kwargs):
            await hold.wait()
            return ("out", "")

        shell.mode = Mode.BASH
        with patch("bae.repl.shell.dispatch_bash", side_effect=slow_bash):
            await shell._dispatch("sleep 10")

        assert len(shell.tm.active()) == 1
        tt = shell.tm.active()[0]
        assert not tt.task.done()
        hold.set()
        await tt.task

    @pytest.mark.asyncio
    async def test_dispatch_py_async_tracked(self, shell):
        """PY async expression (await ...) is tracked via TaskManager."""
        hold = asyncio.Event()
        held = asyncio.Event()

        async def mock_async_exec(code, ns):
            async def long_coro():
                held.set()
                await hold.wait()
                return 99
            return long_coro(), ""

        shell.mode = Mode.PY
        with patch("bae.repl.shell.async_exec", side_effect=mock_async_exec):
            await shell._dispatch("await asyncio.sleep(10)")

        # Should be tracked
        assert len(shell.tm.active()) == 1
        tt = shell.tm.active()[0]
        assert tt.mode == "py"
        assert tt.name.startswith("py:")

        hold.set()
        await tt.task


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
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

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

    def test_shell_has_task_manager(self, shell):
        """shell.tm is a TaskManager instance."""
        assert isinstance(shell.tm, TaskManager)
        assert hasattr(shell, '_task_menu')
        assert hasattr(shell, '_task_menu_page')


# --- TestRenderTaskMenu ---

class TestRenderTaskMenu:
    """render_task_menu() unit tests."""

    @pytest.mark.asyncio
    async def test_empty_tasks(self):
        """No active tasks renders 'no tasks running'."""
        tm = TaskManager()
        result = render_task_menu(tm)
        assert any("no tasks running" in text for _, text in result)

    @pytest.mark.asyncio
    async def test_renders_task_names(self):
        """Active tasks appear as numbered list."""
        tm = TaskManager()
        async def sleepy():
            await asyncio.sleep(100)

        tm.submit(sleepy(), name="alpha", mode="nl")
        tm.submit(sleepy(), name="beta", mode="nl")

        result = render_task_menu(tm)
        texts = " ".join(text for _, text in result)
        assert "1" in texts
        assert "alpha" in texts
        assert "2" in texts
        assert "beta" in texts

        tm.revoke_all(graceful=False)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_pagination_indicator(self):
        """More than TASKS_PER_PAGE tasks shows pagination indicator."""
        tm = TaskManager()
        async def sleepy():
            await asyncio.sleep(100)

        for i in range(7):
            tm.submit(sleepy(), name=f"t{i}", mode="nl")

        result = render_task_menu(tm, page=0)
        texts = " ".join(text for _, text in result)
        assert "1/2" in texts

        tm.revoke_all(graceful=False)
        await asyncio.sleep(0)


# --- Helpers ---

def _get_handler(kb, key):
    """Extract the handler for a single-key binding from a KeyBindings object.

    Matches bindings where the entire key sequence is exactly [key].
    For multi-key sequences like ("escape", "enter"), use the full tuple.
    """
    for binding in kb.bindings:
        keys = [k.value if hasattr(k, 'value') else str(k) for k in binding.keys]
        if keys == [key]:
            return binding.handler
    raise ValueError(f"No binding for {key!r}")
