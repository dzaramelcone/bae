"""Tests for v2 markers (Dep with callable, Recall) and field classification."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest

from bae.exceptions import BaeError, RecallError
from bae.markers import Dep, Recall
from bae.node import Node
from bae.resolver import classify_fields, recall_from_trace


def get_data() -> str:
    return "test data"


def get_other() -> str:
    return "other data"


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
