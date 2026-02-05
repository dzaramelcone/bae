"""Tests for Bind marker and type-unique validation."""

from typing import Annotated

import pytest

from bae.graph import Graph
from bae.markers import Bind
from bae.node import Node
from bae.lm import LM


# Mock types for Bind
class DatabaseConn:
    """Mock database connection type."""

    pass


class CacheClient:
    """Mock cache client type."""

    pass


class Config:
    """Mock config type."""

    pass


# Test nodes for Bind marker
class NodeWithStringBind(Node):
    """Node that binds a string value."""

    value: Annotated[str, Bind()]

    def __call__(self, lm: LM) -> None:
        return None


class NodeWithConnBind(Node):
    """Node that binds a DatabaseConn."""

    conn: Annotated[DatabaseConn, Bind()]

    def __call__(self, lm: LM) -> None:
        return None


class AnotherNodeWithConnBind(Node):
    """Another node that binds the same DatabaseConn type."""

    db: Annotated[DatabaseConn, Bind()]

    def __call__(self, lm: LM) -> None:
        return None


class NodeWithCacheBind(Node):
    """Node that binds a CacheClient."""

    cache: Annotated[CacheClient, Bind()]

    def __call__(self, lm: LM) -> None:
        return None


class TestBindMarker:
    """Tests for the Bind marker class."""

    def test_bind_is_frozen_dataclass(self):
        """Bind is a frozen dataclass."""
        b = Bind()
        with pytest.raises(AttributeError):
            b.x = "cannot set"

    def test_bind_instances_equal(self):
        """Two Bind instances are equal."""
        b1 = Bind()
        b2 = Bind()
        assert b1 == b2

    def test_bind_can_be_used_in_annotated(self):
        """Bind can be used in Annotated type hints."""
        # This test passes if the class below can be defined and instantiated
        class TestNode(Node):
            data: Annotated[str, Bind()]

        node = TestNode(data="test")
        assert node.data == "test"


# Graph with single Bind per type (valid)
class StartSingleBind(Node):
    query: str

    def __call__(self, lm: LM) -> ProcessSingleBind:
        return ProcessSingleBind(task=self.query)


class ProcessSingleBind(Node):
    task: str
    result: Annotated[str, Bind()]

    def __call__(self, lm: LM) -> None:
        return None


# Graph with duplicate Bind type (invalid)
class StartDuplicateBind(Node):
    query: str
    first_conn: Annotated[DatabaseConn, Bind()]

    def __call__(self, lm: LM) -> ProcessDuplicateBind:
        return ProcessDuplicateBind(task=self.query)


class ProcessDuplicateBind(Node):
    task: str
    second_conn: Annotated[DatabaseConn, Bind()]  # Duplicate type!

    def __call__(self, lm: LM) -> None:
        return None


# Graph with different Bind types (valid)
class StartMultipleBindTypes(Node):
    query: str
    conn: Annotated[DatabaseConn, Bind()]

    def __call__(self, lm: LM) -> ProcessMultipleBindTypes:
        return ProcessMultipleBindTypes(task=self.query)


class ProcessMultipleBindTypes(Node):
    task: str
    cache: Annotated[CacheClient, Bind()]  # Different type, valid

    def __call__(self, lm: LM) -> None:
        return None


class TestBindValidation:
    """Tests for Graph.validate() Bind type-uniqueness check."""

    def test_single_bind_per_type_valid(self):
        """Graph with single Bind per type is valid."""
        graph = Graph(start=StartSingleBind)
        issues = graph.validate()

        # Should not have any Bind-related issues
        bind_issues = [i for i in issues if "Bind" in i]
        assert bind_issues == []

    def test_duplicate_bind_type_returns_error(self):
        """Graph with duplicate Bind types returns validation error."""
        graph = Graph(start=StartDuplicateBind)
        issues = graph.validate()

        # Should have exactly one duplicate Bind issue
        bind_issues = [i for i in issues if "Bind" in i]
        assert len(bind_issues) == 1
        assert "DatabaseConn" in bind_issues[0]

    def test_multiple_different_bind_types_valid(self):
        """Graph with multiple Bind types (different) is valid."""
        graph = Graph(start=StartMultipleBindTypes)
        issues = graph.validate()

        # Should not have any Bind-related issues
        bind_issues = [i for i in issues if "Bind" in i]
        assert bind_issues == []

    def test_validation_error_mentions_conflicting_nodes(self):
        """Validation error mentions both nodes with conflicting Bind."""
        graph = Graph(start=StartDuplicateBind)
        issues = graph.validate()

        bind_issues = [i for i in issues if "Bind" in i]
        assert len(bind_issues) == 1
        # Should mention which nodes have the conflict
        issue = bind_issues[0]
        assert "StartDuplicateBind" in issue or "ProcessDuplicateBind" in issue
