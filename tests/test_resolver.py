"""Tests for v2 markers (Dep with callable, Recall) and field classification."""

from __future__ import annotations

import graphlib
from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest

from bae.exceptions import BaeError, RecallError
from bae.markers import Dep, Recall
from bae.node import Node
from bae.resolver import (
    build_dep_dag,
    classify_fields,
    recall_from_trace,
    resolve_dep,
    resolve_fields,
    validate_node_deps,
)


def get_data() -> str:
    return "test data"


def get_other() -> str:
    return "other data"


# --- Dep functions for DAG tests ---


def get_location() -> str:
    return "NYC"


def get_weather(location: Annotated[str, Dep(get_location)]) -> str:
    return f"Weather in {location}"


def get_forecast(weather: Annotated[str, Dep(get_weather)]) -> str:
    return f"Forecast: {weather}"


def get_temperature() -> int:
    return 72


# Circular dep functions — define first, then patch annotations
def circular_a(b: str) -> str:
    return b


def circular_b(a: str) -> str:
    return a


circular_a.__annotations__["b"] = Annotated[str, Dep(circular_b)]
circular_b.__annotations__["a"] = Annotated[str, Dep(circular_a)]


# For return type mismatch test: returns int but field expects str
def get_wrong_type() -> int:
    return 42


# For missing return annotation test
def no_return_annotation(x: str):
    return x


# For subclass return type test
class Fruit:
    """Base type for dep return type subclass test."""

    pass


class Apple(Fruit):
    """Subclass of Fruit."""

    pass


def get_apple() -> Apple:
    return Apple()


class TestDepMarker:
    def test_dep_stores_callable(self):
        """Dep(callable) stores a reference to the callable."""
        dep = Dep(get_data)
        assert dep.fn is get_data

    def test_dep_frozen(self):
        """Dep is frozen - cannot reassign fields."""
        dep = Dep(get_data)
        try:
            dep.fn = get_other
            assert False, "Should have raised FrozenInstanceError"
        except FrozenInstanceError:
            pass

    def test_dep_backward_compat(self):
        """v1 Dep(description='...') still works."""
        dep = Dep(description="old style")
        assert dep.description == "old style"
        assert dep.fn is None


class TestRecallMarker:
    def test_recall_creates_marker(self):
        """Recall() creates an instance."""
        marker = Recall()
        assert isinstance(marker, Recall)

    def test_recall_frozen(self):
        """Recall is frozen - cannot set attributes."""
        marker = Recall()
        try:
            marker.x = 1
            assert False, "Should have raised FrozenInstanceError"
        except FrozenInstanceError:
            pass


class TestRecallError:
    def test_recall_error_is_bae_error(self):
        """RecallError inherits from BaeError."""
        assert issubclass(RecallError, BaeError)

    def test_recall_error_message(self):
        """RecallError preserves its message."""
        try:
            raise RecallError("no match for Foo")
        except RecallError as e:
            assert str(e) == "no match for Foo"


class TestClassifyFields:
    def test_dep_field_classified(self):
        """Dep-annotated field is classified as 'dep'."""

        class TestNode(Node):
            data: Annotated[str, Dep(get_data)]

        result = classify_fields(TestNode)
        assert result["data"] == "dep"

    def test_recall_field_classified(self):
        """Recall-annotated field is classified as 'recall'."""

        class TestNode(Node):
            prev: Annotated[str, Recall()]

        result = classify_fields(TestNode)
        assert result["prev"] == "recall"

    def test_plain_field_classified(self):
        """Unannotated field is classified as 'plain'."""

        class TestNode(Node):
            name: str

        result = classify_fields(TestNode)
        assert result["name"] == "plain"

    def test_mixed_fields(self):
        """All three field types classified correctly together."""

        class TestNode(Node):
            data: Annotated[str, Dep(get_data)]
            prev: Annotated[str, Recall()]
            name: str

        result = classify_fields(TestNode)
        assert result["data"] == "dep"
        assert result["prev"] == "recall"
        assert result["name"] == "plain"

    def test_annotated_without_marker(self):
        """Annotated field without Dep/Recall marker is classified as 'plain'."""

        class TestNode(Node):
            data: Annotated[str, "some other metadata"]

        result = classify_fields(TestNode)
        assert result["data"] == "plain"


# --- Test node types for recall testing ---


class VibeCheck(Node):
    """Simple node with a string field."""

    mood: str

    def __call__(self, lm) -> None: ...


class WeatherReport(Node):
    """Node with int and str fields."""

    temperature: int
    conditions: str

    def __call__(self, lm) -> None: ...


class DepNode(Node):
    """Node with a dep-annotated field (should be skipped by recall)."""

    external_data: Annotated[str, Dep(get_data)]
    reasoning: str

    def __call__(self, lm) -> None: ...


class Animal:
    """Plain base class for subclass matching tests."""

    pass


class Dog(Animal):
    """Subclass of Animal."""

    pass


class PetNode(Node):
    """Node with a field typed as base class Animal."""

    pet: Animal

    def __call__(self, lm) -> None: ...


class RecallNode(Node):
    """Node with a Recall-annotated field (should be skipped by recall)."""

    recalled: Annotated[str, Recall()]
    original: str

    def __call__(self, lm) -> None: ...


class TestRecallFromTrace:
    def test_recall_finds_matching_type(self):
        """Trace has single node with matching str field."""
        trace = [VibeCheck.model_construct(mood="happy")]
        assert recall_from_trace(trace, str) == "happy"

    def test_recall_most_recent_wins(self):
        """When multiple nodes have matching fields, last in trace wins."""
        trace = [
            VibeCheck.model_construct(mood="sad"),
            VibeCheck.model_construct(mood="happy"),
        ]
        assert recall_from_trace(trace, str) == "happy"

    def test_recall_searches_backward(self):
        """Finds int on WeatherReport even though VibeCheck is more recent."""
        trace = [
            WeatherReport.model_construct(temperature=72, conditions="sunny"),
            VibeCheck.model_construct(mood="chill"),
        ]
        assert recall_from_trace(trace, int) == 72

    def test_recall_skips_dep_fields(self):
        """Dep-annotated fields are not LLM-filled and must be skipped."""
        dep_node = DepNode.model_construct(
            external_data="dep value", reasoning="llm value"
        )
        trace = [dep_node]
        assert recall_from_trace(trace, str) == "llm value"

    def test_recall_no_match_raises_error(self):
        """RecallError raised when no field of target type found in trace."""
        trace = [VibeCheck.model_construct(mood="ok")]
        with pytest.raises(RecallError):
            recall_from_trace(trace, int)

    def test_recall_empty_trace_raises_error(self):
        """RecallError raised on empty trace."""
        with pytest.raises(RecallError):
            recall_from_trace([], str)

    def test_recall_subclass_matching(self):
        """Field typed as Animal matches when searching for Animal (via issubclass)."""
        fido = Dog()
        node = PetNode.model_construct(pet=fido)
        trace = [node]
        result = recall_from_trace(trace, Animal)
        assert result is fido

    def test_recall_skips_recall_fields(self):
        """Recall-annotated fields are infrastructure and must be skipped."""
        node = RecallNode.model_construct(recalled="recalled value", original="real value")
        trace = [node]
        assert recall_from_trace(trace, str) == "real value"


# --- Test classes for dep DAG and validation ---


class TestBuildDepDag:
    def test_single_dep(self):
        """Node with one Dep field produces a DAG containing that dep function."""

        class SingleDepNode(Node):
            loc: Annotated[str, Dep(get_location)]

        ts = build_dep_dag(SingleDepNode)
        order = list(ts.static_order())
        assert get_location in order

    def test_chained_deps(self):
        """Dep that itself has a Dep param is walked transitively.

        get_weather depends on get_location, so get_location must come first.
        """

        class ChainedNode(Node):
            weather: Annotated[str, Dep(get_weather)]

        ts = build_dep_dag(ChainedNode)
        order = list(ts.static_order())
        loc_idx = order.index(get_location)
        weather_idx = order.index(get_weather)
        assert loc_idx < weather_idx

    def test_deep_chain(self):
        """Three-level dep chain: forecast -> weather -> location."""

        class DeepNode(Node):
            forecast: Annotated[str, Dep(get_forecast)]

        ts = build_dep_dag(DeepNode)
        order = list(ts.static_order())
        loc_idx = order.index(get_location)
        weather_idx = order.index(get_weather)
        forecast_idx = order.index(get_forecast)
        assert loc_idx < weather_idx < forecast_idx

    def test_multiple_independent_deps(self):
        """Node with two independent dep fields includes both in DAG."""

        class MultiNode(Node):
            loc: Annotated[str, Dep(get_location)]
            temp: Annotated[int, Dep(get_temperature)]

        ts = build_dep_dag(MultiNode)
        order = list(ts.static_order())
        assert get_location in order
        assert get_temperature in order

    def test_shared_transitive_dep(self):
        """Two dep fields that share a transitive dep: leaf appears once."""

        class SharedNode(Node):
            weather: Annotated[str, Dep(get_weather)]
            forecast: Annotated[str, Dep(get_forecast)]

        ts = build_dep_dag(SharedNode)
        order = list(ts.static_order())
        # get_location is a transitive dep of both get_weather and get_forecast
        assert order.count(get_location) == 1

    def test_circular_deps_detected(self):
        """Circular dep chain raises CycleError on static_order/prepare."""

        class CircularNode(Node):
            a: Annotated[str, Dep(circular_a)]

        ts = build_dep_dag(CircularNode)
        with pytest.raises(graphlib.CycleError):
            list(ts.static_order())


class TestValidateNodeDeps:
    def test_valid_deps_no_errors(self):
        """Node with properly typed dep produces no validation errors."""

        class ValidNode(Node):
            loc: Annotated[str, Dep(get_location)]

        errors = validate_node_deps(ValidNode, is_start=False)
        assert errors == []

    def test_return_type_mismatch(self):
        """Dep returning int for a str field is caught as a type error."""

        class MismatchNode(Node):
            data: Annotated[str, Dep(get_wrong_type)]

        errors = validate_node_deps(MismatchNode, is_start=False)
        assert len(errors) >= 1
        error_msg = errors[0]
        assert "get_wrong_type" in error_msg
        assert "str" in error_msg

    def test_missing_return_annotation(self):
        """Dep function without return type annotation is caught."""

        class NoReturnNode(Node):
            data: Annotated[str, Dep(no_return_annotation)]

        errors = validate_node_deps(NoReturnNode, is_start=False)
        assert len(errors) >= 1
        assert "no_return_annotation" in errors[0]

    def test_subclass_return_type_valid(self):
        """Dep returning a subclass of the field type passes MRO check."""

        class SubclassNode(Node):
            fruit: Annotated[Fruit, Dep(get_apple)]

        errors = validate_node_deps(SubclassNode, is_start=False)
        assert errors == []

    def test_recall_on_start_node_error(self):
        """Recall field on a start node is an error."""

        class StartRecallNode(Node):
            prev: Annotated[str, Recall()]

        errors = validate_node_deps(StartRecallNode, is_start=True)
        assert len(errors) >= 1
        assert "recall" in errors[0].lower() or "Recall" in errors[0]

    def test_recall_on_non_start_valid(self):
        """Recall field on a non-start node is fine."""

        class NonStartRecallNode(Node):
            prev: Annotated[str, Recall()]

        errors = validate_node_deps(NonStartRecallNode, is_start=False)
        assert errors == []


# --- Tracked dep functions for cache verification ---

call_count: dict[str, int] = {}


def tracked_get_location() -> str:
    call_count["get_location"] = call_count.get("get_location", 0) + 1
    return "NYC"


def tracked_get_weather(location: Annotated[str, Dep(tracked_get_location)]) -> str:
    call_count["get_weather"] = call_count.get("get_weather", 0) + 1
    return f"Sunny in {location}"


def failing_dep() -> str:
    raise ConnectionError("API down")


class TestResolveDep:
    def test_resolve_leaf_dep(self):
        """Leaf dep with no transitive deps resolves by calling fn directly."""
        cache: dict = {}
        result = resolve_dep(get_location, cache)
        assert result == "NYC"
        assert get_location in cache
        assert cache[get_location] == "NYC"

    def test_resolve_chained_dep(self):
        """Chained dep resolves transitive deps first, passes as kwargs."""
        cache: dict = {}
        result = resolve_dep(get_weather, cache)
        assert result == "Weather in NYC"
        assert get_location in cache
        assert get_weather in cache

    def test_cache_prevents_duplicate_calls(self):
        """Same dep function called once even when resolved through multiple paths."""
        call_count.clear()
        cache: dict = {}
        resolve_dep(tracked_get_weather, cache)
        resolve_dep(tracked_get_weather, cache)
        assert call_count["get_location"] == 1
        assert call_count["get_weather"] == 1

    def test_cache_keyed_by_identity(self):
        """Pre-populated cache entry used instead of calling the dep function."""
        cache: dict = {tracked_get_location: "cached"}
        call_count.clear()
        result = resolve_dep(tracked_get_weather, cache)
        assert result == "Sunny in cached"
        assert call_count.get("get_location", 0) == 0

    def test_dep_exception_propagates_raw(self):
        """Dep function exceptions propagate unwrapped."""
        with pytest.raises(ConnectionError, match="API down"):
            resolve_dep(failing_dep, {})


class TestResolveFields:
    def test_resolve_dep_field(self):
        """Node with a single Dep field resolves to the dep function's return value."""

        class DepFieldNode(Node):
            location: Annotated[str, Dep(get_location)]

        result = resolve_fields(DepFieldNode, trace=[], dep_cache={})
        assert result == {"location": "NYC"}

    def test_resolve_recall_field(self):
        """Node with a single Recall field resolves from trace."""
        trace = [VibeCheck.model_construct(mood="happy")]

        class RecallFieldNode(Node):
            mood: Annotated[str, Recall()]

        result = resolve_fields(RecallFieldNode, trace=trace, dep_cache={})
        assert result == {"mood": "happy"}

    def test_resolve_mixed_fields(self):
        """Dep and Recall fields both resolved; plain fields excluded."""
        trace = [VibeCheck.model_construct(mood="happy")]

        class MixedNode(Node):
            location: Annotated[str, Dep(get_location)]
            mood: Annotated[str, Recall()]
            name: str

        result = resolve_fields(MixedNode, trace=trace, dep_cache={})
        assert "location" in result
        assert result["location"] == "NYC"
        assert "mood" in result
        assert result["mood"] == "happy"
        assert "name" not in result

    def test_resolve_fields_declaration_order(self):
        """Resolved fields appear in declaration order."""
        trace = [VibeCheck.model_construct(mood="happy")]

        class OrderedNode(Node):
            location: Annotated[str, Dep(get_location)]
            mood: Annotated[str, Recall()]
            temperature: Annotated[int, Dep(get_temperature)]

        result = resolve_fields(OrderedNode, trace=trace, dep_cache={})
        keys = list(result.keys())
        assert keys == ["location", "mood", "temperature"]

    def test_resolve_dep_caching_across_fields(self):
        """Shared transitive dep called only once across multiple fields."""
        call_count.clear()

        class SharedDepNode(Node):
            weather: Annotated[str, Dep(tracked_get_weather)]
            location: Annotated[str, Dep(tracked_get_location)]

        resolve_fields(SharedDepNode, trace=[], dep_cache={})
        assert call_count["get_location"] == 1

    def test_resolve_fields_empty_for_plain_only(self):
        """Node with only plain fields returns empty dict."""

        class PlainNode(Node):
            name: str
            value: int

        result = resolve_fields(PlainNode, trace=[], dep_cache={})
        assert result == {}

    def test_dep_cache_persists_across_calls(self):
        """Same dep_cache dict shared across multiple resolve_fields calls."""
        call_count.clear()
        shared_cache: dict = {}

        class NodeA(Node):
            location: Annotated[str, Dep(tracked_get_location)]

        class NodeB(Node):
            weather: Annotated[str, Dep(tracked_get_weather)]

        resolve_fields(NodeA, trace=[], dep_cache=shared_cache)
        resolve_fields(NodeB, trace=[], dep_cache=shared_cache)
        # tracked_get_location was resolved in NodeA, cached for NodeB's
        # tracked_get_weather which transitively depends on tracked_get_location
        assert call_count["get_location"] == 1
