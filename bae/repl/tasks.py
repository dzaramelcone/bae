"""TaskManager: lifecycle-tracked asyncio tasks with process group management."""

from __future__ import annotations

import asyncio
import enum
import os
import signal
from dataclasses import dataclass


class TaskState(enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    REVOKED = "revoked"


@dataclass
class TrackedTask:
    task: asyncio.Task
    name: str
    mode: str
    task_id: int
    state: TaskState = TaskState.RUNNING
    process: asyncio.subprocess.Process | None = None


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[int, TrackedTask] = {}
        self._by_asyncio_task: dict[asyncio.Task, TrackedTask] = {}
        self._next_id = 1

    def submit(self, coro, *, name: str, mode: str) -> TrackedTask:
        task = asyncio.create_task(coro, name=name)
        tt = TrackedTask(task=task, name=name, mode=mode, task_id=self._next_id)
        self._tasks[self._next_id] = tt
        self._by_asyncio_task[task] = tt
        self._next_id += 1
        task.add_done_callback(self._on_done)
        return tt

    def register_process(self, process: asyncio.subprocess.Process) -> None:
        current = asyncio.current_task()
        tt = self._by_asyncio_task.get(current)
        if tt is not None:
            tt.process = process

    def revoke(self, task_id: int, *, graceful: bool = True) -> None:
        tt = self._tasks.get(task_id)
        if tt is None or tt.state != TaskState.RUNNING:
            return
        if tt.process and tt.process.returncode is None:
            self._kill_process(tt.process, graceful)
        tt.task.cancel()
        tt.state = TaskState.REVOKED

    def revoke_all(self, *, graceful: bool = False) -> None:
        for task_id in list(self._tasks):
            self.revoke(task_id, graceful=graceful)

    def active(self) -> list[TrackedTask]:
        return sorted(
            [tt for tt in self._tasks.values() if tt.state == TaskState.RUNNING],
            key=lambda tt: tt.task_id,
        )

    async def shutdown(self) -> None:
        self.revoke_all(graceful=True)
        tasks = [tt.task for tt in self._tasks.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _on_done(self, task: asyncio.Task) -> None:
        tt = self._by_asyncio_task.get(task)
        if tt is None or tt.state != TaskState.RUNNING:
            return
        if task.cancelled():
            tt.state = TaskState.REVOKED
        elif task.exception() is not None:
            tt.state = TaskState.FAILURE
        else:
            tt.state = TaskState.SUCCESS

    @staticmethod
    def _kill_process(process: asyncio.subprocess.Process, graceful: bool) -> None:
        try:
            pgid = os.getpgid(process.pid)
        except (ProcessLookupError, OSError):
            return
        if graceful:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        else:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
