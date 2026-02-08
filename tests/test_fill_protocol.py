"""Tests for the fill() JSON structured output protocol.

Verifies:
- ClaudeCLIBackend.fill() sends prompt and uses JSON schema
- Graph.run() resolves target deps before fill()
- fill() receives source node and resolved dict
"""

from __future__ import annotations

from typing import Annotated
from unittest.mock import patch

import pytest
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

    def __call__(self) -> MiddleNode: ...


class MiddleNode(Node):
    weather: WeatherDep
    location: LocationDep
    vibe: Vibe

    def __call__(self) -> EndNode: ...


class EndNode(Node):
    """Final recommendation."""

    top: str
    bottom: str

    def __call__(self) -> None: ...


# ── Prompt structure tests ─────────────────────────────────────────────


class TestPromptStructure:
    """fill() prompt includes source context, resolved deps, and instruction."""

    def test_cli_fill_sends_prompt_with_source_and_context(self):
        """ClaudeCLIBackend.fill() sends source + context + instruction in prompt."""
        backend = ClaudeCLIBackend()
        source = StartNode(user_message="ugh i just got up")
        resolved = {
            "weather": Weather(temp=72.0, conditions="rainy"),
            "location": Location(name="Seattle", lat=47.6),
        }

        captured_args = {}

        def capture_cli(prompt, schema):
            captured_args["prompt"] = prompt
            captured_args["schema"] = schema
            return {"vibe": {"mood": "groggy", "cues": "just woke up"}}

        with patch.object(backend, "_run_cli_json", side_effect=capture_cli):
            backend.fill(MiddleNode, resolved, "MiddleNode", source=source)

        prompt = captured_args["prompt"]

        # Source node context
        assert "StartNode" in prompt
        assert "ugh i just got up" in prompt

        # Resolved deps as context
        assert "Context:" in prompt

        # Instruction
        assert "MiddleNode" in prompt

    def test_cli_fill_uses_json_schema(self):
        """ClaudeCLIBackend.fill() passes JSON schema from plain model."""
        backend = ClaudeCLIBackend()
        resolved: dict = {}

        captured_args = {}

        def capture_cli(prompt, schema):
            captured_args["schema"] = schema
            return {"top": "Navy sweater", "bottom": "Chinos"}

        with patch.object(backend, "_run_cli_json", side_effect=capture_cli):
            backend.fill(EndNode, resolved, "EndNode")

        schema = captured_args["schema"]
        assert "properties" in schema
        assert "top" in schema["properties"]
        assert "bottom" in schema["properties"]

    def test_cli_fill_no_plain_fields_skips_llm(self):
        """fill() with no plain fields returns model_construct without LLM call."""

        class AllDepsNode(Node):
            weather: WeatherDep
            location: LocationDep

            def __call__(self) -> None: ...

        backend = ClaudeCLIBackend()
        resolved = {
            "weather": Weather(temp=72.0, conditions="rainy"),
            "location": Location(name="Seattle", lat=47.6),
        }

        with patch.object(backend, "_run_cli_json") as mock_cli:
            result = backend.fill(AllDepsNode, resolved, "AllDepsNode")

            mock_cli.assert_not_called()
            assert isinstance(result, AllDepsNode)
            assert result.weather.temp == 72.0


# ── Graph.run() integration ────────────────────────────────────────────


class CapturingLM:
    """Mock LM that captures fill() calls and returns canned responses."""

    def __init__(self, responses: dict[type, Node]):
        self.responses = responses
        self.fill_calls: list[dict] = []

    def choose_type(self, types, context):
        for t in types:
            if t in self.responses:
                return t
        return types[0]

    def fill(self, target, resolved, instruction, source=None):
        self.fill_calls.append({
            "target": target,
            "resolved": resolved,
            "instruction": instruction,
            "source": source,
        })
        return self.responses[target]

    def make(self, node, target):
        raise NotImplementedError

    def decide(self, node):
        raise NotImplementedError


class TestGraphFillIntegration:
    """Graph.run() resolves target deps then calls fill() with source."""

    def test_fill_receives_resolved_deps(self):
        """fill() gets only the target's resolved dep values, not current node fields."""
        graph = Graph(start=StartNode)

        middle = MiddleNode.model_construct(
            weather=Weather(temp=72.0, conditions="rainy"),
            location=Location(name="Seattle", lat=47.6),
            vibe=Vibe(mood="groggy", cues="just woke up"),
        )
        end = EndNode.model_construct(top="Navy sweater", bottom="Chinos")

        lm = CapturingLM(responses={MiddleNode: middle, EndNode: end})

        result = graph.run(
            StartNode(user_message="ugh i just got up"),
            lm=lm,
        )

        assert len(result.trace) == 3
        assert len(lm.fill_calls) == 2

        # First fill: StartNode → MiddleNode
        call1 = lm.fill_calls[0]
        assert call1["target"] is MiddleNode
        assert "weather" in call1["resolved"]  # dep resolved
        assert "location" in call1["resolved"]  # dep resolved
        assert "vibe" not in call1["resolved"]  # plain — LLM fills
        assert isinstance(call1["source"], StartNode)  # source is previous node

        # Second fill: MiddleNode → EndNode
        call2 = lm.fill_calls[1]
        assert call2["target"] is EndNode
        assert call2["resolved"] == {}  # no deps on EndNode
        assert isinstance(call2["source"], MiddleNode)

    def test_fill_source_is_none_for_start_node(self):
        """Start node is never filled — it's caller-provided."""
        graph = Graph(start=EndNode)

        lm = CapturingLM(responses={})

        result = graph.run(EndNode(top="Tee", bottom="Jeans"), lm=lm)

        # Terminal node — no fill() calls at all
        assert len(lm.fill_calls) == 0
        assert len(result.trace) == 1

    def test_instruction_is_class_name_plus_docstring(self):
        """fill() instruction includes class name and docstring."""
        graph = Graph(start=StartNode)

        middle = MiddleNode.model_construct(
            weather=Weather(temp=72.0, conditions="rainy"),
            location=Location(name="Seattle", lat=47.6),
            vibe=Vibe(mood="groggy", cues="just woke up"),
        )
        end = EndNode.model_construct(top="Navy sweater", bottom="Chinos")

        lm = CapturingLM(responses={MiddleNode: middle, EndNode: end})
        graph.run(StartNode(user_message="test"), lm=lm)

        # MiddleNode has no docstring
        assert lm.fill_calls[0]["instruction"] == "MiddleNode"

        # EndNode has docstring
        assert "EndNode" in lm.fill_calls[1]["instruction"]
        assert "Final recommendation." in lm.fill_calls[1]["instruction"]
