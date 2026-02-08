"""Tests for v2 markers (Dep with callable, Recall) and field classification."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Annotated

from bae.exceptions import BaeError, RecallError
from bae.markers import Dep, Recall
from bae.node import Node
from bae.resolver import classify_fields


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
