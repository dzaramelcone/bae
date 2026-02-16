"""Tests for v2 markers (Dep with callable, Recall) and field classification."""

from __future__ import annotations

import asyncio
import graphlib
import time
from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest

from bae.exceptions import BaeError, RecallError
from bae.markers import Dep, Gate, Recall
from bae.node import Node
from bae.resolver import (
    LM_KEY,
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

    def test_classify_gate_field(self):
        """Gate-annotated field is classified as 'gate'."""

        class TestNode(Node):
            approved: Annotated[bool, Gate(description="Approve?")]

        result = classify_fields(TestNode)
        assert result["approved"] == "gate"

    def test_gate_excluded_from_plain_model(self):
        """_build_plain_model excludes gate-annotated fields."""
        from bae.lm import _build_plain_model

        class TestNode(Node):
            approved: Annotated[bool, Gate(description="Approve?")]
            reason: str

        PlainModel = _build_plain_model(TestNode)
        assert "approved" not in PlainModel.model_fields
        assert "reason" in PlainModel.model_fields

    def test_recall_skips_gate_fields(self):
        """recall_from_trace skips gate-annotated fields when searching."""

        class GateNode(Node):
            gated: Annotated[str, Gate(description="Enter value")]
            plain_val: str

        node = GateNode.model_construct(gated="gate value", plain_val="real value")
        trace = [node]
        assert recall_from_trace(trace, str) == "real value"

    def test_gate_and_plain_coexist(self):
        """Gate and plain fields classified correctly on the same node."""

        class TestNode(Node):
            approved: Annotated[bool, Gate(description="Approve?")]
            reason: str

        result = classify_fields(TestNode)
        assert result["approved"] == "gate"
        assert result["reason"] == "plain"


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
    async def test_resolve_leaf_dep(self):
        """Leaf dep with no transitive deps resolves by calling fn directly."""
        cache: dict = {}
        result = await resolve_dep(get_location, cache)
        assert result == "NYC"
        assert get_location in cache
        assert cache[get_location] == "NYC"

    async def test_resolve_chained_dep(self):
        """Chained dep resolves transitive deps first, passes as kwargs."""
        cache: dict = {}
        result = await resolve_dep(get_weather, cache)
        assert result == "Weather in NYC"
        assert get_location in cache
        assert get_weather in cache

    async def test_cache_prevents_duplicate_calls(self):
        """Same dep function called once even when resolved through multiple paths."""
        call_count.clear()
        cache: dict = {}
        await resolve_dep(tracked_get_weather, cache)
        await resolve_dep(tracked_get_weather, cache)
        assert call_count["get_location"] == 1
        assert call_count["get_weather"] == 1

    async def test_cache_keyed_by_identity(self):
        """Pre-populated cache entry used instead of calling the dep function."""
        cache: dict = {tracked_get_location: "cached"}
        call_count.clear()
        result = await resolve_dep(tracked_get_weather, cache)
        assert result == "Sunny in cached"
        assert call_count.get("get_location", 0) == 0

    async def test_dep_exception_propagates_raw(self):
        """Dep function exceptions propagate unwrapped."""
        with pytest.raises(ConnectionError, match="API down"):
            await resolve_dep(failing_dep, {})


class TestResolveFields:
    async def test_resolve_dep_field(self):
        """Node with a single Dep field resolves to the dep function's return value."""

        class DepFieldNode(Node):
            location: Annotated[str, Dep(get_location)]

        result = await resolve_fields(DepFieldNode, trace=[], dep_cache={})
        assert result == {"location": "NYC"}

    async def test_resolve_recall_field(self):
        """Node with a single Recall field resolves from trace."""
        trace = [VibeCheck.model_construct(mood="happy")]

        class RecallFieldNode(Node):
            mood: Annotated[str, Recall()]

        result = await resolve_fields(RecallFieldNode, trace=trace, dep_cache={})
        assert result == {"mood": "happy"}

    async def test_resolve_mixed_fields(self):
        """Dep and Recall fields both resolved; plain fields excluded."""
        trace = [VibeCheck.model_construct(mood="happy")]

        class MixedNode(Node):
            location: Annotated[str, Dep(get_location)]
            mood: Annotated[str, Recall()]
            name: str

        result = await resolve_fields(MixedNode, trace=trace, dep_cache={})
        assert "location" in result
        assert result["location"] == "NYC"
        assert "mood" in result
        assert result["mood"] == "happy"
        assert "name" not in result

    async def test_resolve_fields_declaration_order(self):
        """Resolved fields appear in declaration order."""
        trace = [VibeCheck.model_construct(mood="happy")]

        class OrderedNode(Node):
            location: Annotated[str, Dep(get_location)]
            mood: Annotated[str, Recall()]
            temperature: Annotated[int, Dep(get_temperature)]

        result = await resolve_fields(OrderedNode, trace=trace, dep_cache={})
        keys = list(result.keys())
        assert keys == ["location", "mood", "temperature"]

    async def test_resolve_dep_caching_across_fields(self):
        """Shared transitive dep called only once across multiple fields."""
        call_count.clear()

        class SharedDepNode(Node):
            weather: Annotated[str, Dep(tracked_get_weather)]
            location: Annotated[str, Dep(tracked_get_location)]

        await resolve_fields(SharedDepNode, trace=[], dep_cache={})
        assert call_count["get_location"] == 1

    async def test_resolve_fields_empty_for_plain_only(self):
        """Node with only plain fields returns empty dict."""

        class PlainNode(Node):
            name: str
            value: int

        result = await resolve_fields(PlainNode, trace=[], dep_cache={})
        assert result == {}

    async def test_dep_cache_persists_across_calls(self):
        """Same dep_cache dict shared across multiple resolve_fields calls."""
        call_count.clear()
        shared_cache: dict = {}

        class NodeA(Node):
            location: Annotated[str, Dep(tracked_get_location)]

        class NodeB(Node):
            weather: Annotated[str, Dep(tracked_get_weather)]

        await resolve_fields(NodeA, trace=[], dep_cache=shared_cache)
        await resolve_fields(NodeB, trace=[], dep_cache=shared_cache)
        # tracked_get_location was resolved in NodeA, cached for NodeB's
        # tracked_get_weather which transitively depends on tracked_get_location
        assert call_count["get_location"] == 1


# =============================================================================
# Node-as-Dep tests
# =============================================================================

# --- Mock LM for Node-as-Dep tests ---

lm_fill_count: dict[str, int] = {}


class MockLM:
    """Minimal LM that fills plain fields with deterministic values."""

    async def fill(self, target, resolved, instruction, source=None):
        lm_fill_count[target.__name__] = lm_fill_count.get(target.__name__, 0) + 1
        # Sleep to simulate LLM latency (used by concurrency test)
        await asyncio.sleep(0.05)
        # Build plain fields with deterministic values
        from bae.resolver import classify_fields

        fields = classify_fields(target)
        all_fields = dict(resolved)
        for name, kind in fields.items():
            if kind == "plain" and name not in all_fields and name in target.model_fields:
                field_info = target.model_fields[name]
                ann = field_info.annotation
                if ann is str:
                    all_fields[name] = f"mock_{name}"
                elif ann == list[str]:
                    all_fields[name] = [f"mock_{name}_1"]
                else:
                    all_fields[name] = f"mock_{name}"
        return target.model_construct(**all_fields)

    async def make(self, node, target):
        raise NotImplementedError

    async def decide(self, node):
        raise NotImplementedError

    async def choose_type(self, types, context):
        raise NotImplementedError


# --- Node-as-Dep test node types ---


class UserInfo(Node):
    """Data model used as Recall source."""

    name: str = "Dzara"


class StartNode(Node):
    """Start node with a UserInfo field — provides Recall source in trace."""

    user_info: UserInfo

    async def __call__(self) -> None: ...


class InferBackground(Node):
    """Node-as-Dep target: has a Recall + plain fields."""

    user_info: Annotated[UserInfo, Recall()]
    occupation: str
    lifestyle: str


class InferPersonality(Node):
    """Another Node-as-Dep target: Recall + plain fields."""

    user_info: Annotated[UserInfo, Recall()]
    mbti: str


class BuildWardrobe(Node):
    """Node-as-Dep that itself depends on other Node-as-Deps."""

    user_info: Annotated[UserInfo, Recall()]
    background: Annotated[InferBackground, Dep()]
    personality: Annotated[InferPersonality, Dep()]
    tops: list[str]


class FinalNode(Node):
    """Top-level node with a single Node-as-Dep."""

    wardrobe: Annotated[BuildWardrobe, Dep()]
    recommendation: str


class TwoDepNode(Node):
    """Node with two independent Node-as-Deps for concurrency test."""

    bg: Annotated[InferBackground, Dep()]
    personality: Annotated[InferPersonality, Dep()]
    summary: str


class ReuseSameDepNode(Node):
    """Two fields that reference the same Node-as-Dep type."""

    a: Annotated[InferBackground, Dep()]
    b: Annotated[InferBackground, Dep()]
    output: str


class TestNodeDepInDag:
    def test_node_dep_in_dag(self):
        """build_dep_dag includes Node deps and their transitive deps."""

        class Host(Node):
            bg: Annotated[InferBackground, Dep()]

        ts = build_dep_dag(Host)
        order = list(ts.static_order())
        assert InferBackground in order

    def test_node_dep_transitive_in_dag(self):
        """Node dep that itself has Node deps: all appear in DAG."""
        ts = build_dep_dag(FinalNode)
        order = list(ts.static_order())
        assert InferBackground in order
        assert InferPersonality in order
        assert BuildWardrobe in order

    def test_node_dep_ordering(self):
        """Transitive Node deps come before the node that depends on them."""
        ts = build_dep_dag(FinalNode)
        order = list(ts.static_order())
        bg_idx = order.index(InferBackground)
        pers_idx = order.index(InferPersonality)
        wardrobe_idx = order.index(BuildWardrobe)
        assert bg_idx < wardrobe_idx
        assert pers_idx < wardrobe_idx


class TestNodeDepResolves:
    async def test_node_dep_resolves(self):
        """Basic Node-as-Dep: Recall + plain fields filled via mock LM."""
        lm_fill_count.clear()
        mock_lm = MockLM()
        trace = [StartNode.model_construct(user_info=UserInfo(name="Dzara"))]
        cache: dict = {LM_KEY: mock_lm}

        class Host(Node):
            bg: Annotated[InferBackground, Dep()]

        result = await resolve_fields(Host, trace=trace, dep_cache=cache)
        assert "bg" in result
        bg = result["bg"]
        assert isinstance(bg, InferBackground)
        # Recall field should be resolved from trace
        assert bg.user_info.name == "Dzara"
        # Plain fields should be filled by mock LM
        assert bg.occupation == "mock_occupation"
        assert bg.lifestyle == "mock_lifestyle"

    async def test_node_dep_concurrent(self):
        """Two independent Node deps fire concurrently via gather."""
        lm_fill_count.clear()
        mock_lm = MockLM()
        trace = [StartNode.model_construct(user_info=UserInfo(name="Dzara"))]
        cache: dict = {LM_KEY: mock_lm}

        t0 = time.monotonic()
        result = await resolve_fields(TwoDepNode, trace=trace, dep_cache=cache)
        elapsed = time.monotonic() - t0

        assert "bg" in result
        assert "personality" in result
        # Two 50ms sleeps should overlap — total < 150ms if concurrent
        # (sequential would be >= 100ms, concurrent ~50ms + overhead)
        assert elapsed < 0.15, f"Took {elapsed:.3f}s — deps may not be concurrent"

    async def test_node_dep_chained(self):
        """Node dep depending on another Node dep resolves in order."""
        lm_fill_count.clear()
        mock_lm = MockLM()
        trace = [StartNode.model_construct(user_info=UserInfo(name="Dzara"))]
        cache: dict = {LM_KEY: mock_lm}

        result = await resolve_fields(FinalNode, trace=trace, dep_cache=cache)
        wardrobe = result["wardrobe"]
        assert isinstance(wardrobe, BuildWardrobe)
        # Chained deps should be resolved
        assert isinstance(wardrobe.background, InferBackground)
        assert isinstance(wardrobe.personality, InferPersonality)

    async def test_node_dep_cached(self):
        """Same Node dep referenced twice → only one LM call."""
        lm_fill_count.clear()
        mock_lm = MockLM()
        trace = [StartNode.model_construct(user_info=UserInfo(name="Dzara"))]
        cache: dict = {LM_KEY: mock_lm}

        result = await resolve_fields(ReuseSameDepNode, trace=trace, dep_cache=cache)
        # Both fields should get the same instance
        assert result["a"] is result["b"]
        # LM fill should only be called once for InferBackground
        assert lm_fill_count.get("InferBackground", 0) == 1


class TestValidateAcceptsNodeDep:
    def test_validate_accepts_node_dep(self):
        """validate_node_deps doesn't error on Dep() + Node type."""

        class NodeWithNodeDep(Node):
            bg: Annotated[InferBackground, Dep()]

        errors = validate_node_deps(NodeWithNodeDep, is_start=False)
        assert errors == []

    def test_validate_accepts_chained_node_dep(self):
        """validate_node_deps doesn't error on chained Node-as-Deps."""
        errors = validate_node_deps(FinalNode, is_start=False)
        assert errors == []
