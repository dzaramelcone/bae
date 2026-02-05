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
from bae.graph import Graph, _get_routing_strategy
from bae.node import Node, _has_ellipsis_body
from bae.result import GraphResult


# =============================================================================
# Test Node Classes
# =============================================================================


class TargetA(Node):
    """Target node A for testing."""

    value: str

    def __call__(self, lm: LM) -> None:
        ...


class TargetB(Node):
    """Target node B for testing."""

    option: str

    def __call__(self, lm: LM) -> None:
        ...


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


# Terminal node for integration tests
class TerminalTarget(Node):
    """Terminal target node."""

    done: str = "yes"

    def __call__(self, lm: LM) -> None:
        ...


# Start node with union return for graph tests
class StartUnionNode(Node):
    """Start node with union return type and ellipsis body."""

    content: Annotated[str, Context(description="Content")]

    def __call__(self, lm: LM) -> TerminalTarget | TargetB:
        ...


# Start node with single return for graph tests
class StartSingleNode(Node):
    """Start node with single return type and ellipsis body."""

    data: Annotated[str, Context(description="Data")]

    def __call__(self, lm: LM) -> TerminalTarget:
        ...


# Start node with custom logic for graph tests
class StartCustomNode(Node):
    """Start node with custom logic (escape hatch)."""

    data: Annotated[str, Context(description="Data")]
    call_count: int = 0

    def __call__(self, lm: LM) -> TerminalTarget:
        # This is custom logic - not just ellipsis
        return lm.make(self, TerminalTarget)


# Mid-step node for trace tests
class MidNode(Node):
    """Middle step node."""

    mid: str = "middle"

    def __call__(self, lm: LM) -> TerminalTarget:
        ...


# Pure terminal start node for terminal test
class PureTerminalNode(Node):
    """Node that only returns None."""

    data: str = "done"

    def __call__(self, lm: LM) -> None:
        ...


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


# =============================================================================
# Test: _get_routing_strategy
# =============================================================================


class TestGetRoutingStrategy:
    """Tests for _get_routing_strategy() function."""

    def test_union_ellipsis_returns_decide(self):
        """Union return type with ellipsis body returns 'decide' strategy."""
        strategy, types_list = _get_routing_strategy(EllipsisUnionNode)
        assert strategy == "decide"
        assert set(types_list) == {TargetA, TargetB}

    def test_single_ellipsis_returns_make(self):
        """Single return type with ellipsis body returns 'make' strategy."""
        strategy, target = _get_routing_strategy(EllipsisSingleNode)
        assert strategy == "make"
        assert target is TargetA

    def test_optional_single_ellipsis_returns_decide(self):
        """A | None with ellipsis body returns 'decide' (choice between A and None)."""
        strategy, types_list = _get_routing_strategy(EllipsisOptionalSingleNode)
        assert strategy == "decide"
        assert set(types_list) == {TargetA}

    def test_optional_union_ellipsis_returns_decide(self):
        """A | B | None with ellipsis body returns 'decide' strategy."""
        strategy, types_list = _get_routing_strategy(EllipsisOptionalUnionNode)
        assert strategy == "decide"
        assert set(types_list) == {TargetA, TargetB}

    def test_terminal_ellipsis_returns_terminal(self):
        """Pure None return with ellipsis body returns 'terminal' strategy."""
        strategy_result = _get_routing_strategy(EllipsisTerminalNode)
        assert strategy_result == ("terminal",)

    def test_custom_logic_returns_custom(self):
        """Node with custom logic returns 'custom' strategy."""
        strategy_result = _get_routing_strategy(CustomLogicNode)
        assert strategy_result == ("custom",)

    def test_custom_make_returns_custom(self):
        """Node with custom make logic returns 'custom' strategy."""
        strategy_result = _get_routing_strategy(CustomMakeNode)
        assert strategy_result == ("custom",)

    def test_base_node_returns_custom(self):
        """Base Node class returns 'custom' strategy."""
        strategy_result = _get_routing_strategy(Node)
        assert strategy_result == ("custom",)


# =============================================================================
# Test: Graph.run() auto-routing integration
# =============================================================================


class MockLM:
    """Mock LM that returns nodes from a sequence."""

    def __init__(self, sequence: list[Node | None] | None = None):
        self.sequence = sequence or []
        self.index = 0
        self.make_calls: list[tuple[Node, type]] = []
        self.decide_calls: list[Node] = []

    def make(self, node: Node, target: type) -> Node:
        self.make_calls.append((node, target))
        result = self.sequence[self.index]
        self.index += 1
        return result

    def decide(self, node: Node) -> Node | None:
        self.decide_calls.append(node)
        result = self.sequence[self.index]
        self.index += 1
        return result


class TestGraphRunAutoRouting:
    """Tests for Graph.run() auto-routing based on ellipsis body."""

    def test_ellipsis_union_calls_lm_decide(self):
        """Ellipsis body with union return type calls lm.decide."""
        graph = Graph(start=StartUnionNode)
        lm = MockLM(sequence=[TerminalTarget(), None])

        result = graph.run(StartUnionNode(content="test"), lm=lm)

        # Should have called decide for StartNode
        assert len(lm.decide_calls) == 1

    def test_ellipsis_single_calls_lm_make(self):
        """Ellipsis body with single return type calls lm.make."""
        graph = Graph(start=StartSingleNode)
        lm = MockLM(sequence=[TerminalTarget(), None])

        result = graph.run(StartSingleNode(data="test"), lm=lm)

        # Should have called make for StartNode
        assert len(lm.make_calls) == 1
        assert lm.make_calls[0][1] is TerminalTarget

    def test_custom_logic_called_directly(self):
        """Node with custom logic is called directly (escape hatch)."""
        graph = Graph(start=StartCustomNode)
        lm = MockLM(sequence=[TerminalTarget(), None])

        result = graph.run(StartCustomNode(data="test"), lm=lm)

        # Custom __call__ was invoked via make()
        # (StartCustomNode calls lm.make internally)
        assert len(lm.make_calls) == 1

    def test_ellipsis_terminal_returns_graph_result_with_none(self):
        """Ellipsis body with pure None return type returns GraphResult with node=None."""
        graph = Graph(start=PureTerminalNode)
        lm = MockLM(sequence=[])  # No LM calls needed

        result = graph.run(PureTerminalNode(), lm=lm)

        # Should return GraphResult with node=None
        assert isinstance(result, GraphResult)
        assert result.node is None
        assert len(result.trace) == 1  # Just the start node
        # No LM calls should have been made
        assert len(lm.make_calls) == 0
        assert len(lm.decide_calls) == 0

    def test_graph_run_returns_graph_result(self):
        """Graph.run() returns GraphResult with node and trace."""
        graph = Graph(start=StartSingleNode)
        terminal = TerminalTarget()
        lm = MockLM(sequence=[terminal, None])

        result = graph.run(StartSingleNode(data="test"), lm=lm)

        # Should return GraphResult
        assert isinstance(result, GraphResult)
        assert result.node is None  # Terminal node returned None
        assert len(result.trace) >= 1  # At least start node

    def test_trace_includes_all_nodes(self):
        """GraphResult.trace includes all visited nodes in order."""
        graph = Graph(start=StartSingleNode)
        start = StartSingleNode(data="test")
        mid = MidNode()
        end = TerminalTarget()
        lm = MockLM(sequence=[mid, end, None])

        result = graph.run(start, lm=lm)

        assert isinstance(result, GraphResult)
        assert len(result.trace) == 3
        assert result.trace[0] is start
        assert result.trace[1] is mid
        assert result.trace[2] is end
