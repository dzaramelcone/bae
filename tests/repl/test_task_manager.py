"""Tests for TaskManager lifecycle, process association, revoke, and shutdown."""

from __future__ import annotations

import asyncio
import signal
from unittest.mock import MagicMock, patch

import pytest

from bae.repl.tasks import TaskManager, TaskState, TrackedTask


# --- Fixtures ---

@pytest.fixture
def tm():
    return TaskManager()


# --- TestSubmit ---

class TestSubmit:
    """TaskManager.submit: create, track, auto-transition on completion."""

    @pytest.mark.asyncio
    async def test_submit_returns_tracked_task(self, tm):
        """submit() wraps coroutine in TrackedTask with RUNNING state."""
        async def noop():
            await asyncio.sleep(10)

        tt = tm.submit(noop(), name="test:sub", mode="nl")
        assert isinstance(tt, TrackedTask)
        assert tt.state == TaskState.RUNNING
        assert tt.name == "test:sub"
        assert tt.mode == "nl"
        assert tt.task_id == 1
        tt.task.cancel()
        try:
            await tt.task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_submit_auto_increments_id(self, tm):
        """Each submit() gets a unique, incrementing task_id."""
        async def noop():
            await asyncio.sleep(10)

        tt1 = tm.submit(noop(), name="a", mode="nl")
        tt2 = tm.submit(noop(), name="b", mode="bash")
        assert tt1.task_id == 1
        assert tt2.task_id == 2
        for tt in [tt1, tt2]:
            tt.task.cancel()
            try:
                await tt.task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_done_callback_success(self, tm):
        """Task completing normally transitions state to SUCCESS."""
        async def quick():
            return 42

        tt = tm.submit(quick(), name="ok", mode="nl")
        await tt.task
        assert tt.state == TaskState.SUCCESS

    @pytest.mark.asyncio
    async def test_done_callback_failure(self, tm):
        """Task raising exception transitions state to FAILURE."""
        async def bad():
            raise ValueError("boom")

        tt = tm.submit(bad(), name="err", mode="nl")
        try:
            await tt.task
        except ValueError:
            pass
        assert tt.state == TaskState.FAILURE

    @pytest.mark.asyncio
    async def test_done_callback_revoked(self, tm):
        """Task cancelled via cancel() transitions state to REVOKED."""
        async def slow():
            await asyncio.sleep(100)

        tt = tm.submit(slow(), name="rev", mode="nl")
        tt.task.cancel()
        try:
            await tt.task
        except asyncio.CancelledError:
            pass
        assert tt.state == TaskState.REVOKED


# --- TestRegisterProcess ---

class TestRegisterProcess:
    """TaskManager.register_process: associate subprocess with current asyncio.Task."""

    @pytest.mark.asyncio
    async def test_register_process_associates(self, tm):
        """register_process() from inside a running task sets tt.process."""
        proc = MagicMock()
        captured = {}

        async def worker():
            tm.register_process(proc)
            # Verify it was set
            current = asyncio.current_task()
            captured["process"] = tm._by_asyncio_task[current].process

        tt = tm.submit(worker(), name="proc", mode="bash")
        await tt.task
        assert captured["process"] is proc
        assert tt.process is proc

    @pytest.mark.asyncio
    async def test_register_process_noop_for_untracked(self, tm):
        """register_process() is a no-op if current task is not tracked."""
        proc = MagicMock()
        # Call from outside any tracked task -- should not raise
        tm.register_process(proc)


# --- TestRevoke ---

class TestRevoke:
    """TaskManager.revoke: kill process group, cancel task."""

    @pytest.mark.asyncio
    async def test_revoke_cancels_task(self, tm):
        """revoke() cancels the asyncio.Task and sets state to REVOKED."""
        async def slow():
            await asyncio.sleep(100)

        tt = tm.submit(slow(), name="rev", mode="nl")
        tm.revoke(tt.task_id)
        assert tt.state == TaskState.REVOKED
        assert tt.task.cancelled()
        try:
            await tt.task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_revoke_kills_process_graceful(self, tm):
        """revoke(graceful=True) sends SIGTERM to process group."""
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = None

        async def slow():
            await asyncio.sleep(100)

        tt = tm.submit(slow(), name="rev", mode="bash")
        tt.process = proc

        with patch("bae.repl.tasks.os.getpgid", return_value=12345) as mock_getpgid, \
             patch("bae.repl.tasks.os.killpg") as mock_killpg:
            tm.revoke(tt.task_id, graceful=True)
            mock_getpgid.assert_called_once_with(12345)
            mock_killpg.assert_called_once_with(12345, signal.SIGTERM)

        try:
            await tt.task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_revoke_kills_process_non_graceful(self, tm):
        """revoke(graceful=False) sends SIGKILL to process group."""
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = None

        async def slow():
            await asyncio.sleep(100)

        tt = tm.submit(slow(), name="rev", mode="bash")
        tt.process = proc

        with patch("bae.repl.tasks.os.getpgid", return_value=12345) as mock_getpgid, \
             patch("bae.repl.tasks.os.killpg") as mock_killpg:
            tm.revoke(tt.task_id, graceful=False)
            mock_killpg.assert_called_once_with(12345, signal.SIGKILL)

        try:
            await tt.task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_revoke_no_process_just_cancels(self, tm):
        """revoke() with no associated process just cancels the task."""
        async def slow():
            await asyncio.sleep(100)

        tt = tm.submit(slow(), name="rev", mode="nl")
        assert tt.process is None
        tm.revoke(tt.task_id)
        assert tt.state == TaskState.REVOKED
        try:
            await tt.task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_revoke_dead_process_no_error(self, tm):
        """revoke() handles already-dead process gracefully."""
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = None

        async def slow():
            await asyncio.sleep(100)

        tt = tm.submit(slow(), name="rev", mode="bash")
        tt.process = proc

        with patch("bae.repl.tasks.os.getpgid", side_effect=ProcessLookupError):
            tm.revoke(tt.task_id)  # Should not raise
        assert tt.state == TaskState.REVOKED
        try:
            await tt.task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_id_noop(self, tm):
        """revoke() with unknown task_id is a no-op."""
        tm.revoke(999)  # Should not raise

    @pytest.mark.asyncio
    async def test_revoke_already_done_noop(self, tm):
        """revoke() on a completed task is a no-op."""
        async def quick():
            return 1

        tt = tm.submit(quick(), name="done", mode="nl")
        await tt.task
        assert tt.state == TaskState.SUCCESS
        tm.revoke(tt.task_id)
        assert tt.state == TaskState.SUCCESS  # Not changed


# --- TestRevokeAll ---

class TestRevokeAll:
    """TaskManager.revoke_all: kill all active tasks."""

    @pytest.mark.asyncio
    async def test_revoke_all_kills_all_active(self, tm):
        """revoke_all() revokes every active task."""
        async def slow():
            await asyncio.sleep(100)

        tt1 = tm.submit(slow(), name="a", mode="nl")
        tt2 = tm.submit(slow(), name="b", mode="bash")
        tm.revoke_all(graceful=False)

        assert tt1.state == TaskState.REVOKED
        assert tt2.state == TaskState.REVOKED
        for tt in [tt1, tt2]:
            try:
                await tt.task
            except asyncio.CancelledError:
                pass


# --- TestActive ---

class TestActive:
    """TaskManager.active: list running tasks sorted by ID."""

    @pytest.mark.asyncio
    async def test_active_returns_running_only(self, tm):
        """active() returns only tasks in RUNNING state."""
        async def slow():
            await asyncio.sleep(100)

        async def quick():
            return 1

        tt_slow = tm.submit(slow(), name="slow", mode="nl")
        tt_quick = tm.submit(quick(), name="quick", mode="nl")
        await tt_quick.task  # Completes -> SUCCESS

        active = tm.active()
        assert len(active) == 1
        assert active[0] is tt_slow
        tt_slow.task.cancel()
        try:
            await tt_slow.task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_active_sorted_by_id(self, tm):
        """active() returns tasks in task_id order."""
        async def slow():
            await asyncio.sleep(100)

        tt1 = tm.submit(slow(), name="first", mode="nl")
        tt2 = tm.submit(slow(), name="second", mode="bash")
        tt3 = tm.submit(slow(), name="third", mode="py")

        active = tm.active()
        assert [tt.task_id for tt in active] == [1, 2, 3]

        for tt in [tt1, tt2, tt3]:
            tt.task.cancel()
            try:
                await tt.task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_active_empty_when_all_done(self, tm):
        """active() returns empty list when no tasks are running."""
        async def quick():
            return 1

        tt = tm.submit(quick(), name="done", mode="nl")
        await tt.task
        assert tm.active() == []


# --- TestShutdown ---

class TestShutdown:
    """TaskManager.shutdown: graceful termination and await."""

    @pytest.mark.asyncio
    async def test_shutdown_revokes_and_awaits(self, tm):
        """shutdown() revokes all tasks gracefully and awaits completion."""
        async def slow():
            await asyncio.sleep(100)

        tt1 = tm.submit(slow(), name="a", mode="nl")
        tt2 = tm.submit(slow(), name="b", mode="bash")
        await tm.shutdown()

        assert tt1.state == TaskState.REVOKED
        assert tt2.state == TaskState.REVOKED
        assert tt1.task.done()
        assert tt2.task.done()

    @pytest.mark.asyncio
    async def test_shutdown_empty_noop(self, tm):
        """shutdown() with no tasks does nothing."""
        await tm.shutdown()  # Should not raise
