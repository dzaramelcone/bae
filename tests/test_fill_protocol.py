"""Tests for the fill() JSON structured output protocol.

Verifies:
- ClaudeCLIBackend.fill() sends prompt and uses JSON schema
- Graph.run() resolves target deps before fill()
- fill() receives source node and resolved dict
"""

from __future__ import annotations

from typing import Annotated
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel, HttpUrl

from bae.graph import Graph, _build_instruction
from bae.lm import ClaudeCLIBackend
from bae.markers import Dep
from bae.node import Node
from bae.result import GraphResult


# ── Test types (mirrors ootd.py structure) ─────────────────────────────


class Weather(BaseModel):
    temp: float
    conditions: str


class Location(BaseModel):
    name: str
    lat: float


def get_weather() -> Weather:
    return Weather(temp=72.0, conditions="rainy")


def get_location() -> Location:
    return Location(name="Seattle", lat=47.6)


WeatherDep = Annotated[Weather, Dep(get_weather)]
LocationDep = Annotated[Location, Dep(get_location)]


class Vibe(BaseModel):
    mood: str
    cues: str


class StartNode(Node):
    user_message: str

    async def __call__(self) -> MiddleNode: ...


class MiddleNode(Node):
    weather: WeatherDep
    location: LocationDep
    vibe: Vibe

    async def __call__(self) -> EndNode: ...


class EndNode(Node):
    """Final recommendation."""

    top: str
    bottom: str

    async def __call__(self) -> None: ...


# ── Prompt structure tests ─────────────────────────────────────────────


class TestPromptStructure:
    """fill() prompt includes source context, resolved deps, and instruction."""

    async def test_cli_fill_sends_prompt_with_source_and_context(self):
        """ClaudeCLIBackend.fill() sends source + context + instruction in prompt."""
        backend = ClaudeCLIBackend()
        source = StartNode(user_message="ugh i just got up")
        resolved = {
            "weather": Weather(temp=72.0, conditions="rainy"),
            "location": Location(name="Seattle", lat=47.6),
        }

        captured_args = {}

        async def capture_cli(prompt, schema, **kwargs):
            captured_args["prompt"] = prompt
            captured_args["schema"] = schema
            return {"vibe": {"mood": "groggy", "cues": "just woke up"}}

        with patch.object(backend, "_run_cli_json", side_effect=capture_cli):
            await backend.fill(MiddleNode, resolved, "MiddleNode", source=source)

        prompt = captured_args["prompt"]

        # Source node data
        assert "Input data:" in prompt
        assert "ugh i just got up" in prompt

        # Resolved deps as context
        assert "Context:" in prompt

        # Instruction
        assert "MiddleNode" in prompt

    async def test_cli_fill_uses_json_schema(self):
        """ClaudeCLIBackend.fill() passes JSON schema from plain model."""
        backend = ClaudeCLIBackend()
        resolved: dict = {}

        captured_args = {}

        async def capture_cli(prompt, schema, **kwargs):
            captured_args["schema"] = schema
            return {"top": "Navy sweater", "bottom": "Chinos"}

        with patch.object(backend, "_run_cli_json", side_effect=capture_cli):
            await backend.fill(EndNode, resolved, "EndNode")

        schema = captured_args["schema"]
        assert "properties" in schema
        assert "top" in schema["properties"]
        assert "bottom" in schema["properties"]

    async def test_cli_fill_no_plain_fields_skips_llm(self):
        """fill() with no plain fields returns model_construct without LLM call."""

        class AllDepsNode(Node):
            weather: WeatherDep
            location: LocationDep

            async def __call__(self) -> None: ...

        backend = ClaudeCLIBackend()
        resolved = {
            "weather": Weather(temp=72.0, conditions="rainy"),
            "location": Location(name="Seattle", lat=47.6),
        }

        with patch.object(backend, "_run_cli_json", new_callable=AsyncMock) as mock_cli:
            result = await backend.fill(AllDepsNode, resolved, "AllDepsNode")

            mock_cli.assert_not_called()
            assert isinstance(result, AllDepsNode)
            assert result.weather.temp == 72.0


# ── Graph.run() integration ────────────────────────────────────────────


class CapturingLM:
    """Mock LM that captures fill() calls and returns canned responses."""

    def __init__(self, responses: dict[type, Node]):
        self.responses = responses
        self.fill_calls: list[dict] = []

    async def choose_type(self, types, context):
        for t in types:
            if t in self.responses:
                return t
        return types[0]

    async def fill(self, target, resolved, instruction, source=None):
        self.fill_calls.append({
            "target": target,
            "resolved": resolved,
            "instruction": instruction,
            "source": source,
        })
        return self.responses[target]

    async def make(self, node, target):
        raise NotImplementedError

    async def decide(self, node):
        raise NotImplementedError


class TestGraphFillIntegration:
    """Graph.run() resolves target deps then calls fill() with source."""

    async def test_fill_receives_resolved_deps(self):
        """fill() gets only the target's resolved dep values, not current node fields."""
        graph = Graph(start=StartNode)

        middle = MiddleNode.model_construct(
            weather=Weather(temp=72.0, conditions="rainy"),
            location=Location(name="Seattle", lat=47.6),
            vibe=Vibe(mood="groggy", cues="just woke up"),
        )
        end = EndNode.model_construct(top="Navy sweater", bottom="Chinos")

        lm = CapturingLM(responses={MiddleNode: middle, EndNode: end})

        result = await graph.arun(
            user_message="ugh i just got up",
            lm=lm,
        )

        assert len(result.trace) == 3
        assert len(lm.fill_calls) == 2

        # First fill: StartNode -> MiddleNode
        call1 = lm.fill_calls[0]
        assert call1["target"] is MiddleNode
        assert "weather" in call1["resolved"]  # dep resolved
        assert "location" in call1["resolved"]  # dep resolved
        assert "vibe" not in call1["resolved"]  # plain -- LLM fills
        assert isinstance(call1["source"], StartNode)  # source is previous node

        # Second fill: MiddleNode -> EndNode
        call2 = lm.fill_calls[1]
        assert call2["target"] is EndNode
        assert call2["resolved"] == {}  # no deps on EndNode
        assert isinstance(call2["source"], MiddleNode)

    async def test_fill_source_is_none_for_start_node(self):
        """Start node is never filled -- it's caller-provided."""
        graph = Graph(start=EndNode)

        lm = CapturingLM(responses={})

        result = await graph.arun(top="Tee", bottom="Jeans", lm=lm)

        # Terminal node -- no fill() calls at all
        assert len(lm.fill_calls) == 0
        assert len(result.trace) == 1

    async def test_instruction_is_class_name_only(self):
        """fill() instruction is class name only -- docstrings are inert."""
        graph = Graph(start=StartNode)

        middle = MiddleNode.model_construct(
            weather=Weather(temp=72.0, conditions="rainy"),
            location=Location(name="Seattle", lat=47.6),
            vibe=Vibe(mood="groggy", cues="just woke up"),
        )
        end = EndNode.model_construct(top="Navy sweater", bottom="Chinos")

        lm = CapturingLM(responses={MiddleNode: middle, EndNode: end})
        await graph.arun(user_message="test", lm=lm)

        # MiddleNode has no docstring -- class name only
        assert lm.fill_calls[0]["instruction"] == "MiddleNode"

        # EndNode has docstring but instruction is class name only
        assert lm.fill_calls[1]["instruction"] == "EndNode"


class TestFillNestedModelPreservation:
    """fill() returns nodes with nested BaseModel instances, not raw dicts."""

    async def test_cli_fill_preserves_nested_model(self):
        """ClaudeCLIBackend.fill() produces VibeCheck instance, not dict."""
        from examples.ootd import (
            AnticipateUsersDay,
            CalendarResult,
            GeoLocation,
            VibeCheck,
            WeatherResult,
        )

        backend = ClaudeCLIBackend()
        resolved = {
            "weather": WeatherResult(
                name="Seattle",
                conditions=[],
                temp=72.0,
                feels_like=70.0,
                temp_min=65.0,
                temp_max=75.0,
                humidity=60,
                wind_speed=5.0,
                clouds=50,
                visibility=10000,
            ),
            "schedule": CalendarResult(events=[]),
            "location": GeoLocation(
                name="Seattle", lat=47.6, lon=-122.3, country="US", state="WA"
            ),
        }

        async def mock_cli(prompt, schema, **kwargs):
            return {
                "vibe": {
                    "mood": "groggy",
                    "stylometry": "casual",
                    "context_cues": "just woke up",
                }
            }

        with patch.object(backend, "_run_cli_json", side_effect=mock_cli):
            result = await backend.fill(
                AnticipateUsersDay, resolved, "AnticipateUsersDay"
            )

        assert isinstance(result, AnticipateUsersDay)
        assert isinstance(result.vibe, VibeCheck)
        assert result.vibe.mood == "groggy"


class TestBuildInstruction:
    """Direct unit tests for _build_instruction."""

    def test_returns_class_name_only(self):
        """_build_instruction returns class name, ignoring __doc__."""
        assert _build_instruction(EndNode) == "EndNode"

    def test_returns_class_name_when_no_docstring(self):
        assert _build_instruction(MiddleNode) == "MiddleNode"
