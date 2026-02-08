"""TDD tests for XML prompt helpers used by fill().

Tests:
- _build_xml_schema: generates schema showing field types and sources
- _build_partial_xml: partial XML with deps serialized, ending at open tag
- _parse_xml_completion: parse LLM continuation, extract fields, validate
- _build_plain_model: dynamic Pydantic model with only plain fields
- _serialize_value: convert Pydantic models/scalars to XML string
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


class SourceNode(Node):
    user_message: str

    def __call__(self) -> None: ...


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


class DepThenPlainNode(Node):
    weather: WeatherDep
    vibe: VibeCheck
    outfit: str

    def __call__(self) -> None: ...


# ── _build_xml_schema ──────────────────────────────────────────────────


class TestBuildXmlSchema:
    """_build_xml_schema generates schema showing field types and sources."""

    def test_mixed_fields_show_source_annotations(self):
        """Dep fields show source='dep', plain fields show nested structure."""
        from bae.lm import _build_xml_schema

        schema = _build_xml_schema(MixedNode)

        assert '<schema name="MixedNode">' in schema
        assert 'source="dep"' in schema
        assert "<weather" in schema
        assert "<location" in schema
        assert "<vibe>" in schema
        assert "</schema>" in schema

    def test_all_plain_fields(self):
        """All plain fields have no source annotation."""
        from bae.lm import _build_xml_schema

        schema = _build_xml_schema(AllPlainNode)

        assert 'source="dep"' not in schema
        assert "<top>" in schema
        assert "<bottom>" in schema

    def test_includes_docstring_as_description(self):
        """Class docstring becomes description attribute on schema tag."""
        from bae.lm import _build_xml_schema

        schema = _build_xml_schema(AllPlainNode)

        assert 'description="A node with only plain fields."' in schema

    def test_no_docstring_no_description(self):
        """No docstring means no description attribute."""
        from bae.lm import _build_xml_schema

        schema = _build_xml_schema(MixedNode)

        assert "description=" not in schema


# ── _build_partial_xml ─────────────────────────────────────────────────


class TestBuildPartialXml:
    """_build_partial_xml generates partial XML ending at first plain field."""

    def test_mixed_node_ends_at_first_plain_field(self):
        """Partial XML serializes deps, ends at open tag of first plain field."""
        from bae.lm import _build_partial_xml

        resolved = {
            "weather": Weather(temp=72.0, conditions="sunny"),
            "location": Location(name="Seattle", lat=47.6, lon=-122.3),
        }

        xml = _build_partial_xml(MixedNode, resolved)

        assert xml.startswith("<MixedNode>")
        assert "<weather>" in xml
        assert "<temp>72.0</temp>" in xml
        assert "<location>" in xml
        assert xml.rstrip().endswith("<vibe>")
        # Should NOT have closing tags for vibe or MixedNode
        assert "</vibe>" not in xml
        assert "</MixedNode>" not in xml

    def test_all_plain_ends_at_first_field(self):
        """All-plain node ends at open tag of first field."""
        from bae.lm import _build_partial_xml

        xml = _build_partial_xml(AllPlainNode, {})

        assert xml.startswith("<AllPlainNode>")
        assert xml.rstrip().endswith("<top>")
        assert "</top>" not in xml

    def test_dep_then_plain_serializes_dep_only(self):
        """Only dep fields are serialized, stops at first plain."""
        from bae.lm import _build_partial_xml

        resolved = {
            "weather": Weather(temp=72.0, conditions="sunny"),
        }

        xml = _build_partial_xml(DepThenPlainNode, resolved)

        assert "<weather>" in xml
        assert xml.rstrip().endswith("<vibe>")
        assert "</vibe>" not in xml


# ── _parse_xml_completion ──────────────────────────────────────────────


class TestParseXmlCompletion:
    """_parse_xml_completion extracts field values from LLM continuation."""

    def test_parses_single_plain_field(self):
        """Parses a single closing-tag field from continuation."""
        from bae.lm import _parse_xml_completion

        response = """Navy merino</top>
  <bottom>Charcoal chinos</bottom>
  <accessories>
    <item>Umbrella</item>
  </accessories>
  <inspo>
    <item>https://example.com/1</item>
  </inspo>
</AllPlainNode>"""

        result = _parse_xml_completion(response, AllPlainNode, "top")

        assert result["top"] == "Navy merino"
        assert result["bottom"] == "Charcoal chinos"
        assert result["accessories"] == ["Umbrella"]

    def test_parses_nested_model_field(self):
        """Parses a nested Pydantic model from continuation."""
        from bae.lm import _parse_xml_completion

        response = """
    <mood>groggy</mood>
    <style>casual</style>
  </vibe>
</MixedNode>"""

        result = _parse_xml_completion(response, MixedNode, "vibe")

        assert isinstance(result["vibe"], dict)
        assert result["vibe"]["mood"] == "groggy"
        assert result["vibe"]["style"] == "casual"

    def test_handles_list_fields(self):
        """Parses list fields with <item> tags."""
        from bae.lm import _parse_xml_completion

        response = """Cool sneakers</footwear>
  <accessories>
    <item>Watch</item>
    <item>Scarf</item>
  </accessories>
</SomeNode>"""

        # We need a node with these fields
        class SomeNode(Node):
            footwear: str
            accessories: list[str]

            def __call__(self) -> None: ...

        result = _parse_xml_completion(response, SomeNode, "footwear")

        assert result["footwear"] == "Cool sneakers"
        assert result["accessories"] == ["Watch", "Scarf"]


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


# ── _serialize_value ───────────────────────────────────────────────────


class TestSerializeValue:
    """_serialize_value converts values to XML strings."""

    def test_pydantic_model(self):
        """Serializes Pydantic BaseModel to XML elements."""
        from bae.lm import _serialize_value

        w = Weather(temp=72.0, conditions="sunny")
        xml = _serialize_value("weather", w, indent=2)

        assert "<weather>" in xml
        assert "<temp>72.0</temp>" in xml
        assert "<conditions>sunny</conditions>" in xml
        assert "</weather>" in xml

    def test_scalar_value(self):
        """Serializes scalar to simple element."""
        from bae.lm import _serialize_value

        xml = _serialize_value("name", "Alice", indent=2)
        assert "<name>Alice</name>" in xml

    def test_list_value(self):
        """Serializes list with <item> tags."""
        from bae.lm import _serialize_value

        xml = _serialize_value("items", ["a", "b"], indent=2)
        assert "<items>" in xml
        assert "<item>a</item>" in xml
        assert "<item>b</item>" in xml


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
