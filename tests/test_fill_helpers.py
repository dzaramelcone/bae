"""Tests for fill() helpers: _build_plain_model and validate_plain_fields.

Tests:
- _build_plain_model: dynamic Pydantic model with only plain fields
- validate_plain_fields: two-stage validation separating dep errors from LLM errors
"""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel, HttpUrl

from bae.markers import Dep, Recall
from bae.node import Node


# ── Test types ──────────────────────────────────────────────────────────


class Weather(BaseModel):
    temp: float
    conditions: str


class Location(BaseModel):
    name: str
    lat: float
    lon: float


def get_weather() -> Weather:
    return Weather(temp=72.0, conditions="sunny")


def get_location() -> Location:
    return Location(name="Seattle", lat=47.6, lon=-122.3)


WeatherDep = Annotated[Weather, Dep(get_weather)]
LocationDep = Annotated[Location, Dep(get_location)]


class VibeCheck(BaseModel):
    mood: str
    style: str


class MixedNode(Node):
    weather: WeatherDep
    location: LocationDep
    vibe: VibeCheck

    def __call__(self) -> None: ...


class AllPlainNode(Node):
    """A node with only plain fields."""

    top: str
    bottom: str
    accessories: list[str]
    inspo: list[HttpUrl]

    def __call__(self) -> None: ...


# ── _build_plain_model ─────────────────────────────────────────────────


class TestBuildPlainModel:
    """_build_plain_model creates dynamic Pydantic model with only plain fields."""

    def test_mixed_node_plain_model(self):
        """Plain model for MixedNode has only 'vibe' field."""
        from bae.lm import _build_plain_model

        PlainModel = _build_plain_model(MixedNode)

        field_names = set(PlainModel.model_fields.keys())
        assert field_names == {"vibe"}

    def test_all_plain_model(self):
        """Plain model for AllPlainNode has all fields."""
        from bae.lm import _build_plain_model

        PlainModel = _build_plain_model(AllPlainNode)

        field_names = set(PlainModel.model_fields.keys())
        assert field_names == {"top", "bottom", "accessories", "inspo"}

    def test_plain_model_validates(self):
        """Plain model can validate data."""
        from bae.lm import _build_plain_model

        PlainModel = _build_plain_model(MixedNode)

        instance = PlainModel.model_validate(
            {"vibe": {"mood": "happy", "style": "casual"}}
        )
        assert instance.vibe.mood == "happy"


# ── validate_plain_fields ──────────────────────────────────────────────


class NodeWithTypedPlains(Node):
    """Node with typed plain fields for validation testing."""

    weather: WeatherDep
    temp_f: float
    summary: str
    tags: list[str]

    def __call__(self) -> None: ...


class TestValidatePlainFields:
    """validate_plain_fields validates only LLM-generated plain fields."""

    def test_valid_plain_fields_pass(self):
        """Valid plain field values pass validation and return validated dict."""
        from bae.lm import validate_plain_fields

        raw = {"temp_f": "72.5", "summary": "warm day", "tags": ["sunny", "nice"]}
        result = validate_plain_fields(raw, NodeWithTypedPlains)

        assert result["temp_f"] == 72.5  # coerced from string
        assert result["summary"] == "warm day"
        assert result["tags"] == ["sunny", "nice"]

    def test_invalid_plain_fields_raise_fill_error(self):
        """Invalid plain field values raise FillError with validation details."""
        from bae.exceptions import FillError
        from bae.lm import validate_plain_fields

        raw = {"temp_f": "not_a_number", "summary": "ok", "tags": ["fine"]}

        with pytest.raises(FillError) as exc_info:
            validate_plain_fields(raw, NodeWithTypedPlains)

        err = exc_info.value
        assert err.node_type is NodeWithTypedPlains
        assert "temp_f" in err.validation_errors
        assert err.attempts == 0  # no retry, just validation

    def test_missing_required_field_raises_fill_error(self):
        """Missing required plain fields raise FillError."""
        from bae.exceptions import FillError
        from bae.lm import validate_plain_fields

        raw = {"temp_f": "72.5"}  # missing summary and tags

        with pytest.raises(FillError) as exc_info:
            validate_plain_fields(raw, NodeWithTypedPlains)

        err = exc_info.value
        assert "summary" in err.validation_errors or "tags" in err.validation_errors

    def test_dep_fields_excluded_from_validation(self):
        """Dep fields are NOT included in plain field validation."""
        from bae.lm import validate_plain_fields

        # Only plain fields in the raw dict — no weather (dep)
        raw = {"temp_f": "72.5", "summary": "warm", "tags": ["a"]}
        result = validate_plain_fields(raw, NodeWithTypedPlains)

        assert "weather" not in result

    def test_returns_validated_model_dump(self):
        """Return value is a dict of validated+coerced plain field values."""
        from bae.lm import validate_plain_fields

        raw = {"temp_f": "99", "summary": "hot", "tags": ["desert"]}
        result = validate_plain_fields(raw, NodeWithTypedPlains)

        # Should be a plain dict, not a model instance
        assert isinstance(result, dict)
        assert isinstance(result["temp_f"], float)

    def test_nested_model_validated(self):
        """Nested BaseModel plain fields are validated through Pydantic."""
        from bae.lm import validate_plain_fields

        raw = {"vibe": {"mood": "happy", "style": "casual"}}
        result = validate_plain_fields(raw, MixedNode)

        # Should be a validated VibeCheck instance after model_dump
        assert result["vibe"]["mood"] == "happy"

    def test_nested_model_invalid_raises_fill_error(self):
        """Invalid nested model data raises FillError."""
        from bae.exceptions import FillError
        from bae.lm import validate_plain_fields

        # VibeCheck requires mood and style — provide neither
        raw = {"vibe": {"wrong_key": "bad"}}

        with pytest.raises(FillError) as exc_info:
            validate_plain_fields(raw, MixedNode)

        assert "vibe" in exc_info.value.validation_errors


# ── _strip_format ────────────────────────────────────────────────────


class TestStripFormat:
    """_strip_format removes 'format' fields that break Claude CLI --json-schema."""

    def test_strips_top_level_format(self):
        from bae.lm import _strip_format

        schema = {"type": "string", "format": "uri"}
        assert _strip_format(schema) == {"type": "string"}

    def test_strips_nested_format(self):
        from bae.lm import _strip_format

        schema = {
            "type": "object",
            "properties": {
                "link": {"type": "string", "format": "uri"},
                "name": {"type": "string"},
            },
        }
        result = _strip_format(schema)
        assert "format" not in result["properties"]["link"]
        assert result["properties"]["name"] == {"type": "string"}

    def test_strips_format_in_array_items(self):
        from bae.lm import _strip_format

        schema = {
            "type": "array",
            "items": {"type": "string", "format": "uri", "description": "a url"},
        }
        result = _strip_format(schema)
        assert result["items"] == {"type": "string", "description": "a url"}

    def test_preserves_non_format_fields(self):
        from bae.lm import _strip_format

        schema = {
            "type": "object",
            "title": "Foo",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
            "additionalProperties": False,
        }
        assert _strip_format(schema) == schema

    def test_no_mutation(self):
        from bae.lm import _strip_format

        original = {"type": "string", "format": "uri"}
        _strip_format(original)
        assert "format" in original  # original unchanged
