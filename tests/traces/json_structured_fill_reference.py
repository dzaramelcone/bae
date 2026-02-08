"""Working reference: JSON structured fill via Claude CLI.

Verified 2026-02-08. Demonstrates the prompt pattern that works
with Claude CLI's --json-schema constrained decoding.

Key findings:
- XML in prompt causes CLI to hang/enter agent mode
- JSON prompt with transform_schema for input + output works reliably
- include input schema so Claude understands the structure
- include output schema so Claude knows what it's producing
- --json-schema constrains output via constrained decoding (guaranteed conformant)
- Both haiku and sonnet work; haiku is faster (~9s vs ~12s)
- Nested BaseModels with $ref/$defs work fine
- Field(description=...) steers field semantics effectively
"""

import json
import subprocess
import time

from anthropic import transform_schema
from pydantic import BaseModel, Field


# ── Models ───────────────────────────────────────────────────────────────


class WeatherCondition(BaseModel):
    main: str
    description: str


class WeatherResult(BaseModel):
    name: str
    conditions: list[WeatherCondition]
    temp: float
    humidity: int


class CalendarEvent(BaseModel):
    summary: str
    location: str
    categories: list[str]


class CalendarResult(BaseModel):
    events: list[CalendarEvent]


class GeoLocation(BaseModel):
    name: str
    lat: float
    lon: float
    country: str
    state: str


class VibeCheck(BaseModel):
    mood: str
    communication_style: str = Field(description="Infer users tone and style")
    context_cues: str


class IsTheUserGettingDressed(BaseModel):
    user_message: str


class AnticipateUsersDay(BaseModel):
    weather: WeatherResult
    schedule: CalendarResult
    location: GeoLocation
    vibe: VibeCheck


class RecommendOOTD(BaseModel):
    top: str = Field(description="Top layer recommendation")
    bottom: str = Field(description="Bottom recommendation")
    footwear: str = Field(description="Footwear recommendation")
    accessories: list[str] = Field(description="Accessory list")
    final_response: str = Field(description="Brief explanation")


# ── Prompt builder ───────────────────────────────────────────────────────


def build_fill_prompt(
    source_cls: type[BaseModel],
    source_data: dict,
    target_cls: type[BaseModel],
    context: dict | None = None,
    instruction: str = "",
) -> str:
    """Build a JSON fill prompt with input + output schemas.

    Pattern:
        Input schema (transform_schema)
        Input data (JSON)
        Context (JSON, optional)
        Output schema (transform_schema)
        Instruction text
    """
    input_schema = transform_schema(source_cls)
    output_schema = transform_schema(target_cls)

    parts = [
        f"Input schema:\n{json.dumps(input_schema, indent=2)}",
        f"Input data:\n{json.dumps(source_data, indent=2)}",
    ]

    if context:
        parts.append(f"Context:\n{json.dumps(context, indent=2)}")

    parts.append(f"Output schema:\n{json.dumps(output_schema, indent=2)}")
    parts.append(instruction)

    return "\n\n".join(parts)


# ── Runner ───────────────────────────────────────────────────────────────


def run_cli_json(prompt: str, schema: dict, model: str, timeout: int = 30) -> dict:
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
        "--no-session-persistence",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    data = json.loads(result.stdout)
    if isinstance(data, list):
        for item in reversed(data):
            if item.get("type") == "result" and "structured_output" in item:
                return item["structured_output"]
        raise RuntimeError("No structured_output in CLI response")
    return data


# ── E2E demo ─────────────────────────────────────────────────────────────


if __name__ == "__main__":
    model = "claude-haiku-4-5-20251001"

    # Turn 1: IsTheUserGettingDressed → VibeCheck
    source_data = {"user_message": "ugh i just got up"}
    context = {
        "weather": {
            "name": "Seattle",
            "conditions": [{"main": "Rain", "description": "moderate rain"}],
            "temp": 284.26,
            "humidity": 85,
        },
        "schedule": {
            "events": [
                {"summary": "Team standup", "location": "Conference Room A", "categories": ["WORK"]},
                {"summary": "Client lunch", "location": "Riverside Patio (Outdoor)", "categories": ["CLIENT"]},
                {"summary": "Gym session", "location": "Downtown Fitness", "categories": ["FITNESS"]},
            ]
        },
        "location": {"name": "Seattle", "lat": 47.6062, "lon": -122.3321, "country": "US", "state": "Washington"},
    }

    prompt1 = build_fill_prompt(
        IsTheUserGettingDressed, source_data, VibeCheck,
        context=context,
        instruction="AnticipateUsersDay — Read the user message and context. Produce a VibeCheck. Be concise.",
    )

    print(f"Turn 1: {len(prompt1)} chars")
    start = time.time()
    vibe = run_cli_json(prompt1, transform_schema(VibeCheck), model, timeout=30)
    print(f"  {time.time() - start:.1f}s")
    print(f"  {json.dumps(vibe, indent=2)}")

    # Turn 2: AnticipateUsersDay → RecommendOOTD
    anticipate_data = {
        "weather": context["weather"],
        "schedule": context["schedule"],
        "location": context["location"],
        "vibe": vibe,
    }

    prompt2 = build_fill_prompt(
        AnticipateUsersDay, anticipate_data, RecommendOOTD,
        instruction="RecommendOOTD — OOTD = outfit of the day. Be brief and practical.",
    )

    print(f"\nTurn 2: {len(prompt2)} chars")
    start = time.time()
    ootd = run_cli_json(prompt2, transform_schema(RecommendOOTD), model, timeout=30)
    print(f"  {time.time() - start:.1f}s")
    print(f"  {json.dumps(ootd, indent=2)}")
