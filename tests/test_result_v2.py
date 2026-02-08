"""Tests for GraphResult.result property and Generic[T] support.

Tests the redesigned GraphResult which:
- Exposes a `.result` property returning the terminal node (trace[-1])
- Is Generic[T] where T defaults to Node for typed terminal access
- Maintains backward compatibility with existing construction and fields
"""

from bae.node import Node
from bae.result import GraphResult


# -- Test node subclasses ---------------------------------------------------


class Alpha(Node):
    a: str = "alpha"


class Beta(Node):
    b: str = "beta"


class Gamma(Node):
    g: str = "gamma"


# -- Tests: .result property ------------------------------------------------


class TestGraphResultProperty:
    """Tests for GraphResult.result returning the terminal node."""

    def test_result_returns_last_node_in_trace(self):
        """GraphResult.result is trace[-1], the terminal node."""
        a = Alpha()
        b = Beta()
        c = Gamma()
        gr = GraphResult(node=None, trace=[a, b, c])

        assert gr.result is c

    def test_result_with_empty_trace_is_none(self):
        """GraphResult.result is None when trace is empty."""
        gr = GraphResult(node=None, trace=[])

        assert gr.result is None

    def test_result_with_single_node_trace(self):
        """GraphResult.result returns the only node when trace has one entry."""
        a = Alpha()
        gr = GraphResult(node=None, trace=[a])

        assert gr.result is a

    def test_result_is_same_object_as_trace_last(self):
        """GraphResult.result is the same object (identity) as trace[-1]."""
        a = Alpha(a="first")
        b = Beta(b="second")
        gr = GraphResult(node=None, trace=[a, b])

        assert gr.result is gr.trace[-1]


# -- Tests: backward compatibility -----------------------------------------


class TestGraphResultBackwardCompat:
    """Ensure existing construction and field access still works."""

    def test_construction_with_node_and_trace(self):
        """GraphResult(node=..., trace=...) construction still works."""
        a = Alpha()
        b = Beta()
        gr = GraphResult(node=a, trace=[a, b])

        assert gr.node is a
        assert gr.trace == [a, b]

    def test_node_field_still_accessible(self):
        """result.node still returns the node field value."""
        b = Beta()
        gr = GraphResult(node=b, trace=[b])

        assert gr.node is b

    def test_node_none_still_works(self):
        """GraphResult(node=None, ...) still valid."""
        a = Alpha()
        gr = GraphResult(node=None, trace=[a])

        assert gr.node is None

    def test_trace_is_ordered_list(self):
        """GraphResult.trace is an accessible ordered list."""
        a = Alpha()
        b = Beta()
        c = Gamma()
        gr = GraphResult(node=None, trace=[a, b, c])

        assert isinstance(gr.trace, list)
        assert len(gr.trace) == 3
        assert gr.trace[0] is a
        assert gr.trace[1] is b
        assert gr.trace[2] is c


# -- Tests: Generic[T] type annotation support ------------------------------


class TestGraphResultGeneric:
    """Tests for GraphResult Generic[T] support.

    These tests verify that GraphResult is generic and can be parameterized.
    The typing benefit is at the type-checker level, but we verify the
    runtime mechanics work correctly.
    """

    def test_graphresult_is_generic(self):
        """GraphResult can be parameterized with a type (runtime subscript)."""
        # This should not raise -- GraphResult[Alpha] is valid at runtime
        specialized = GraphResult[Alpha]
        assert specialized is not None

    def test_generic_subscript_still_constructs(self):
        """GraphResult[T] subscript can still be used for isinstance-like checks."""
        # Verify the base class works after parameterization
        a = Alpha()
        gr = GraphResult(node=None, trace=[a])
        assert isinstance(gr, GraphResult)

    def test_unparameterized_still_works(self):
        """GraphResult without type parameter works (default T=Node)."""
        a = Alpha()
        gr = GraphResult(node=None, trace=[a])

        # .result still works without parameterization
        assert gr.result is a
