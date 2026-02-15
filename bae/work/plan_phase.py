"""Plan phase workflow -- revision loop with user gates.

Graph:
    InitPlanPhase -> ValidatePhase -> LoadContext -+-> ResearchPhase -> DraftPlan
                                                   +-> DraftPlan (skip research)
                                                            |
                                                        CheckPlan <--+
                                                          |          |
                                                    +- PresentPlan   |
                                                    +- RevisePlan ---+
"""

from __future__ import annotations

from typing import Annotated

from bae import Effect, Graph, Node, Recall

from bae.work.deps import RoadmapDep, StateDep, save_plan
from bae.work.models import PlanConfig
from bae.work.prompt import BlockersGate


class InitPlanPhase(Node):
    """Entry point: caller provides phase_id and optional config."""

    phase_id: str
    config: PlanConfig = PlanConfig()

    async def __call__(self) -> ValidatePhase: ...


class ValidatePhase(Node):
    """Check that the phase exists and is ready for planning."""

    phase_id: Annotated[str, Recall()]
    state: StateDep
    roadmap: RoadmapDep
    is_valid: bool

    async def __call__(self) -> LoadContext | None: ...


class LoadContext(Node):
    """Load phase requirements and context."""

    config: Annotated[PlanConfig, Recall()]
    state: StateDep
    roadmap: RoadmapDep
    phase_requirements: str

    async def __call__(self) -> ResearchPhase | DraftPlan: ...


class ResearchPhase(Node):
    """Research the domain before planning."""

    state: StateDep
    approved: BlockersGate
    findings: list[str]
    blockers: list[str]

    async def __call__(self) -> DraftPlan | None: ...


class DraftPlan(Node):
    """Draft the phase plan."""

    context: Annotated[LoadContext, Recall()]
    plan_content: str

    async def __call__(self) -> CheckPlan: ...


class CheckPlan(Node):
    """Review the plan for completeness."""

    plan: Annotated[DraftPlan, Recall()]
    issues: list[str]
    passed: bool
    iteration: int = 0

    async def __call__(self) -> Annotated[PresentPlan, Effect(save_plan)] | RevisePlan: ...


class RevisePlan(Node):
    """Revise the plan based on checker feedback."""

    review: Annotated[CheckPlan, Recall()]
    previous_plan: Annotated[DraftPlan, Recall()]
    revised_content: str

    async def __call__(self) -> CheckPlan: ...


class PresentPlan(Node):
    """Terminal: present the final plan."""

    plan: Annotated[DraftPlan, Recall()]
    summary: str

    async def __call__(self) -> None: ...


plan_phase = Graph(start=InitPlanPhase)
