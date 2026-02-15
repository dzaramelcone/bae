"""Integration test for new_project graph with mock LM and prompt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bae.work.new_project import (
    AgreeOnProblem,
    AssembleRoadmap,
    ChallengeProject,
    CommitRoadmap,
    DefendProblem,
    DefineRequirements,
    ExamineProblem,
    GatherAnswers,
    IdentifyTopics,
    Question,
    QuestionOption,
    ResearchAlternatives,
    ReviewAlternatives,
    ReviewRequirements,
    ReviewRoadmap,
    Topic,
    new_project,
)
from bae.work.prompt import PromptResult


# -- Test doubles --------------------------------------------------------------


class FakePrompt:
    """Pre-loaded prompt responses for deterministic testing."""

    def __init__(self, ask_responses: list[PromptResult], confirm_responses: list[bool]):
        self._asks = iter(ask_responses)
        self._confirms = iter(confirm_responses)
        self.ask_calls: list[str] = []
        self.confirm_calls: list[str] = []

    async def ask(self, question, *, choices=None, multi_select=False):
        self.ask_calls.append(question)
        return next(self._asks)

    async def confirm(self, message):
        self.confirm_calls.append(message)
        return next(self._confirms)


def _make_topics() -> list[Topic]:
    """Minimal valid topics (3 topics, 3 questions each, 3 options each)."""
    def _topic(name: str) -> Topic:
        return Topic(
            subject=name,
            questions=[
                Question(
                    text=f"{name} q{i}?",
                    options=[
                        QuestionOption(label=f"{name}_opt{i}_{j}")
                        for j in range(3)
                    ],
                )
                for i in range(3)
            ],
        )
    return [_topic("arch"), _topic("testing"), _topic("deploy")]


class MockLM:
    """Mock LM that merges resolved fields with pre-configured mock data."""

    def __init__(self, fills: dict[type, dict]):
        self.fills = fills
        self.fill_calls: list[type] = []
        self.choose_type_calls: list[list[type]] = []

    async def choose_type(self, types, context):
        self.choose_type_calls.append(types)
        return types[0]

    async def fill(self, target, resolved, instruction, source=None):
        self.fill_calls.append(target)
        mock_fields = self.fills.get(target, {})
        return target.model_construct(**{**resolved, **mock_fields})

    async def make(self, node, target):
        raise NotImplementedError

    async def decide(self, node):
        raise NotImplementedError


# -- Tests ---------------------------------------------------------------------


class TestNewProjectHappyPath:
    """Full graph: agree → examine (satisfied) → research → topics → Q&A → reqs → roadmap."""

    @pytest.fixture
    def topics(self):
        return _make_topics()

    @pytest.fixture
    def prompt(self, topics):
        """FakePrompt with responses for:
        1. AgreeOnProblem: state the problem
        2. GatherAnswers: 3 topics x 3 questions = 9 selections
        """
        ask_responses = [
            # AgreeOnProblem: state the real problem
            PromptResult(text="Team loses track of tasks across repos, no visibility into who's working on what"),
            # GatherAnswers: 9 questions, each selects first option label
            *[
                PromptResult(text=f"{t.subject}_opt{i}_0")
                for t in topics
                for i in range(3)
            ],
        ]
        # 2 independent gates: ReviewRequirements + ReviewRoadmap
        confirm_responses = [True, True]
        return FakePrompt(ask_responses, confirm_responses)

    @pytest.fixture
    def lm(self, topics):
        return MockLM(fills={
            # ExamineProblem: LM satisfied on first round (no defend loop)
            ExamineProblem: {
                "probing_questions": ["How did this problem start?", "What have you tried?"],
                "satisfied": True,
            },
            # Node-as-Dep: LM fills these concurrently for ReviewAlternatives
            ChallengeProject: {
                "why_not_build": "Linear is $8/seat and does exactly this",
                "existing_solutions": ["Linear", "Jira", "GitHub Projects"],
                "unstated_assumptions": ["Team will adopt a new tool", "Kanban is the right model"],
            },
            ResearchAlternatives: {
                "approaches": ["Use Linear", "GitHub Projects + automation", "Build custom"],
                "rationale": "Off-the-shelf covers 90% of needs for a 5-person team",
            },
            # ReviewAlternatives → make IdentifyTopics (LM fills topics)
            IdentifyTopics: {"topics": topics},
            # GatherAnswers → partial fill DefineRequirements
            DefineRequirements: {
                "functional": ["user auth", "data export"],
                "non_functional": ["< 200ms p95", "99.9% uptime"],
            },
            # ReviewRequirements → partial fill AssembleRoadmap
            AssembleRoadmap: {
                "phases": [
                    {"name": "foundation", "tasks": ["setup", "auth"]},
                    {"name": "features", "tasks": ["export", "dashboard"]},
                ],
            },
            # ReviewRoadmap → partial fill CommitRoadmap
            CommitRoadmap: {"summary": "Project roadmap complete."},
        })

    async def test_full_trace(self, prompt, lm, monkeypatch, tmp_path):
        monkeypatch.setattr("bae.work.prompt._prompt", prompt)
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

        result = await new_project.arun(
            AgreeOnProblem.model_construct(description="Build a task tracker"),
            lm=lm,
            max_iters=30,
        )

        trace_types = [n.__class__.__name__ for n in result.trace]
        assert trace_types == [
            "AgreeOnProblem",
            "ExamineProblem",
            "ReviewAlternatives",
            "IdentifyTopics",
            "GatherAnswers",
            "DefineRequirements",
            "ReviewRequirements",
            "AssembleRoadmap",
            "ReviewRoadmap",
            "CommitRoadmap",
        ]

    async def test_problem_stated(self, prompt, lm, monkeypatch, tmp_path):
        monkeypatch.setattr("bae.work.prompt._prompt", prompt)
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

        result = await new_project.arun(
            AgreeOnProblem.model_construct(description="Build a task tracker"),
            lm=lm,
            max_iters=30,
        )

        agree = result.trace[0]
        assert isinstance(agree, AgreeOnProblem)
        assert "loses track" in agree.stated_problem

        examine = result.trace[1]
        assert isinstance(examine, ExamineProblem)
        assert examine.satisfied is True
        assert len(examine.probing_questions) == 2

    async def test_challenge_fields(self, prompt, lm, monkeypatch, tmp_path):
        monkeypatch.setattr("bae.work.prompt._prompt", prompt)
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

        result = await new_project.arun(
            AgreeOnProblem.model_construct(description="Build a task tracker"),
            lm=lm,
            max_iters=30,
        )

        review_alt = result.trace[2]
        assert isinstance(review_alt, ReviewAlternatives)
        assert "Linear" in review_alt.challenge.why_not_build
        assert "Linear" in review_alt.challenge.existing_solutions
        assert len(review_alt.challenge.unstated_assumptions) == 2
        assert len(review_alt.research.approaches) == 3

    async def test_partial_fill(self, prompt, lm, monkeypatch, tmp_path):
        """DefineRequirements is partially constructed by GatherAnswers.__call__,
        then LM fills the remaining plain fields (functional, non_functional)."""
        monkeypatch.setattr("bae.work.prompt._prompt", prompt)
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

        result = await new_project.arun(
            AgreeOnProblem.model_construct(description="Build a task tracker"),
            lm=lm,
            max_iters=30,
        )

        reqs = result.trace[5]
        assert isinstance(reqs, DefineRequirements)
        assert reqs.functional == ["user auth", "data export"]
        assert reqs.non_functional == ["< 200ms p95", "99.9% uptime"]
        assert isinstance(reqs.context, GatherAnswers)

    async def test_roadmap_json_written(self, prompt, lm, monkeypatch, tmp_path):
        monkeypatch.setattr("bae.work.prompt._prompt", prompt)
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

        await new_project.arun(
            AgreeOnProblem.model_construct(description="Build a task tracker"),
            lm=lm,
            max_iters=30,
        )

        roadmap_path = tmp_path / ".planning" / "ROADMAP.json"
        assert roadmap_path.exists()

        data = json.loads(roadmap_path.read_text())
        assert "Linear" in data["why_not_build"]
        assert "Linear" in data["existing_solutions"]
        assert len(data["unstated_assumptions"]) == 2
        assert len(data["approaches"]) == 3
        assert data["functional"] == ["user auth", "data export"]
        assert data["non_functional"] == ["< 200ms p95", "99.9% uptime"]
        assert len(data["phases"]) == 2
        assert data["summary"] == "Project roadmap complete."
        assert set(data["discovery"].keys()) == {"arch", "testing", "deploy"}

    async def test_prompt_calls(self, prompt, lm, monkeypatch, tmp_path):
        monkeypatch.setattr("bae.work.prompt._prompt", prompt)
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

        await new_project.arun(
            AgreeOnProblem.model_construct(description="Build a task tracker"),
            lm=lm,
            max_iters=30,
        )

        # 1 problem statement + 9 Q&A = 10 ask calls
        assert len(prompt.ask_calls) == 10
        assert "actual problem" in prompt.ask_calls[0].lower()
        assert "[arch]" in prompt.ask_calls[1]

        # 2 independent confirm calls (requirements + roadmap)
        assert len(prompt.confirm_calls) == 2
        assert "requirements" in prompt.confirm_calls[0].lower()
        assert "roadmap" in prompt.confirm_calls[1].lower()

    async def test_lm_calls_minimal(self, prompt, lm, monkeypatch, tmp_path):
        """Only 7 LM fills, no choose_type calls — deterministic routing."""
        monkeypatch.setattr("bae.work.prompt._prompt", prompt)
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

        await new_project.arun(
            AgreeOnProblem.model_construct(description="Build a task tracker"),
            lm=lm,
            max_iters=30,
        )

        assert lm.fill_calls == [
            ExamineProblem,          # partial fill from AgreeOnProblem
            ChallengeProject,        # Node-as-Dep
            ResearchAlternatives,    # Node-as-Dep
            IdentifyTopics,          # make from ReviewAlternatives
            DefineRequirements,      # partial fill from GatherAnswers
            AssembleRoadmap,         # partial fill from ReviewRequirements
            CommitRoadmap,           # partial fill from ReviewRoadmap
        ]
        assert lm.choose_type_calls == []


class TestExaminationLoop:
    """ExamineProblem → DefendProblem → ExamineProblem loop when not satisfied."""

    @pytest.fixture
    def topics(self):
        return _make_topics()

    @pytest.fixture
    def prompt(self, topics):
        ask_responses = [
            # AgreeOnProblem: vague problem statement
            PromptResult(text="We need better project management"),
            # DefendProblem round 1: answer 2 probing questions
            PromptResult(text="Started when we hit 5 devs"),
            PromptResult(text="Tried Trello but it didn't stick"),
            # GatherAnswers: 9 questions
            *[
                PromptResult(text=f"{t.subject}_opt{i}_0")
                for t in topics
                for i in range(3)
            ],
        ]
        confirm_responses = [True, True]
        return FakePrompt(ask_responses, confirm_responses)

    @pytest.fixture
    def lm(self, topics):
        """ExamineProblem filled twice: first unsatisfied, then satisfied."""
        fill_count = {"ExamineProblem": 0}

        class LoopingMockLM(MockLM):
            async def fill(self, target, resolved, instruction, source=None):
                self.fill_calls.append(target)
                if target is ExamineProblem:
                    fill_count["ExamineProblem"] += 1
                    if fill_count["ExamineProblem"] == 1:
                        # First round: not satisfied, ask probing questions
                        return target.model_construct(**{
                            **resolved,
                            "probing_questions": ["How did this problem start?", "What have you tried?"],
                            "satisfied": False,
                        })
                    else:
                        # Second round: satisfied after hearing answers
                        return target.model_construct(**{
                            **resolved,
                            "probing_questions": ["Confirmed?"],
                            "satisfied": True,
                        })
                mock_fields = self.fills.get(target, {})
                return target.model_construct(**{**resolved, **mock_fields})

        return LoopingMockLM(fills={
            ChallengeProject: {
                "why_not_build": "Linear exists",
                "existing_solutions": ["Linear"],
                "unstated_assumptions": ["Team will adopt it"],
            },
            ResearchAlternatives: {
                "approaches": ["Use Linear"],
                "rationale": "Cheaper",
            },
            IdentifyTopics: {"topics": topics},
            DefineRequirements: {
                "functional": ["task boards"],
                "non_functional": ["fast"],
            },
            AssembleRoadmap: {"phases": [{"name": "mvp", "tasks": ["setup"]}]},
            CommitRoadmap: {"summary": "Done."},
        })

    async def test_defend_loop(self, prompt, lm, monkeypatch, tmp_path):
        monkeypatch.setattr("bae.work.prompt._prompt", prompt)
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: tmp_path))

        result = await new_project.arun(
            AgreeOnProblem.model_construct(description="Build a task tracker"),
            lm=lm,
            max_iters=30,
        )

        trace_types = [n.__class__.__name__ for n in result.trace]
        assert trace_types == [
            "AgreeOnProblem",
            "ExamineProblem",       # round 1: not satisfied
            "DefendProblem",        # user answers probing questions
            "ExamineProblem",       # round 2: satisfied
            "ReviewAlternatives",
            "IdentifyTopics",
            "GatherAnswers",
            "DefineRequirements",
            "ReviewRequirements",
            "AssembleRoadmap",
            "ReviewRoadmap",
            "CommitRoadmap",
        ]

        # DefendProblem captured answers
        defend = result.trace[2]
        assert isinstance(defend, DefendProblem)
        assert len(defend.answers) == 2
        assert "Started when we hit 5 devs" in defend.answers.values()
