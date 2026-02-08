"""End-to-end test for ootd.py graph with mocked LLM.

Verifies the full graph execution flow matches the plan:
1. IsTheUserGettingDressed → AnticipateUsersDay (deps resolved, vibe LLM-filled)
2. AnticipateUsersDay → RecommendOOTD (all plain, LLM-filled)
3. RecommendOOTD → None (terminal)

Saves full prompt/response traces to tests/traces/ootd_e2e.txt.
"""

from __future__ import annotations

from pathlib import Path

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
from pydantic_ai import format_as_xml

from bae.lm import _build_partial_xml, _build_xml_schema, _serialize_value
from bae.node import Node
from bae.resolver import classify_fields
from bae.result import GraphResult

TRACES_DIR = Path(__file__).parent / "traces"


# ── Mock LM with trace capture ────────────────────────────────────────


class OotdCapturingLM:
    """Mock LM that returns canned ootd responses and builds real prompts for traces."""

    def __init__(self):
        self.fill_calls: list[dict] = []
        self.turns: list[dict] = []

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

        # Build the actual prompt (same as ClaudeCLIBackend.fill)
        fields = classify_fields(target)
        plain_fields = [n for n in target.model_fields if fields.get(n) == "plain"]
        first_plain = plain_fields[0] if plain_fields else None

        prompt_parts: list[str] = []
        if source is not None:
            prompt_parts.append(
                _serialize_value(source.__class__.__name__, source)
            )
        prompt_parts.append(_build_xml_schema(target))
        prompt_parts.append(_build_partial_xml(target, resolved))
        prompt = "\n\n".join(prompt_parts)

        # Generate canned response
        if target is AnticipateUsersDay:
            result = AnticipateUsersDay.model_construct(
                weather=resolved["weather"],
                schedule=resolved["schedule"],
                location=resolved["location"],
                vibe=VibeCheck(
                    mood="groggy but has places to be",
                    communication_style="low-energy, practical, wants efficiency",
                    context_cues="just woke up, rainy Seattle morning, indoor standup then outdoor client lunch requiring business casual, gym in the evening",
                ),
            )
            response = """    <mood>groggy but has places to be</mood>
    <communication_style>low-energy, practical, wants efficiency</communication_style>
    <context_cues>just woke up, rainy Seattle morning, indoor standup then outdoor client lunch requiring business casual, gym in the evening</context_cues>
  </vibe>
</AnticipateUsersDay>"""
        elif target is RecommendOOTD:
            result = RecommendOOTD.model_construct(
                top="Navy merino crewneck over a white Oxford button-down",
                bottom="Charcoal slim chinos",
                footwear="Waterproof leather Chelsea boots",
                accessories=["Compact umbrella", "Simple silver watch"],
                final_response="Rainy Seattle day with a client lunch at an outdoor restaurant — you need layers that look business-casual but handle weather. The merino-over-Oxford combo reads polished without a blazer, chinos bridge casual and professional, and waterproof Chelseas keep your feet dry on the walk. Toss the umbrella and gym bag in a tote and you're set from standup through leg day.",
                inspo=[
                    HttpUrl("https://pinterest.com/pin/pnw-business-casual"),
                    HttpUrl("https://pinterest.com/pin/rainy-day-smart-layers"),
                ],
            )
            response = """Navy merino crewneck over a white Oxford button-down</top>
  <bottom>Charcoal slim chinos</bottom>
  <footwear>Waterproof leather Chelsea boots</footwear>
  <accessories>
    <item>Compact umbrella</item>
    <item>Simple silver watch</item>
  </accessories>
  <final_response>Rainy Seattle day with a client lunch at an outdoor restaurant — you need layers that look business-casual but handle weather. The merino-over-Oxford combo reads polished without a blazer, chinos bridge casual and professional, and waterproof Chelseas keep your feet dry on the walk. Toss the umbrella and gym bag in a tote and you're set from standup through leg day.</final_response>
  <inspo>
    <item>https://pinterest.com/pin/pnw-business-casual</item>
    <item>https://pinterest.com/pin/rainy-day-smart-layers</item>
  </inspo>
</RecommendOOTD>"""
        else:
            raise ValueError(f"Unexpected target: {target}")

        source_name = source.__class__.__name__ if source else "None"
        self.turns.append({
            "title": f"{source_name} → {target.__name__}",
            "prompt": prompt,
            "response": response,
        })

        return result

    def make(self, node, target):
        raise NotImplementedError

    def decide(self, node):
        raise NotImplementedError

    def write_trace(self, path: Path) -> None:
        """Write all turns to a trace file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        for i, turn in enumerate(self.turns, 1):
            lines.append(f"{'=' * 72}")
            lines.append(f"TURN {i}: {turn['title']}")
            lines.append(f"{'=' * 72}")
            lines.append("")
            lines.append(f"{'─' * 40} INPUT {'─' * 40}")
            lines.append("")
            lines.append(turn["prompt"])
            lines.append("")
            lines.append(f"{'─' * 39} OUTPUT {'─' * 39}")
            lines.append("")
            lines.append(turn["response"])
            lines.append("")
            lines.append("")

        path.write_text("\n".join(lines))


# ── E2E test ───────────────────────────────────────────────────────────


class TestOotdE2E:
    """Full ootd.py graph execution with mocked LLM."""

    def _run_graph(self) -> tuple[GraphResult, OotdCapturingLM]:
        lm = OotdCapturingLM()
        result = graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )
        return result, lm

    def test_graph_completes_three_node_trace(self):
        """Graph produces trace: [IsTheUserGettingDressed, AnticipateUsersDay, RecommendOOTD]."""
        result, _ = self._run_graph()

        assert isinstance(result, GraphResult)
        assert len(result.trace) == 3
        assert isinstance(result.trace[0], IsTheUserGettingDressed)
        assert isinstance(result.trace[1], AnticipateUsersDay)
        assert isinstance(result.trace[2], RecommendOOTD)

    def test_two_fill_calls(self):
        """fill() called twice: once for AnticipateUsersDay, once for RecommendOOTD."""
        _, lm = self._run_graph()

        assert len(lm.fill_calls) == 2
        assert lm.fill_calls[0]["target"] is AnticipateUsersDay
        assert lm.fill_calls[1]["target"] is RecommendOOTD

    def test_iteration1_resolved_has_deps_only(self):
        """First fill: resolved dict has weather/schedule/location (deps), NOT vibe."""
        _, lm = self._run_graph()

        resolved = lm.fill_calls[0]["resolved"]
        assert "weather" in resolved
        assert "schedule" in resolved
        assert "location" in resolved
        assert isinstance(resolved["weather"], WeatherResult)
        assert isinstance(resolved["schedule"], CalendarResult)
        assert isinstance(resolved["location"], GeoLocation)
        assert "vibe" not in resolved

    def test_iteration1_source_is_start_node(self):
        """First fill: source is IsTheUserGettingDressed instance."""
        _, lm = self._run_graph()

        call1 = lm.fill_calls[0]
        assert call1["source_type"] is IsTheUserGettingDressed
        assert call1["source"].user_message == "ugh i just got up"

    def test_iteration2_resolved_is_empty(self):
        """Second fill: RecommendOOTD has no deps, resolved is empty."""
        _, lm = self._run_graph()

        assert lm.fill_calls[1]["resolved"] == {}

    def test_iteration2_source_is_anticipate(self):
        """Second fill: source is AnticipateUsersDay with all fields populated."""
        _, lm = self._run_graph()

        call2 = lm.fill_calls[1]
        assert call2["source_type"] is AnticipateUsersDay
        source = call2["source"]
        assert isinstance(source.weather, WeatherResult)
        assert isinstance(source.vibe, VibeCheck)
        assert source.vibe.mood == "groggy but has places to be"

    def test_terminal_node_has_outfit_data(self):
        """Terminal node (RecommendOOTD) has all outfit fields populated."""
        result, _ = self._run_graph()

        ootd = result.trace[-1]
        assert isinstance(ootd, RecommendOOTD)
        assert ootd.top == "Navy merino crewneck over a white Oxford button-down"
        assert ootd.bottom == "Charcoal slim chinos"
        assert ootd.footwear == "Waterproof leather Chelsea boots"
        assert len(ootd.accessories) == 2
        assert "Compact umbrella" in ootd.accessories

    def test_dep_chaining_resolves_weather_from_location(self):
        """WeatherDep chains on LocationDep — weather fixture uses Seattle data."""
        _, lm = self._run_graph()

        weather = lm.fill_calls[0]["resolved"]["weather"]
        assert weather.name == "Seattle"
        assert weather.temp > 0

    def test_instruction_matches_class_name(self):
        """fill() instructions are class names (+ docstring for RecommendOOTD)."""
        _, lm = self._run_graph()

        assert lm.fill_calls[0]["instruction"] == "AnticipateUsersDay"
        assert "RecommendOOTD" in lm.fill_calls[1]["instruction"]
        assert "OOTD = outfit of the day." in lm.fill_calls[1]["instruction"]

    def test_writes_trace_file(self):
        """E2E run saves trace to tests/traces/ootd_e2e.txt."""
        _, lm = self._run_graph()

        trace_path = TRACES_DIR / "ootd_e2e.txt"
        lm.write_trace(trace_path)

        content = trace_path.read_text()
        assert "TURN 1:" in content
        assert "TURN 2:" in content
        assert "INPUT" in content
        assert "OUTPUT" in content
        assert "<IsTheUserGettingDressed>" in content
        assert "<AnticipateUsersDay>" in content
        assert "<RecommendOOTD>" in content
