"""TDD tests for auto-routing in Graph.run().

Tests:
1. _has_ellipsis_body detection (node.py)
2. _get_routing_strategy (graph.py)
3. Graph.run() auto-routing integration
"""

import ast
import inspect
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest

from bae.lm import LM
from bae.markers import Context
from bae.node import Node, _has_ellipsis_body
from bae.result import GraphResult


# =============================================================================
# Test Node Classes
# =============================================================================


class TargetA(Node):
    """Target node A for testing."""

    value: str


class TargetB(Node):
    """Target node B for testing."""

    option: str


# Nodes with ellipsis body (auto-routing)
class EllipsisUnionNode(Node):
    """Node with ellipsis body and union return type."""

    content: Annotated[str, Context(description="Content")]

    def __call__(self, lm: LM) -> TargetA | TargetB:
        ...


class EllipsisSingleNode(Node):
    """Node with ellipsis body and single return type."""

    data: Annotated[str, Context(description="Data")]

    def __call__(self, lm: LM) -> TargetA:
        ...


class EllipsisOptionalSingleNode(Node):
    """Node with ellipsis body and optional single return type (A | None)."""

    data: Annotated[str, Context(description="Data")]

    def __call__(self, lm: LM) -> TargetA | None:
        ...


class EllipsisOptionalUnionNode(Node):
    """Node with ellipsis body and optional union return type (A | B | None)."""

    content: Annotated[str, Context(description="Content")]

    def __call__(self, lm: LM) -> TargetA | TargetB | None:
        ...


class EllipsisTerminalNode(Node):
    """Node with ellipsis body and pure None return type."""

    data: Annotated[str, Context(description="Data")]

    def __call__(self, lm: LM) -> None:
        ...


# Nodes with custom logic (escape hatch)
class CustomLogicNode(Node):
    """Node with custom __call__ logic."""

    content: Annotated[str, Context(description="Content")]

    def __call__(self, lm: LM) -> TargetA | TargetB:
        return lm.decide(self)


class CustomMakeNode(Node):
    """Node with custom logic using lm.make."""

    data: Annotated[str, Context(description="Data")]

    def __call__(self, lm: LM) -> TargetA:
        return lm.make(self, TargetA)


class CustomConditionNode(Node):
    """Node with custom conditional logic."""

    query: Annotated[str, Context(description="Query")]

    def __call__(self, lm: LM) -> TargetA | TargetB:
        if "special" in self.query:
            return lm.make(self, TargetB)
        return lm.make(self, TargetA)


# =============================================================================
# Test: _has_ellipsis_body detection
# =============================================================================


class TestHasEllipsisBody:
    """Tests for _has_ellipsis_body() function."""

    def test_ellipsis_body_returns_true(self):
        """Method with only `...` in body returns True."""
        assert _has_ellipsis_body(EllipsisUnionNode.__call__) is True
        assert _has_ellipsis_body(EllipsisSingleNode.__call__) is True

    def test_custom_logic_returns_false(self):
        """Method with actual logic returns False."""
        assert _has_ellipsis_body(CustomLogicNode.__call__) is False
        assert _has_ellipsis_body(CustomMakeNode.__call__) is False
        assert _has_ellipsis_body(CustomConditionNode.__call__) is False

    def test_base_node_returns_false(self):
        """Base Node.__call__ has logic, returns False."""
        assert _has_ellipsis_body(Node.__call__) is False

    def test_ellipsis_terminal_returns_true(self):
        """Terminal node with ellipsis body returns True."""
        assert _has_ellipsis_body(EllipsisTerminalNode.__call__) is True

    def test_ellipsis_optional_returns_true(self):
        """Optional return type with ellipsis body returns True."""
        assert _has_ellipsis_body(EllipsisOptionalSingleNode.__call__) is True
        assert _has_ellipsis_body(EllipsisOptionalUnionNode.__call__) is True
