"""E2E ootd.py graph test via Claude CLI.

Runs the full ootd graph with ClaudeCLIBackend (haiku for speed):
1. IsTheUserGettingDressed → AnticipateUsersDay (deps resolved, vibe LLM-filled)
2. AnticipateUsersDay → RecommendOOTD (all plain, LLM-filled)
3. RecommendOOTD → None (terminal)

Gated behind --run-e2e (requires live Claude CLI + API key).
"""

from __future__ import annotations

import pytest

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

from bae.lm import ClaudeCLIBackend
from bae.result import GraphResult


@pytest.mark.e2e
class TestOotdCLI:
    """Full ootd.py graph execution via Claude CLI."""

    @pytest.fixture(scope="class")
    async def run(self):
        """Run the graph once, share result across tests."""
        lm = ClaudeCLIBackend(model="claude-haiku-4-5-20251001", timeout=60)
        result = await graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )
        return result

    def test_three_node_trace(self, run):
        """Graph produces trace: [IsTheUserGettingDressed, AnticipateUsersDay, RecommendOOTD]."""
        assert isinstance(run, GraphResult)
        assert len(run.trace) == 3
        assert isinstance(run.trace[0], IsTheUserGettingDressed)
        assert isinstance(run.trace[1], AnticipateUsersDay)
        assert isinstance(run.trace[2], RecommendOOTD)

    def test_anticipate_has_resolved_deps(self, run):
        """AnticipateUsersDay has weather/schedule/location from dep resolution."""
        anticipate = run.trace[1]
        assert isinstance(anticipate.weather, WeatherResult)
        assert isinstance(anticipate.schedule, CalendarResult)
        assert isinstance(anticipate.location, GeoLocation)
        assert anticipate.weather.name == "Seattle"

    def test_anticipate_has_llm_filled_vibe(self, run):
        """AnticipateUsersDay.vibe was filled by the LLM (not a dep)."""
        anticipate = run.trace[1]
        assert isinstance(anticipate.vibe, VibeCheck)
        assert anticipate.vibe.mood  # non-empty string
        assert anticipate.vibe.communication_style
        assert anticipate.vibe.context_cues

    def test_recommend_has_outfit_fields(self, run):
        """Terminal node has all outfit fields populated by LLM."""
        ootd = run.trace[-1]
        assert isinstance(ootd, RecommendOOTD)
        assert ootd.top  # non-empty
        assert ootd.bottom
        assert ootd.footwear
        assert len(ootd.accessories) > 0
        assert ootd.final_response

    def test_recommend_has_inspo_urls(self, run):
        """RecommendOOTD.inspo contains URL-like strings."""
        ootd = run.trace[-1]
        assert len(ootd.inspo) > 0
        for url in ootd.inspo:
            assert str(url).startswith("http")
