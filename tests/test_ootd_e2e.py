"""End-to-end test for ootd.py graph with mocked LLM.

Verifies the full graph execution flow matches the plan:
1. IsTheUserGettingDressed → AnticipateUsersDay (deps resolved, vibe LLM-filled)
2. AnticipateUsersDay → RecommendOOTD (all plain, LLM-filled)
3. RecommendOOTD → None (terminal)

Uses a CapturingLM to verify:
- fill() receives correct resolved dict (only deps)
- fill() receives source node (previous context frame)
- Prompt structure follows XML completion protocol
"""

from __future__ import annotations

from examples.ootd import (
    AnticipateUsersDay,
    CalendarResult,
    GeoLocation,
    IsTheUserGettingDressed,
    RecommendOOTD,
    VibeCheck,
    WeatherResult,
    graph,
)
from pydantic import HttpUrl

from bae.node import Node
from bae.resolver import classify_fields
from bae.result import GraphResult


# ── Mock LM ────────────────────────────────────────────────────────────


class OotdCapturingLM:
    """Mock LM that returns canned ootd responses and captures fill() calls."""

    def __init__(self):
        self.fill_calls: list[dict] = []

    def choose_type(self, types, context):
        return types[0]

    def fill(self, target, resolved, instruction, source=None):
        self.fill_calls.append({
            "target": target,
            "resolved": dict(resolved),
            "instruction": instruction,
            "source": source,
            "source_type": type(source) if source else None,
        })

        if target is AnticipateUsersDay:
            return AnticipateUsersDay.model_construct(
                weather=resolved["weather"],
                schedule=resolved["schedule"],
                location=resolved["location"],
                vibe=VibeCheck(
                    mood="groggy but has places to be",
                    communication_style="low-energy, practical",
                    context_cues="just woke up, rainy Seattle morning",
                ),
            )
        elif target is RecommendOOTD:
            return RecommendOOTD.model_construct(
                top="Navy merino crewneck",
                bottom="Charcoal slim chinos",
                footwear="Waterproof Chelsea boots",
                accessories=["Compact umbrella", "Silver watch"],
                final_response="Rainy Seattle day — layers that work.",
                inspo=[
                    HttpUrl("https://example.com/pnw-casual"),
                    HttpUrl("https://example.com/rainy-layers"),
                ],
            )

        raise ValueError(f"Unexpected target: {target}")

    def make(self, node, target):
        raise NotImplementedError

    def decide(self, node):
        raise NotImplementedError


# ── E2E test ───────────────────────────────────────────────────────────


class TestOotdE2E:
    """Full ootd.py graph execution with mocked LLM."""

    def test_graph_completes_three_node_trace(self):
        """Graph produces trace: [IsTheUserGettingDressed, AnticipateUsersDay, RecommendOOTD]."""
        lm = OotdCapturingLM()

        result = graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )

        assert isinstance(result, GraphResult)
        assert len(result.trace) == 3
        assert isinstance(result.trace[0], IsTheUserGettingDressed)
        assert isinstance(result.trace[1], AnticipateUsersDay)
        assert isinstance(result.trace[2], RecommendOOTD)

    def test_two_fill_calls(self):
        """fill() called twice: once for AnticipateUsersDay, once for RecommendOOTD."""
        lm = OotdCapturingLM()

        graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )

        assert len(lm.fill_calls) == 2
        assert lm.fill_calls[0]["target"] is AnticipateUsersDay
        assert lm.fill_calls[1]["target"] is RecommendOOTD

    def test_iteration1_resolved_has_deps_only(self):
        """First fill: resolved dict has weather/schedule/location (deps), NOT vibe."""
        lm = OotdCapturingLM()

        graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )

        call1 = lm.fill_calls[0]
        resolved = call1["resolved"]

        # Deps resolved by the graph runtime
        assert "weather" in resolved
        assert "schedule" in resolved
        assert "location" in resolved
        assert isinstance(resolved["weather"], WeatherResult)
        assert isinstance(resolved["schedule"], CalendarResult)
        assert isinstance(resolved["location"], GeoLocation)

        # vibe is plain — NOT in resolved
        assert "vibe" not in resolved

    def test_iteration1_source_is_start_node(self):
        """First fill: source is IsTheUserGettingDressed instance."""
        lm = OotdCapturingLM()

        graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )

        call1 = lm.fill_calls[0]
        assert call1["source_type"] is IsTheUserGettingDressed
        assert call1["source"].user_message == "ugh i just got up"

    def test_iteration2_resolved_is_empty(self):
        """Second fill: RecommendOOTD has no deps, resolved is empty."""
        lm = OotdCapturingLM()

        graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )

        call2 = lm.fill_calls[1]
        assert call2["resolved"] == {}

    def test_iteration2_source_is_anticipate(self):
        """Second fill: source is AnticipateUsersDay with all fields populated."""
        lm = OotdCapturingLM()

        graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )

        call2 = lm.fill_calls[1]
        assert call2["source_type"] is AnticipateUsersDay

        source = call2["source"]
        # Deps should be populated on source
        assert isinstance(source.weather, WeatherResult)
        assert isinstance(source.vibe, VibeCheck)
        assert source.vibe.mood == "groggy but has places to be"

    def test_terminal_node_has_outfit_data(self):
        """Terminal node (RecommendOOTD) has all outfit fields populated."""
        lm = OotdCapturingLM()

        result = graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )

        ootd = result.trace[-1]
        assert isinstance(ootd, RecommendOOTD)
        assert ootd.top == "Navy merino crewneck"
        assert ootd.bottom == "Charcoal slim chinos"
        assert ootd.footwear == "Waterproof Chelsea boots"
        assert len(ootd.accessories) == 2
        assert "Compact umbrella" in ootd.accessories

    def test_dep_chaining_resolves_weather_from_location(self):
        """WeatherDep chains on LocationDep — weather fixture uses Seattle data."""
        lm = OotdCapturingLM()

        graph.run(
            IsTheUserGettingDressed(user_message="test"),
            lm=lm,
        )

        weather = lm.fill_calls[0]["resolved"]["weather"]
        assert weather.name == "Seattle"
        # Verify it loaded from the fixture
        assert weather.temp > 0

    def test_instruction_matches_class_name(self):
        """fill() instructions are class names (+ docstring for RecommendOOTD)."""
        lm = OotdCapturingLM()

        graph.run(
            IsTheUserGettingDressed(user_message="test"),
            lm=lm,
        )

        assert lm.fill_calls[0]["instruction"] == "AnticipateUsersDay"
        assert "RecommendOOTD" in lm.fill_calls[1]["instruction"]
        assert "OOTD = outfit of the day." in lm.fill_calls[1]["instruction"]
