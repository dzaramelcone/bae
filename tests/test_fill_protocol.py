"""Tests for the fill() XML completion protocol.

Verifies:
- Prompt structure: source XML + schema + partial XML at open tag
- Graph.run() resolves target deps before fill()
- fill() receives source node and resolved dict
- End-to-end ootd.py graph with mocked LLM
"""

from __future__ import annotations

from typing import Annotated
from unittest.mock import patch

import pytest
from pydantic import BaseModel, HttpUrl

from bae.graph import Graph, _build_instruction
from bae.lm import (
    ClaudeCLIBackend,
    _build_partial_xml,
    _build_xml_schema,
)
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
    """fill() prompt has three sections: source XML, schema, partial XML."""

    def test_schema_shows_dep_annotations(self):
        """Schema for MiddleNode marks weather/location as dep, vibe as plain."""
        schema = _build_xml_schema(MiddleNode)

        assert '<schema name="MiddleNode">' in schema
        assert '<weather source="dep">' in schema
        assert '<location source="dep">' in schema
        # vibe is plain — no source attr
        assert "<vibe>" in schema
        assert 'source="dep">Vibe' not in schema

    def test_schema_includes_docstring_as_description(self):
        """EndNode's docstring becomes schema description."""
        schema = _build_xml_schema(EndNode)

        assert 'description="Final recommendation."' in schema

    def test_partial_xml_serializes_deps_stops_at_plain(self):
        """Partial XML has resolved deps, ends at first plain field open tag."""
        resolved = {
            "weather": Weather(temp=72.0, conditions="rainy"),
            "location": Location(name="Seattle", lat=47.6),
        }

        xml = _build_partial_xml(MiddleNode, resolved)

        # Starts with root tag
        assert xml.startswith("<MiddleNode>")
        # Has serialized deps
        assert "<weather>" in xml
        assert "<temp>72.0</temp>" in xml
        assert "<location>" in xml
        assert "<name>Seattle</name>" in xml
        # Ends at first plain field open tag
        assert xml.rstrip().endswith("<vibe>")
        # No closing tags for partial content
        assert "</vibe>" not in xml
        assert "</MiddleNode>" not in xml

    def test_all_plain_partial_xml(self):
        """EndNode (all plain) partial XML ends at <top>."""
        xml = _build_partial_xml(EndNode, {})

        assert xml.startswith("<EndNode>")
        assert xml.rstrip().endswith("<top>")

    def test_cli_fill_sends_three_part_prompt(self):
        """ClaudeCLIBackend.fill() sends source + schema + partial XML."""
        backend = ClaudeCLIBackend()
        source = StartNode(user_message="ugh i just got up")
        resolved = {
            "weather": Weather(temp=72.0, conditions="rainy"),
            "location": Location(name="Seattle", lat=47.6),
        }

        captured_prompt = None

        def capture_prompt(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            # Return valid XML continuation
            return """
    <mood>groggy</mood>
    <cues>just woke up</cues>
  </vibe>
</MiddleNode>"""

        with patch.object(backend, "_run_cli_text", side_effect=capture_prompt):
            backend.fill(MiddleNode, resolved, "MiddleNode", source=source)

        assert captured_prompt is not None

        # Part 1: Source node XML
        assert "<StartNode>" in captured_prompt
        assert "<user_message>ugh i just got up</user_message>" in captured_prompt

        # Part 2: Schema
        assert '<schema name="MiddleNode">' in captured_prompt
        assert 'source="dep"' in captured_prompt

        # Part 3: Partial XML ending at <vibe>
        assert "<MiddleNode>" in captured_prompt
        assert "<temp>72.0</temp>" in captured_prompt
        assert captured_prompt.rstrip().endswith("<vibe>")


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
