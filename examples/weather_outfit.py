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
import base64
import webbrowser
from typing import Annotated

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


class LocationService:
    """Mock geocoding service returning OpenWeatherMap Geo API-style JSON."""

    def geocode(self, query: str) -> str:
        """Geocode a location name. Returns raw JSON string."""
        # Mock responses - real API returns array of matches
        if "seattle" in query.lower():
            return '''[{
  "name": "Seattle",
  "local_names": {"en": "Seattle"},
  "lat": 47.6062,
  "lon": -122.3321,
  "country": "US",
  "state": "Washington"
}]'''
        elif "phoenix" in query.lower():
            return '''[{
  "name": "Phoenix",
  "local_names": {"en": "Phoenix"},
  "lat": 33.4484,
  "lon": -112.0740,
  "country": "US",
  "state": "Arizona"
}]'''
        else:
            # Default to Portland
            return '''[{
  "name": "Portland",
  "local_names": {"en": "Portland"},
  "lat": 45.5152,
  "lon": -122.6784,
  "country": "US",
  "state": "Oregon"
}]'''


class WeatherService:
    """Mock weather service returning OpenWeatherMap-style JSON."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def get_current(self, location: str) -> str:
        """Get current weather. Returns raw JSON string (OpenWeatherMap format)."""
        # Mock responses based on location name
        # Seattle
        if "seattle" in location.lower():
            return '''{
  "coord": {"lon": -122.33, "lat": 47.61},
  "weather": [{"id": 501, "main": "Rain", "description": "moderate rain", "icon": "10d"}],
  "main": {"temp": 284.26, "feels_like": 283.74, "temp_min": 283.15, "temp_max": 285.37, "pressure": 1012, "humidity": 85},
  "visibility": 8000,
  "wind": {"speed": 5.36, "deg": 200},
  "clouds": {"all": 90},
  "dt": 1738800000,
  "sys": {"country": "US", "sunrise": 1738765200, "sunset": 1738800000},
  "timezone": -28800,
  "name": "Seattle"
}'''
        # Phoenix
        elif "phoenix" in location.lower():
            return '''{
  "coord": {"lon": -112.07, "lat": 33.45},
  "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
  "main": {"temp": 308.15, "feels_like": 307.5, "temp_min": 306.15, "temp_max": 310.15, "pressure": 1010, "humidity": 15},
  "visibility": 10000,
  "wind": {"speed": 2.24, "deg": 180},
  "clouds": {"all": 0},
  "dt": 1738800000,
  "sys": {"country": "US", "sunrise": 1738765200, "sunset": 1738803600},
  "timezone": -25200,
  "name": "Phoenix"
}'''
        # Default: mild weather
        else:
            return '''{
  "coord": {"lon": -122.68, "lat": 45.52},
  "weather": [{"id": 803, "main": "Clouds", "description": "broken clouds", "icon": "04d"}],
  "main": {"temp": 293.15, "feels_like": 292.5, "temp_min": 291.15, "temp_max": 295.15, "pressure": 1015, "humidity": 50},
  "visibility": 10000,
  "wind": {"speed": 3.58, "deg": 270},
  "clouds": {"all": 75},
  "dt": 1738800000,
  "sys": {"country": "US", "sunrise": 1738765200, "sunset": 1738801800},
  "timezone": -28800,
  "name": "Portland"
}'''


class CalendarService:
    """Mock calendar service returning iCalendar (.ics) format."""

    def __init__(self, user_id: str | None = None):
        self.user_id = user_id

    def get_todays_events(self) -> str:
        """Get today's calendar events. Returns raw ICS string."""
        # In production: call Apple Calendar API, Google Calendar, etc.
        return '''BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Bae Example//EN
BEGIN:VEVENT
UID:standup-001@example.com
DTSTAMP:20260205T080000Z
DTSTART:20260205T090000
DTEND:20260205T091500
SUMMARY:Team standup
LOCATION:Conference Room A (Indoor)
DESCRIPTION:Daily sync with engineering team
CATEGORIES:MEETING,WORK
END:VEVENT
BEGIN:VEVENT
UID:lunch-002@example.com
DTSTAMP:20260205T080000Z
DTSTART:20260205T120000
DTEND:20260205T133000
SUMMARY:Client lunch - Acme Corp
LOCATION:Riverside Patio Restaurant (Outdoor)
DESCRIPTION:Q1 planning discussion with Acme team. Business casual attire.
CATEGORIES:MEETING,CLIENT,BUSINESS
END:VEVENT
BEGIN:VEVENT
UID:gym-003@example.com
DTSTAMP:20260205T080000Z
DTSTART:20260205T173000
DTEND:20260205T183000
SUMMARY:Gym session
LOCATION:Downtown Fitness (Indoor)
DESCRIPTION:Leg day
CATEGORIES:PERSONAL,FITNESS
END:VEVENT
END:VCALENDAR'''


# =============================================================================
# Graph Nodes
# =============================================================================

# TODO: Context should support automatic markdown wrapping for raw data:
#   weather_json: Annotated[str, Context(markup="json")]  # wraps in ```json\n...\n```
#   events_ics: Annotated[str, Context(markup="ics")]     # wraps in ```ics\n...\n```
# This makes LLM context cleaner and signals the format explicitly.


class CheckWeather(Node):
    """Check the weather for the user's location."""

    location: Annotated[str, Context(description="User's location (city name)")]
    weather_json: Annotated[str | None, Bind()] = None

    def __call__(
        self,
        lm: LM,
        weather_service: Annotated[WeatherService, Dep(description="Weather API client")],
    ) -> CheckSchedule:
        """Fetch weather and continue to schedule check."""
        self.weather_json = weather_service.get_current(self.location)
        return CheckSchedule(
            weather_json=self.weather_json,
            events_ics="",
        )


class CheckSchedule(Node):
    """Check today's calendar for events."""

    weather_json: Annotated[str, Context(description="Current weather (OpenWeatherMap JSON)")]
    events_ics: Annotated[str | None, Bind()] = None

    def __call__(
        self,
        lm: LM,
        calendar_service: Annotated[CalendarService, Dep(description="Calendar API client")],
    ) -> DecideActivity:
        """Fetch schedule and decide what to do."""
        self.events_ics = calendar_service.get_todays_events()
        return DecideActivity(
            weather_json=self.weather_json,
            events_ics=self.events_ics,
        )


class DecideActivity(Node):
    """Decide whether to go out or stay home based on weather and schedule."""

    weather_json: Annotated[str, Context(description="Current weather (OpenWeatherMap JSON)")]
    events_ics: Annotated[str, Context(description="Today's calendar (iCalendar/ICS format)")]

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

    weather_json: Annotated[str, Context(description="Weather to dress for (JSON)")]
    events_ics: Annotated[str, Context(description="Events to dress for (ICS)")]
    primary_activity: Annotated[str, Context(description="Main reason for going out")]

    def __call__(self) -> OutfitRecommendation:
        """Generate outfit recommendation for going out."""
        ...


class StayingHome(Node):
    """User is staying home today. Recommend comfort clothes."""

    weather_json: Annotated[str, Context(description="Weather for indoor temp context (JSON)")]
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
