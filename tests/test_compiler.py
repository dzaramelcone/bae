"""TDD tests for node_to_signature conversion.

Tests the conversion of bae Node classes to DSPy Signature classes.
"""

from typing import Annotated

import dspy
import pytest

from bae.markers import Context, Dep
from bae.node import Node


class TestNodeToSignature:
    """Test node_to_signature() function."""

    def test_class_name_becomes_instruction(self):
        """Case 1: Class name becomes the Signature instruction."""
        from bae.compiler import node_to_signature

        class AnalyzeUserIntent(Node):
            pass

        sig = node_to_signature(AnalyzeUserIntent)
        assert sig.instructions == "AnalyzeUserIntent"

    def test_annotated_field_becomes_input_field(self):
        """Case 2: Annotated field with Context becomes InputField."""
        from bae.compiler import node_to_signature

        class ProcessRequest(Node):
            request: Annotated[str, Context(description="The user's request")]

        sig = node_to_signature(ProcessRequest)
        assert "request" in sig.input_fields
        assert sig.input_fields["request"].json_schema_extra["desc"] == "The user's request"

    def test_unannotated_field_excluded(self):
        """Case 3: Unannotated fields are excluded from Signature."""
        from bae.compiler import node_to_signature

        class ProcessRequest(Node):
            request: Annotated[str, Context(description="The user's request")]
            internal_counter: int = 0  # No Annotated wrapper

        sig = node_to_signature(ProcessRequest)
        assert "request" in sig.input_fields
        assert "internal_counter" not in sig.input_fields

    def test_multiple_annotated_fields(self):
        """Case 4: Multiple annotated fields all become InputFields."""
        from bae.compiler import node_to_signature

        class ChatNode(Node):
            history: Annotated[str, Context(description="Chat history")]
            user_input: Annotated[str, Context(description="Current user message")]

        sig = node_to_signature(ChatNode)
        assert "history" in sig.input_fields
        assert "user_input" in sig.input_fields
        assert sig.input_fields["history"].json_schema_extra["desc"] == "Chat history"
        assert sig.input_fields["user_input"].json_schema_extra["desc"] == "Current user message"

    def test_return_type_becomes_output_field(self):
        """Case 5: Return type hint creates an OutputField.

        For Phase 1, output type is always str (union handling deferred to Phase 2).
        """
        from bae.compiler import node_to_signature

        class Response(Node):
            pass

        class Decider(Node):
            def __call__(self, lm) -> Response | None:
                return None

        sig = node_to_signature(Decider)
        assert "output" in sig.output_fields

    def test_node_with_no_annotated_fields(self):
        """Case 6: Node with only internal fields produces valid Signature with no inputs."""
        from bae.compiler import node_to_signature

        class EmptyNode(Node):
            internal: int = 0

        sig = node_to_signature(EmptyNode)
        assert len(sig.input_fields) == 0  # Valid - no inputs
        assert "output" in sig.output_fields

    def test_result_is_dspy_signature_subclass(self):
        """Case 7: Result is a valid dspy.Signature subclass."""
        from bae.compiler import node_to_signature

        class SomeNode(Node):
            data: Annotated[str, Context(description="Some data")]

        sig = node_to_signature(SomeNode)
        assert issubclass(sig, dspy.Signature)


class TestContextMarker:
    """Test the Context annotation marker."""

    def test_context_is_frozen_dataclass(self):
        """Context should be immutable (frozen dataclass)."""
        ctx = Context(description="test")
        with pytest.raises(Exception):  # FrozenInstanceError
            ctx.description = "modified"

    def test_context_holds_description(self):
        """Context stores description string."""
        ctx = Context(description="The user's query")
        assert ctx.description == "The user's query"

    def test_context_equality(self):
        """Two Context objects with same description are equal."""
        ctx1 = Context(description="test")
        ctx2 = Context(description="test")
        assert ctx1 == ctx2


class TestDepMarker:
    """Test the Dep annotation marker for __call__ parameters."""

    def test_dep_is_frozen_dataclass(self):
        """Dep should be immutable (frozen dataclass)."""
        dep = Dep(description="test")
        with pytest.raises(Exception):  # FrozenInstanceError
            dep.description = "modified"

    def test_dep_holds_description(self):
        """Dep stores description string."""
        dep = Dep(description="Database connection")
        assert dep.description == "Database connection"

    def test_dep_equality(self):
        """Two Dep objects with same description are equal."""
        dep1 = Dep(description="test")
        dep2 = Dep(description="test")
        assert dep1 == dep2


class TestDepAnnotatedCallParams:
    """Test Dep-annotated __call__ parameters becoming InputFields."""

    def test_dep_annotated_call_param_becomes_input_field(self):
        """Dep-annotated __call__ param becomes InputField."""
        from bae.compiler import node_to_signature

        class FetchData(Node):
            query: Annotated[str, Context(description="The query")]

            def __call__(
                self,
                lm,
                db: Annotated[str, Dep(description="Database connection string")],
            ) -> None:
                pass

        sig = node_to_signature(FetchData)
        assert "db" in sig.input_fields
        assert sig.input_fields["db"].json_schema_extra["desc"] == "Database connection string"

    def test_multiple_dep_params_become_input_fields(self):
        """Multiple Dep-annotated params all become InputFields."""
        from bae.compiler import node_to_signature

        class ProcessWithDeps(Node):
            def __call__(
                self,
                lm,
                cache: Annotated[str, Dep(description="Cache service")],
                logger: Annotated[str, Dep(description="Logger instance")],
            ) -> None:
                pass

        sig = node_to_signature(ProcessWithDeps)
        assert "cache" in sig.input_fields
        assert "logger" in sig.input_fields
        assert sig.input_fields["cache"].json_schema_extra["desc"] == "Cache service"
        assert sig.input_fields["logger"].json_schema_extra["desc"] == "Logger instance"

    def test_context_and_dep_both_become_input_fields(self):
        """Both Context fields and Dep params appear as InputFields."""
        from bae.compiler import node_to_signature

        class MixedNode(Node):
            request: Annotated[str, Context(description="User request")]

            def __call__(
                self,
                lm,
                api: Annotated[str, Dep(description="API endpoint")],
            ) -> None:
                pass

        sig = node_to_signature(MixedNode)
        # Context field
        assert "request" in sig.input_fields
        assert sig.input_fields["request"].json_schema_extra["desc"] == "User request"
        # Dep param
        assert "api" in sig.input_fields
        assert sig.input_fields["api"].json_schema_extra["desc"] == "API endpoint"

    def test_unannotated_call_param_excluded(self):
        """__call__ param without Dep annotation is excluded."""
        from bae.compiler import node_to_signature

        class NodeWithInternalParam(Node):
            def __call__(
                self,
                lm,
                internal_flag: bool = False,  # No Annotated wrapper
            ) -> None:
                pass

        sig = node_to_signature(NodeWithInternalParam)
        assert "internal_flag" not in sig.input_fields

    def test_self_and_lm_excluded(self):
        """self and lm parameters are always excluded."""
        from bae.compiler import node_to_signature

        class SimpleNode(Node):
            data: Annotated[str, Context(description="Data")]

            def __call__(self, lm) -> None:
                pass

        sig = node_to_signature(SimpleNode)
        assert "self" not in sig.input_fields
        assert "lm" not in sig.input_fields

    def test_node_with_only_dep_params(self):
        """Node with only Dep params (no Context fields) works."""
        from bae.compiler import node_to_signature

        class DepOnlyNode(Node):
            def __call__(
                self,
                lm,
                service: Annotated[str, Dep(description="External service")],
            ) -> None:
                pass

        sig = node_to_signature(DepOnlyNode)
        assert "service" in sig.input_fields
        assert len(sig.input_fields) == 1

    def test_node_without_custom_call(self):
        """Node using base class __call__ has no Dep params (just Context fields)."""
        from bae.compiler import node_to_signature

        class DefaultCallNode(Node):
            data: Annotated[str, Context(description="Some data")]

        sig = node_to_signature(DefaultCallNode)
        # Only the Context field, no Dep params from base __call__
        assert "data" in sig.input_fields
        assert len(sig.input_fields) == 1
