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
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl

from bae import Dep, Graph, Node, Recall, graph


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


class No(Node): ...


class VibeCheck(BaseModel):
    mood: str
    stylometry: str
    context_cues: str


class UserInfo(BaseModel):
    name: str = "Dzara"
    gender: str = "woman"


class IsTheUserGettingDressed(Node):
    user_info: UserInfo
    user_message: str  # caller provides this — start node fields are always user-provided

    async def __call__(self) -> AnticipateUsersDay | No: ...


class AnticipateUsersDay(Node):
    weather: WeatherDep
    schedule: CalendarDep
    location: LocationDep
    vibe: VibeCheck  # LLM fills this — inferred from user_message on previous node

    async def __call__(self) -> RecommendOOTD: ...


class InferUserBackground(Node):
    """Infer background details about the user."""

    user_info: Annotated[UserInfo, Recall()]
    occupation: str
    income: str
    lifestyle: str
    background: str


class InferUserPersonality(Node):
    """Make personal inferences about the user."""

    user_info: Annotated[UserInfo, Recall()]
    brief_perspective: list[str]
    brief_vision: list[str]
    brief_goals: list[str]
    brief_dreams: list[str]
    mbti: str


class GenerateWardrobe(Node):
    """Generate an itemized list of the user's wardrobe."""

    user_info: Annotated[UserInfo, Recall()]
    user_career: Annotated[InferUserBackground, Dep()]
    user_personality: Annotated[InferUserPersonality, Dep()]
    brief_overall_styling: str
    tops: list[str]
    bottoms: list[str]
    footwear: list[str]
    accessories: list[str]


class RecommendOOTD(Node):
    wardrobe: Annotated[GenerateWardrobe, Dep()]
    overall_vision: str
    top: str
    bottom: str
    footwear: str
    accessories: list[str]
    final_response: str
    inspo: list[HttpUrl]

    async def __call__(self) -> None: ...


# =============================================================================
# Run
# =============================================================================


ootd = graph(start=IsTheUserGettingDressed)

if __name__ == "__main__":
    import asyncio

    result = asyncio.run(ootd(name="Dzara", user_message="ugh i just got up"))
    print(result.trace[-1].model_dump_json(indent=2))
