"""New project workflow -- problem validation, structured Q&A, roadmap assembly.

Graph:
    AgreeOnProblem → ExamineProblem ←→ DefendProblem (loop until satisfied)
                           ↓
                     ReviewAlternatives → IdentifyTopics → GatherAnswers
                      ↑ (deps: challenge         ↑               ↓
                         + research)              │       DefineRequirements
                                                  │            ↓
                                                  ├── ReviewRequirements (reject)
                                                  │            ↓
                                                  │      AssembleRoadmap
                                                  │            ↓
                                                  └── ReviewRoadmap (reject)
                                                               ↓
                                                         CommitRoadmap ✎ save
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from bae import Dep, Effect, Graph, Node, Recall

from bae.work.prompt import PromptChoice, PromptDep


# -- Models (graph-local) -----------------------------------------------------


class QuestionOption(BaseModel):
    label: str
    description: str = ""


class Question(BaseModel):
    text: str
    options: list[QuestionOption] = Field(min_length=3, max_length=5)
    multi_select: bool = False


class Topic(BaseModel):
    subject: str
    questions: list[Question] = Field(min_length=3, max_length=5)


class ProjectRoadmap(BaseModel):
    """Structured project roadmap — serialized as JSON for reliable round-tripping."""

    why_not_build: str | None = None
    existing_solutions: list[str] | None = None
    unstated_assumptions: list[str] | None = None
    approaches: list[str] | None = None
    approaches_rationale: str | None = None
    discovery: dict[str, list[str]] | None = None
    functional: list[str] | None = None
    non_functional: list[str] | None = None
    phases: list[dict] | None = None
    summary: str | None = None


# -- Node-as-Dep (LM-filled, resolved concurrently) --------------------------


class ChallengeProject(Node):
    """Help the user avoid building something they don't need."""

    problem: Annotated[ExamineProblem, Recall()]
    why_not_build: str
    existing_solutions: list[str]
    unstated_assumptions: list[str]

    async def __call__(self) -> None: ...


class ResearchAlternatives(Node):
    """Find ways to solve the confirmed problem without building from scratch."""

    problem: Annotated[ExamineProblem, Recall()]
    approaches: list[str]
    rationale: str

    async def __call__(self) -> None: ...


# -- Effect functions ---------------------------------------------------------


async def save_project_roadmap(node) -> None:
    """Write structured project roadmap to .planning/ROADMAP.json."""
    roadmap = ProjectRoadmap(
        why_not_build=node.alternatives.challenge.why_not_build,
        existing_solutions=node.alternatives.challenge.existing_solutions,
        unstated_assumptions=node.alternatives.challenge.unstated_assumptions,
        approaches=node.alternatives.research.approaches,
        approaches_rationale=node.alternatives.research.rationale,
        discovery=node.qa.answers,
        functional=node.reqs.functional,
        non_functional=node.reqs.non_functional,
        phases=node.roadmap.phases,
        summary=node.summary,
    )
    path = Path.cwd() / ".planning" / "ROADMAP.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(roadmap.model_dump_json(indent=2))


# -- Graph nodes --------------------------------------------------------------


class AgreeOnProblem(Node):
    """User states what they want to build and what problem they're dealing with."""

    description: str
    prompt: PromptDep
    stated_problem: str = ""

    async def __call__(self) -> ExamineProblem:
        result = await self.prompt.ask(
            f"You want to: {self.description}\n\n"
            "What is the actual problem you're dealing with?\n"
            "Not the solution you have in mind — the problem itself."
        )
        self.stated_problem = result.text
        return ExamineProblem.model_construct()


class ExamineProblem(Node):
    """Cross-examine the stated problem. LM decides if it's well-stated."""

    context: Annotated[AgreeOnProblem, Recall()]
    probing_questions: list[str] = Field(min_length=2, max_length=5)
    satisfied: bool

    async def __call__(self) -> DefendProblem | ReviewAlternatives:
        if self.satisfied:
            return ReviewAlternatives.model_construct()
        return DefendProblem.model_construct()


class DefendProblem(Node):
    """User answers probing questions about the stated problem."""

    examination: Annotated[ExamineProblem, Recall()]
    prompt: PromptDep
    answers: dict[str, str] = Field(default_factory=dict)

    async def __call__(self) -> ExamineProblem:
        collected: dict[str, str] = {}
        for q in self.examination.probing_questions:
            result = await self.prompt.ask(q)
            collected[q] = result.text
        self.answers = collected
        return ExamineProblem.model_construct()


class ReviewAlternatives(Node):
    """Join parallel challenge and research results."""

    challenge: Annotated[ChallengeProject, Dep()]
    research: Annotated[ResearchAlternatives, Dep()]

    async def __call__(self) -> IdentifyTopics: ...


class IdentifyTopics(Node):
    """Generate structured topics with questions and options."""

    problem: Annotated[AgreeOnProblem, Recall()]
    topics: list[Topic] = Field(min_length=3, max_length=5)

    async def __call__(self) -> GatherAnswers:
        return GatherAnswers.model_construct()


class GatherAnswers(Node):
    """Prompt user through each topic's questions with follow-up."""

    identified: Annotated[IdentifyTopics, Recall()]
    prompt: PromptDep
    answers: dict[str, list[str]] = Field(default_factory=dict)

    async def __call__(self) -> DefineRequirements:
        collected: dict[str, list[str]] = {}
        for topic in self.identified.topics:
            topic_answers: list[str] = []
            for q in topic.questions:
                choices = [
                    PromptChoice(label=o.label, description=o.description) for o in q.options
                ]
                result = await self.prompt.ask(
                    f"[{topic.subject}] {q.text}",
                    choices=choices,
                    multi_select=q.multi_select,
                )
                topic_answers.append(result.text)
                # Follow-up loop for freeform elaboration
                if result.text and result.text not in [o.label for o in q.options]:
                    while True:
                        follow_up = await self.prompt.ask("Anything else to add on this?")
                        if not follow_up.text or follow_up.text.lower() in (
                            "no",
                            "n",
                            "done",
                            "",
                        ):
                            break
                        topic_answers.append(follow_up.text)
            collected[topic.subject] = topic_answers
        self.answers = collected
        return DefineRequirements.model_construct()


class DefineRequirements(Node):
    """Synthesize Q&A into requirements."""

    context: Annotated[GatherAnswers, Recall()]
    functional: list[str]
    non_functional: list[str]

    async def __call__(self) -> ReviewRequirements:
        return ReviewRequirements.model_construct()


class ReviewRequirements(Node):
    """User gate: approve or refine requirements."""

    reqs: Annotated[DefineRequirements, Recall()]
    prompt: PromptDep

    async def __call__(self) -> AssembleRoadmap | IdentifyTopics:
        if await self.prompt.confirm("Approve requirements?"):
            return AssembleRoadmap.model_construct()
        return IdentifyTopics.model_construct()


class AssembleRoadmap(Node):
    """Build phased roadmap from approved requirements."""

    reqs: Annotated[DefineRequirements, Recall()]
    phases: list[dict]

    async def __call__(self) -> ReviewRoadmap:
        return ReviewRoadmap.model_construct()


class ReviewRoadmap(Node):
    """User gate: approve or revise roadmap."""

    roadmap: Annotated[AssembleRoadmap, Recall()]
    prompt: PromptDep

    async def __call__(self) -> Annotated[CommitRoadmap, Effect(save_project_roadmap)] | IdentifyTopics:
        if await self.prompt.confirm("Approve roadmap?"):
            return CommitRoadmap.model_construct()
        return IdentifyTopics.model_construct()


class CommitRoadmap(Node):
    """Terminal: roadmap committed with full project context."""

    alternatives: Annotated[ReviewAlternatives, Recall()]
    qa: Annotated[GatherAnswers, Recall()]
    reqs: Annotated[DefineRequirements, Recall()]
    roadmap: Annotated[AssembleRoadmap, Recall()]
    summary: str

    async def __call__(self) -> None: ...


new_project = Graph(start=AgreeOnProblem)
