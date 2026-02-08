"""Tests for DepError and FillError exception subclasses.

DepError: raised when a Dep function fails during field resolution.
FillError: raised when LM fill validation fails after retries.
Both inherit from BaeError and carry structured attributes for diagnostics.
"""

from bae.exceptions import BaeError, DepError, FillError
from bae.node import Node


class SomeNode(Node):
    """Dummy node for exception tests."""

    value: str

    def __call__(self) -> None: ...


# =============================================================================
# Test: DepError
# =============================================================================


class TestDepError:
    """DepError carries node_type, field_name and formats tersely."""

    def test_stores_attributes(self):
        """DepError stores node_type and field_name."""
        err = DepError(
            "fetch_user failed on SomeNode.user_data",
            node_type=SomeNode,
            field_name="user_data",
        )
        assert err.node_type is SomeNode
        assert err.field_name == "user_data"

    def test_str_format(self):
        """str(DepError) uses the message as-is."""
        msg = "DepError: fetch_user failed on SomeNode.user_data"
        err = DepError(msg, node_type=SomeNode, field_name="user_data")
        assert str(err) == msg

    def test_subclass_of_bae_error(self):
        """DepError is a subclass of BaeError."""
        assert issubclass(DepError, BaeError)
        err = DepError("test")
        assert isinstance(err, BaeError)

    def test_trace_attribute_defaults_none(self):
        """err.trace defaults to None."""
        err = DepError("test")
        assert err.trace is None

    def test_trace_attribute_settable(self):
        """err.trace can be set to a list."""
        err = DepError("test")
        err.trace = [SomeNode, SomeNode]
        assert err.trace == [SomeNode, SomeNode]

    def test_exception_chaining(self):
        """raise DepError(...) from original preserves __cause__."""
        original = ValueError("connection refused")
        try:
            raise DepError(
                "fetch_user failed on SomeNode.user_data",
                node_type=SomeNode,
                field_name="user_data",
            ) from original
        except DepError as err:
            assert err.__cause__ is original
            assert isinstance(err.__cause__, ValueError)

    def test_cause_kwarg(self):
        """DepError(cause=exc) sets __cause__ via BaeError."""
        original = RuntimeError("boom")
        err = DepError("test", cause=original)
        assert err.__cause__ is original


# =============================================================================
# Test: FillError
# =============================================================================


class TestFillError:
    """FillError carries node_type, validation_errors, attempts."""

    def test_stores_attributes(self):
        """FillError stores node_type, validation_errors, and attempts."""
        err = FillError(
            "validation failed for SomeNode after 3 attempts",
            node_type=SomeNode,
            validation_errors="field X required",
            attempts=3,
        )
        assert err.node_type is SomeNode
        assert err.validation_errors == "field X required"
        assert err.attempts == 3

    def test_str_includes_context(self):
        """str(FillError) includes node type, attempt count, and validation error."""
        msg = "FillError: SomeNode fill failed after 3 attempts: field X required"
        err = FillError(
            msg,
            node_type=SomeNode,
            validation_errors="field X required",
            attempts=3,
        )
        assert "SomeNode" in str(err)
        assert "3" in str(err)
        assert "field X required" in str(err)

    def test_subclass_of_bae_error(self):
        """FillError is a subclass of BaeError."""
        assert issubclass(FillError, BaeError)
        err = FillError("test")
        assert isinstance(err, BaeError)

    def test_trace_attribute_defaults_none(self):
        """err.trace defaults to None."""
        err = FillError("test")
        assert err.trace is None

    def test_trace_attribute_settable(self):
        """err.trace can be set to a list."""
        err = FillError("test")
        err.trace = [SomeNode]
        assert err.trace == [SomeNode]

    def test_cause_kwarg(self):
        """FillError(cause=exc) sets __cause__ via BaeError."""
        original = RuntimeError("LM failed")
        err = FillError("test", cause=original)
        assert err.__cause__ is original

    def test_exception_chaining(self):
        """raise FillError(...) from original preserves __cause__."""
        original = ValueError("validation error")
        try:
            raise FillError(
                "fill failed",
                node_type=SomeNode,
                validation_errors="bad",
                attempts=2,
            ) from original
        except FillError as err:
            assert err.__cause__ is original
