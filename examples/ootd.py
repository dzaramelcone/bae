"""OOTD recommendation example — v2 DX reference.

Demonstrates:
- Nodes as context frames: fields = prompt context, class name = instruction
- Start node fields are caller-provided (user input)
- Plain fields (no annotation) = LLM fills them
- Dep(callable) for external service injection with chaining
- Recall() for graph state lookup (imported but not needed here)
- Implicit LM: configured on the graph, not in node signatures
- Terminal node = the response schema

Graph:
    IsTheUserGettingDressed → AnticipateUsersDay → RecommendOOTD → None
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, HttpUrl

from bae import Dep, Graph, Node, Recall


FIXTURES_DIR = Path(__file__).parent / "fixtures"


# =============================================================================
# Service Models
# =============================================================================


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


# =============================================================================
# Dep Functions & Type Aliases
# =============================================================================
# Plain functions that fetch external data. Dep(fn) tells bae to call these
# automatically when a node declares a field with the corresponding type alias.
# Dep chaining: get_weather takes LocationDep, so bae resolves location first.


def _load_json(dir: str, name: str) -> dict:
    return json.loads((FIXTURES_DIR / dir / (name + ".json")).read_text())


def get_location() -> GeoLocation:
    """Get the user's current location. Black box — phone GPS, IP lookup, etc."""
    return GeoLocation.model_validate(_load_json("geo", "seattle")[0])


LocationDep = Annotated[GeoLocation, Dep(get_location)]


def get_weather(location: LocationDep) -> WeatherResult:
    """Fetch weather for a location. Chains on LocationDep — bae resolves location first."""
    return WeatherResult.from_openweathermap(_load_json("weather", location.name))


WeatherDep = Annotated[WeatherResult, Dep(get_weather)]


def get_schedule() -> CalendarResult:
    """Fetch today's calendar."""
    text = (FIXTURES_DIR / "cal" / "today.ics").read_text()
    return CalendarResult.from_ics(text)


CalendarDep = Annotated[CalendarResult, Dep(get_schedule)]


# =============================================================================
# Graph Nodes
# =============================================================================
# Nodes are context frames. Fields assemble the information the LLM needs
# to construct the next node. Class name is the instruction. Return type
# is the output schema.
#
# Field annotations:
#   Dep(fn)   — bae calls fn to fill this (external data)
#   Recall()  — bae searches the trace to fill this (graph state)
#   (none)    — LLM fills this when constructing the node


class VibeCheck(BaseModel):
    mood: str
    communication_style: str
    context_cues: str


class IsTheUserGettingDressed(Node):
    user_message: str  # caller provides this — start node fields are always user-provided

    async def __call__(self) -> AnticipateUsersDay: ...


class AnticipateUsersDay(Node):
    weather: WeatherDep
    schedule: CalendarDep
    location: LocationDep
    vibe: VibeCheck  # LLM fills this — inferred from user_message on previous node

    async def __call__(self) -> RecommendOOTD: ...


class RecommendOOTD(Node):
    top: str = Field(description="a specific garment for the upper body")
    bottom: str = Field(description="a specific garment for the lower body")
    footwear: str = Field(description="specific shoes or boots")
    accessories: list[str] = Field(description="jewelry, bags, hats, scarves, etc.")
    final_response: str = Field(description="casual message to the user with the recommendation")
    inspo: list[HttpUrl] = Field(description="outfit inspiration image URLs")

    async def __call__(self) -> None: ...


# =============================================================================
# Run
# =============================================================================


graph = Graph(start=IsTheUserGettingDressed)

if __name__ == "__main__":
    result = graph.run(IsTheUserGettingDressed(user_message="ugh i just got up"))
    print(result.trace[-1].model_dump_json(indent=2))
