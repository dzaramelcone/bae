"""Weather-based outfit recommendation example.

Demonstrates:
- External service injection (WeatherService, CalendarService)
- Clean node definitions with Context/Dep markers
- Decision flow based on real data
- Conversational output
- Full optimization loop

Usage:
    # Run the graph (uses Claude CLI by default)
    uv run python examples/weather_outfit.py

    # Use DSPy backend (requires ANTHROPIC_API_KEY)
    uv run python examples/weather_outfit.py --backend dspy

    # Show the graph structure
    uv run python examples/weather_outfit.py --show-graph

    # Run optimization demo
    uv run python examples/weather_outfit.py --optimize
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import quote

from bae import (
    Bind,
    Context,
    Dep,
    Graph,
    LM,
    Node,
    compile_graph,
    trace_to_examples,
)


# =============================================================================
# External Services (injected as deps)
# =============================================================================


@dataclass
class WeatherData:
    """Weather information for a location."""

    temperature_f: int
    condition: str  # sunny, cloudy, rainy, snowy
    wind_mph: int
    humidity_pct: int

    def summary(self) -> str:
        return f"{self.temperature_f}°F, {self.condition}, wind {self.wind_mph}mph"


@dataclass
class CalendarEvent:
    """A calendar event."""

    title: str
    location: str  # indoor, outdoor, flexible
    formality: str  # casual, business, formal


class WeatherService:
    """Mock weather service. Replace with real API in production."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def get_weather(self, location: str) -> WeatherData:
        """Get weather for a location. Mock implementation."""
        # In production: call OpenWeatherMap, WeatherAPI, etc.
        # Mock: return based on location name for demo
        if "seattle" in location.lower():
            return WeatherData(
                temperature_f=52,
                condition="rainy",
                wind_mph=12,
                humidity_pct=85,
            )
        elif "phoenix" in location.lower():
            return WeatherData(
                temperature_f=95,
                condition="sunny",
                wind_mph=5,
                humidity_pct=15,
            )
        else:
            # Default: mild weather
            return WeatherData(
                temperature_f=68,
                condition="cloudy",
                wind_mph=8,
                humidity_pct=50,
            )


class CalendarService:
    """Mock calendar service. Replace with Google Calendar, etc."""

    def __init__(self, user_id: str | None = None):
        self.user_id = user_id

    def get_todays_events(self) -> list[CalendarEvent]:
        """Get today's calendar events. Mock implementation."""
        # In production: call Google Calendar API, etc.
        return [
            CalendarEvent(
                title="Team standup",
                location="indoor",
                formality="casual",
            ),
            CalendarEvent(
                title="Client lunch",
                location="outdoor",
                formality="business",
            ),
        ]


# =============================================================================
# Graph Nodes
# =============================================================================


class CheckWeather(Node):
    """Check the weather for the user's location."""

    location: Annotated[str, Context(description="User's location (city name)")]
    weather: Annotated[WeatherData | None, Bind()] = None

    def __call__(
        self,
        lm: LM,
        weather_service: Annotated[WeatherService, Dep(description="Weather API client")],
    ) -> CheckSchedule:
        """Fetch weather and continue to schedule check."""
        self.weather = weather_service.get_weather(self.location)
        return CheckSchedule(
            weather=self.weather,
            events=[],
        )


class CheckSchedule(Node):
    """Check today's calendar for events."""

    weather: Annotated[WeatherData, Context(description="Current weather conditions")]
    events: Annotated[list[CalendarEvent], Bind()] = None

    def __call__(
        self,
        lm: LM,
        calendar_service: Annotated[CalendarService, Dep(description="Calendar API client")],
    ) -> DecideActivity:
        """Fetch schedule and decide what to do."""
        self.events = calendar_service.get_todays_events()
        return DecideActivity(
            weather=self.weather,
            events=self.events,
        )


class DecideActivity(Node):
    """Decide whether to go out or stay home based on weather and schedule."""

    weather: Annotated[WeatherData, Context(description="Current weather")]
    events: Annotated[list[CalendarEvent], Context(description="Today's calendar events")]

    def __call__(self) -> GoingOut | StayingHome:
        """LLM decides based on weather and schedule.

        Consider:
        - Outdoor events in bad weather -> might reschedule
        - All indoor events in nice weather -> still might go out
        - Multiple outdoor events -> definitely need weather-appropriate clothes
        """
        ...


class GoingOut(Node):
    """User is going out today. Recommend appropriate outfit."""

    weather: Annotated[WeatherData, Context(description="Weather to dress for")]
    events: Annotated[list[CalendarEvent], Context(description="Events to dress for")]
    primary_activity: Annotated[str, Context(description="Main reason for going out")]

    def __call__(self) -> OutfitRecommendation:
        """Generate outfit recommendation for going out."""
        ...


class StayingHome(Node):
    """User is staying home today. Recommend comfort clothes."""

    weather: Annotated[WeatherData, Context(description="Weather (for indoor temp context)")]
    reason: Annotated[str, Context(description="Why staying home (weather, no events, etc.)")]

    def __call__(self) -> OutfitRecommendation:
        """Generate comfort outfit recommendation."""
        ...


class OutfitRecommendation(Node):
    """Final outfit recommendation with conversational reply."""

    top: str
    bottom: str
    footwear: str
    accessories: list[str]
    explanation: Annotated[str, Context(description="Brief conversational explanation")]

    def __call__(self) -> None:
        """Terminal node - recommendation complete."""
        ...

    def to_message(self) -> str:
        """Format as a friendly message."""
        accessories_str = ", ".join(self.accessories) if self.accessories else "nothing extra"
        return f"""{self.explanation}

Here's what I'd suggest:
  - Top: {self.top}
  - Bottom: {self.bottom}
  - Shoes: {self.footwear}
  - Accessories: {accessories_str}
"""


# =============================================================================
# Graph Setup
# =============================================================================


def create_graph() -> Graph:
    """Create the weather outfit recommendation graph."""
    return Graph(start=CheckWeather)


def create_services() -> dict:
    """Create external service instances."""
    return {
        "weather_service": WeatherService(),
        "calendar_service": CalendarService(),
    }


# =============================================================================
# Optimization Demo
# =============================================================================


def run_optimization_demo(graph: Graph) -> None:
    """Demonstrate the full optimization loop."""
    from bae import ClaudeCLIBackend

    print("\n" + "=" * 60)
    print("OPTIMIZATION DEMO")
    print("=" * 60)

    # 1. Collect traces from multiple runs
    print("\n1. Collecting execution traces (using Claude CLI)...")
    traces = []
    services = create_services()
    lm = ClaudeCLIBackend(model="claude-sonnet-4-20250514", timeout=60)

    locations = ["Seattle, WA", "Phoenix, AZ", "Portland, OR"]
    for loc in locations:
        print(f"   Running for {loc}...")
        result = graph.run(CheckWeather(location=loc), lm=lm, **services)
        traces.append(result.trace)
        print(f"   -> {len(result.trace)} nodes visited")

    # 2. Convert traces to training examples
    print("\n2. Converting traces to DSPy examples...")
    all_examples = []
    for trace in traces:
        examples = trace_to_examples(trace)
        all_examples.extend(examples)
    print(f"   Generated {len(all_examples)} training examples")

    # 3. Compile the graph
    print("\n3. Compiling graph to DSPy...")
    compiled = compile_graph(graph)
    print(f"   Created signatures for {len(compiled.signatures)} node types")

    # 4. Show what optimization would do
    print("\n4. Optimization requires sufficient examples per node type:")
    from collections import Counter

    node_counts = Counter(ex.node_type for ex in all_examples)
    for node_type, count in sorted(node_counts.items()):
        status = "ready" if count >= 10 else f"need {10 - count} more"
        print(f"   {node_type}: {count} examples ({status})")

    print("\n5. To run actual optimization (needs 10+ examples per node):")
    print("   compiled.optimize(all_examples)")
    print("   compiled.save('./compiled_prompts')")
    print("\n6. To load and use optimized prompts:")
    print("   lm = create_optimized_lm(graph, './compiled_prompts')")
    print("   graph.run(start_node, lm=lm, **services)")


# =============================================================================
# CLI
# =============================================================================


def show_graph(graph: Graph) -> None:
    """Open the graph in mermaid.live."""
    mermaid = graph.to_mermaid()
    print("Mermaid diagram:")
    print(mermaid)
    print()

    # Encode for mermaid.live
    # Format: https://mermaid.live/edit#pako:<base64>
    # Simpler: https://mermaid.live/view#base64:<base64>
    import base64

    encoded = base64.urlsafe_b64encode(mermaid.encode()).decode()
    url = f"https://mermaid.live/view#base64:{encoded}"

    print(f"Opening in browser: {url[:80]}...")
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description="Weather outfit recommendation example")
    parser.add_argument(
        "--location",
        default="Seattle, WA",
        help="Location to check weather for",
    )
    parser.add_argument(
        "--show-graph",
        action="store_true",
        help="Show graph structure in mermaid.live",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run optimization demo",
    )
    parser.add_argument(
        "--backend",
        choices=["dspy", "claude"],
        default="claude",
        help="LLM backend to use (claude is default, needs `claude` CLI)",
    )
    args = parser.parse_args()

    graph = create_graph()

    if args.show_graph:
        show_graph(graph)
        return

    if args.optimize:
        run_optimization_demo(graph)
        return

    # Run the graph
    print(f"Checking weather and schedule for {args.location}...")
    print()

    services = create_services()

    if args.backend == "dspy":
        # DSPy requires an LM to be configured
        import dspy

        # Configure DSPy with Claude via LiteLLM
        # Requires ANTHROPIC_API_KEY environment variable
        dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-4-20250514"))
        result = graph.run(CheckWeather(location=args.location), **services)
    else:
        # Use ClaudeCLIBackend (default - just needs `claude` CLI)
        from bae import ClaudeCLIBackend

        lm = ClaudeCLIBackend(model="claude-sonnet-4-20250514", timeout=60)
        result = graph.run(CheckWeather(location=args.location), lm=lm, **services)

    # Print trace
    print("Execution trace:")
    for i, node in enumerate(result.trace):
        print(f"  {i + 1}. {type(node).__name__}")

    # Print result
    print()
    if result.node is None and result.trace:
        final = result.trace[-1]
        if isinstance(final, OutfitRecommendation):
            print(final.to_message())
        else:
            print(f"Ended at: {type(final).__name__}")
    else:
        print(f"Final node: {result.node}")


if __name__ == "__main__":
    main()
