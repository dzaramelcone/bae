"""Quick task workflow -- linear, no loops.

Graph:
    InitQuickTask -> PlanQuickTask -> ExecuteQuickTask -> CommitQuickTask -> QuickTaskDone
"""

from __future__ import annotations

from typing import Annotated

from bae import Effect, Graph, Node, Recall

from bae.work.deps import StateDep, vcs_commit_quick
from bae.work.models import TaskDescription


class InitQuickTask(Node):
    """Entry point: caller provides the task description."""

    task: TaskDescription
    state: StateDep = None

    async def __call__(self) -> PlanQuickTask: ...


class PlanQuickTask(Node):
    """Break the task into steps and identify files to touch."""

    task: Annotated[TaskDescription, Recall()]
    steps: list[str]
    files_to_touch: list[str]

    async def __call__(self) -> ExecuteQuickTask: ...


class ExecuteQuickTask(Node):
    """Execute the planned steps."""

    plan: Annotated[PlanQuickTask, Recall()]
    execution_log: str
    files_changed: list[str]
    success: bool

    async def __call__(self) -> Annotated[CommitQuickTask, Effect(vcs_commit_quick)]: ...


class CommitQuickTask(Node):
    """Commit the changes."""

    execution: Annotated[ExecuteQuickTask, Recall()]
    commit_message: str

    async def __call__(self) -> QuickTaskDone: ...


class QuickTaskDone(Node):
    """Terminal: summarize what was done."""

    summary: str

    async def __call__(self) -> None: ...


quick = Graph(start=InitQuickTask)
