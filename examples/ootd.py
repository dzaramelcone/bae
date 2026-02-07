"""OOTD recommendation example.

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
import json
import re
import webbrowser
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel

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


FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------
# ---------------------- Service Models -------------------------------
# ---------------------------------------------------------------------


class GeoLocation(BaseModel):
    name: str
    lat: float
    lon: float
    country: str
    state: str


class WeatherCondition(BaseModel):
    main: str
    description: str


class WeatherResult(BaseModel):
    name: str
    conditions: list[WeatherCondition]
    temp: float
    feels_like: float
    temp_min: float
    temp_max: float
    humidity: int
    wind_speed: float
    clouds: int
    visibility: int

    @classmethod
    def from_openweathermap(cls, data: dict) -> WeatherResult:
        return cls(
            name=data["name"],
            conditions=[
                WeatherCondition(main=w["main"], description=w["description"])
                for w in data["weather"]
            ],
            temp=data["main"]["temp"],
            feels_like=data["main"]["feels_like"],
            temp_min=data["main"]["temp_min"],
            temp_max=data["main"]["temp_max"],
            humidity=data["main"]["humidity"],
            wind_speed=data["wind"]["speed"],
            clouds=data["clouds"]["all"],
            visibility=data["visibility"],
        )


class CalendarEvent(BaseModel):
    summary: str
    location: str
    description: str
    start: str
    end: str
    categories: list[str]


class CalendarResult(BaseModel):
    events: list[CalendarEvent]

    @classmethod
    def from_ics(cls, text: str) -> CalendarResult:
        events = []
        for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.DOTALL):
            fields: dict[str, str] = {}
            for line in block.strip().splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    fields[key.strip()] = value.strip()
            events.append(
                CalendarEvent(
                    summary=fields.get("SUMMARY", ""),
                    location=fields.get("LOCATION", ""),
                    description=fields.get("DESCRIPTION", ""),
                    start=fields.get("DTSTART", ""),
                    end=fields.get("DTEND", ""),
                    categories=[
                        c.strip() for c in fields.get("CATEGORIES", "").split(",") if c.strip()
                    ],
                )
            )
        return cls(events=events)


# ---------------------------------------------------------------------
# ---------------------- External Services ----------------------------
# ---------------------------------------------------------------------


def _load_json(dir: str, name: str) -> dict:
    return json.loads((FIXTURES_DIR / dir / (name + ".json")).read_text())


def _load_text(dir: str, name: str) -> str:
    return (FIXTURES_DIR / dir / name).read_text()


class Location:
    def get(self, query: str) -> GeoLocation:
        if "seattle" in query.lower():
            data = _load_json(dir="geo", name="seattle")
        elif "phoenix" in query.lower():
            data = _load_json(dir="geo", name="phoenix")
        else:
            data = _load_json(dir="geo", name="portland")
        return GeoLocation.model_validate(data[0])


LocationDep = Annotated[GeoLocation, Dep(Location().get)]


class Weather:
    def get(self, location: LocationDep) -> WeatherResult:
        return WeatherResult.from_openweathermap(_load_json("weather", location.name))


class Calendar:
    def get(self) -> CalendarResult:
        text = _load_text(dir="cal", name="today.ics")
        return CalendarResult.from_ics(text)


WeatherDep = Annotated[WeatherResult, Dep(Weather().get)]
CalendarDep = Annotated[CalendarResult, Dep(Calendar().get)]
# =============================================================================
# Graph Nodes
# =============================================================================

# TODO: GraphConfig should support serialization format for LLM calls:
#   graph = Graph(start=CheckWeather, config=GraphConfig(format="xml"))
#
# XML keeps models aligned better over long contexts - the repeated open/close
# tags with plain language names reinforce structure more than JSON's {}/"" noise.


class IsTheUserGettingDressed(Node):
    def __call__(self) -> AnticipateUsersDay: ...


class AnticipateUsersDay(Node):
    weather: WeatherDep
    schedule: CalendarDep
    location: LocationDep

    def __call__(self) -> RecommendOOTD: ...


class RecommendOOTD(Node):
    top: str
    bottom: str
    footwear: str
    accessories: list[str]
    explanation: Annotated[str, Context(description="Brief conversational explanation")]

    def __call__(self) -> None: ...


# =============================================================================
# Graph Setup
# =============================================================================


def create_graph() -> Graph:
    """Create the weather outfit recommendation graph."""
    return Graph(start=GetUserInfo)


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
