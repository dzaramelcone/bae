"""Tests for GraphResult and exception hierarchy."""

import pytest

from bae.result import GraphResult
from bae.exceptions import BaeError, BaeParseError, BaeLMError
from bae.node import Node


# Test node classes
class NodeA(Node):
    x: str = ""


class NodeB(Node):
    y: str = ""


class NodeC(Node):
    z: str = ""


class TestGraphResult:
    """Tests for GraphResult dataclass."""

    def test_graphresult_with_node_and_trace(self):
        """GraphResult holds final node and execution trace."""
        n1 = NodeA(x="first")
        n2 = NodeB(y="second")
        n3 = NodeC(z="final")

        result = GraphResult(node=n3, trace=[n1, n2, n3])

        assert result.node is n3
        assert result.trace == [n1, n2, n3]

    def test_graphresult_with_none_node(self):
        """GraphResult with None node is valid (terminated normally)."""
        n1 = NodeA(x="only")

        result = GraphResult(node=None, trace=[n1])

        assert result.node is None
        assert result.trace == [n1]

    def test_graphresult_empty_trace(self):
        """GraphResult with empty trace is valid."""
        result = GraphResult(node=None, trace=[])

        assert result.node is None
        assert result.trace == []

    def test_trace_is_flat_list(self):
        """Trace is a flat list of nodes in execution order."""
        nodes = [NodeA(x="1"), NodeB(y="2"), NodeA(x="3")]
        result = GraphResult(node=nodes[-1], trace=nodes)

        # Verify it's a flat list, not nested
        assert isinstance(result.trace, list)
        assert len(result.trace) == 3
        for node in result.trace:
            assert isinstance(node, Node)


class TestBaeExceptions:
    """Tests for exception hierarchy."""

    def test_bae_error_is_base_exception(self):
        """BaeError is the base exception class."""
        err = BaeError("something went wrong")
        assert isinstance(err, Exception)
        assert str(err) == "something went wrong"

    def test_bae_error_chains_cause(self):
        """BaeError wraps original error as __cause__."""
        original = ValueError("original error")
        err = BaeError("wrapped", cause=original)

        assert err.__cause__ is original

    def test_bae_parse_error_inherits(self):
        """BaeParseError inherits from BaeError."""
        err = BaeParseError("parse failed")
        assert isinstance(err, BaeError)

    def test_bae_parse_error_chains_cause(self):
        """BaeParseError chains original error."""
        original = ValueError("bad value")
        err = BaeParseError("validation failed", cause=original)

        assert err.__cause__ is original
        assert str(err) == "validation failed"

    def test_bae_lm_error_inherits(self):
        """BaeLMError inherits from BaeError."""
        err = BaeLMError("API timeout")
        assert isinstance(err, BaeError)

    def test_bae_lm_error_chains_cause(self):
        """BaeLMError chains original error (e.g., TimeoutError)."""
        original = TimeoutError("connection timed out")
        err = BaeLMError("timeout", cause=original)

        assert err.__cause__ is original

    def test_exceptions_can_be_caught_by_base(self):
        """Both BaeParseError and BaeLMError can be caught as BaeError."""
        exceptions = [
            BaeParseError("parse"),
            BaeLMError("lm"),
        ]

        for exc in exceptions:
            with pytest.raises(BaeError):
                raise exc
