"""Execute phase workflow -- wave-based parallelism with checkpoints.

Graph:
    InitExecute -> ValidateExecution -> ExecuteWave -> SpotCheck -+-> HandleFailures -> WaveGate
                                            ^                    +-> WaveGate
                                            +------------------------+  (next wave)
                                                                     |
                                                               VerifyGoal -> UpdateRoadmap
"""

from __future__ import annotations

from typing import Annotated

from bae import Effect, Graph, Node, Recall

from bae.work.deps import StateDep, save_roadmap_status
from bae.work.models import PlanTask, WaveResult
from bae.work.prompt import FailuresGate


class InitExecute(Node):
    """Entry point: specify phase to execute."""

    phase_id: str
    state: StateDep = None

    async def __call__(self) -> ValidateExecution: ...


class ValidateExecution(Node):
    """Validate that plans exist and are ready."""

    phase_id: Annotated[str, Recall()]
    plans: list[PlanTask]
    is_valid: bool

    async def __call__(self) -> ExecuteWave | None: ...


class ExecuteWave(Node):
    """Execute all plans in a wave concurrently."""

    wave_number: int
    plans: list[PlanTask]
    total_waves: int

    async def __call__(self) -> SpotCheck: ...


class SpotCheck(Node):
    """Spot-check wave results."""

    wave_result: WaveResult
    total_waves: int
    assessment: str
    issues: list[str]

    async def __call__(self) -> HandleFailures | WaveGate: ...


class HandleFailures(Node):
    """User decides how to handle wave failures."""

    wave_result: Annotated[WaveResult, Recall()]
    approved: FailuresGate

    async def __call__(self) -> WaveGate | None: ...


class WaveGate(Node):
    """Checkpoint between waves. Routes to next wave or verification."""

    wave_number: int
    total_waves: int

    async def __call__(self) -> ExecuteWave | VerifyGoal: ...


class VerifyGoal(Node):
    """Verify that the phase goal was achieved."""

    state: StateDep
    goal_met: bool
    gaps: list[str]

    async def __call__(self) -> Annotated[UpdateRoadmap, Effect(save_roadmap_status)]: ...


class UpdateRoadmap(Node):
    """Terminal: update roadmap with phase status."""

    verification: Annotated[VerifyGoal, Recall()]

    async def __call__(self) -> None: ...


execute_phase = Graph(start=InitExecute)
