"""TDD tests for v2 node_to_signature with classify_fields integration.

Tests the redesigned node_to_signature() that uses classify_fields() from
bae.resolver to determine InputField vs OutputField mapping, with is_start
parameter for start node semantics.
"""

from typing import Annotated

import dspy

from bae.markers import Dep, Recall
from bae.node import Node


def _get_user_db() -> str:
    return "user_db_connection"


def _get_config() -> str:
    return "config_value"


class TestDepFieldBecomesInputField:
    """Dep-annotated fields become InputFields in the DSPy Signature."""

    def test_dep_field_becomes_input_field(self):
        from bae.compiler import node_to_signature

        class FetchData(Node):
            source: Annotated[str, Dep(_get_user_db)]

        sig = node_to_signature(FetchData)
        assert "source" in sig.input_fields
        assert "source" not in sig.output_fields


class TestRecallFieldBecomesInputField:
    """Recall-annotated fields become InputFields in the DSPy Signature."""

    def test_recall_field_becomes_input_field(self):
        from bae.compiler import node_to_signature

        class ReviewCode(Node):
            prev_analysis: Annotated[str, Recall()]

        sig = node_to_signature(ReviewCode)
        assert "prev_analysis" in sig.input_fields
        assert "prev_analysis" not in sig.output_fields


class TestPlainFieldNonStart:
    """Plain fields on non-start nodes become OutputFields (LLM fills these)."""

    def test_plain_field_non_start_becomes_output_field(self):
        from bae.compiler import node_to_signature

        class GenerateCode(Node):
            code: str

        sig = node_to_signature(GenerateCode)
        assert "code" in sig.output_fields
        assert "code" not in sig.input_fields


class TestPlainFieldStart:
    """Plain fields on start nodes become InputFields (caller-provided)."""

    def test_plain_field_start_becomes_input_field(self):
        from bae.compiler import node_to_signature

        class AnalyzeRequest(Node):
            request: str

        sig = node_to_signature(AnalyzeRequest, is_start=True)
        assert "request" in sig.input_fields
        assert "request" not in sig.output_fields


class TestMixedFields:
    """Nodes with mixed field types get each classified correctly."""

    def test_mixed_fields_classified_correctly(self):
        from bae.compiler import node_to_signature

        class ComplexNode(Node):
            db_conn: Annotated[str, Dep(_get_user_db)]
            prev_result: Annotated[str, Recall()]
            analysis: str
            recommendation: str

        sig = node_to_signature(ComplexNode)
        # Dep -> InputField
        assert "db_conn" in sig.input_fields
        # Recall -> InputField
        assert "prev_result" in sig.input_fields
        # Plain on non-start -> OutputField
        assert "analysis" in sig.output_fields
        assert "recommendation" in sig.output_fields

    def test_mixed_fields_start_node(self):
        from bae.compiler import node_to_signature

        class StartNode(Node):
            db_conn: Annotated[str, Dep(_get_config)]
            user_query: str

        sig = node_to_signature(StartNode, is_start=True)
        # Dep -> InputField always
        assert "db_conn" in sig.input_fields
        # Plain on start -> InputField
        assert "user_query" in sig.input_fields
        # No output fields
        assert len(sig.output_fields) == 0


class TestInstructionFromClassName:
    """Class name (+ optional docstring) is the Signature instruction."""

    def test_class_name_becomes_instruction(self):
        from bae.compiler import node_to_signature

        class AnalyzeUserIntent(Node):
            query: str

        sig = node_to_signature(AnalyzeUserIntent)
        assert sig.instructions == "AnalyzeUserIntent"

    def test_docstring_appended_to_instruction(self):
        from bae.compiler import node_to_signature

        class AnalyzeUserIntent(Node):
            """Determine what the user wants from their query."""

            query: str

        sig = node_to_signature(AnalyzeUserIntent)
        assert sig.instructions == "AnalyzeUserIntent: Determine what the user wants from their query."

    def test_no_docstring_just_class_name(self):
        from bae.compiler import node_to_signature

        class SimpleNode(Node):
            data: str

        sig = node_to_signature(SimpleNode)
        assert sig.instructions == "SimpleNode"


class TestOnlyDepRecallFieldsNonStart:
    """Node with only Dep/Recall fields (non-start) has no OutputFields."""

    def test_only_dep_recall_no_output_fields(self):
        from bae.compiler import node_to_signature

        class ContextOnly(Node):
            source: Annotated[str, Dep(_get_user_db)]
            history: Annotated[str, Recall()]

        sig = node_to_signature(ContextOnly)
        assert len(sig.output_fields) == 0
        assert "source" in sig.input_fields
        assert "history" in sig.input_fields


class TestStartNodeOnlyPlainFields:
    """Start node with only plain fields: all InputFields, no OutputFields."""

    def test_start_all_plain_all_input(self):
        from bae.compiler import node_to_signature

        class EntryPoint(Node):
            query: str
            context: str

        sig = node_to_signature(EntryPoint, is_start=True)
        assert "query" in sig.input_fields
        assert "context" in sig.input_fields
        assert len(sig.output_fields) == 0


class TestResultIsDspySignature:
    """Result is a valid dspy.Signature subclass."""

    def test_result_is_signature_subclass(self):
        from bae.compiler import node_to_signature

        class SomeNode(Node):
            data: str

        sig = node_to_signature(SomeNode)
        assert issubclass(sig, dspy.Signature)


class TestBackwardCompat:
    """Calling without is_start defaults to non-start behavior."""

    def test_default_is_non_start(self):
        from bae.compiler import node_to_signature

        class WorkerNode(Node):
            result: str

        # No is_start arg -> defaults to False -> plain fields are OutputFields
        sig = node_to_signature(WorkerNode)
        assert "result" in sig.output_fields
        assert "result" not in sig.input_fields


class TestExistingTestsStillPass:
    """Verify the old Context-marker path still works.

    The old _extract_context_fields function is kept for v1 callers.
    The old tests in test_compiler.py exercise that path.
    This test just verifies the old function is still importable and works.
    """

    def test_extract_context_fields_still_exists(self):
        from bae.compiler import _extract_context_fields
        from bae.markers import Context

        class OldStyleNode(Node):
            data: Annotated[str, Context(description="Some data")]

        fields = _extract_context_fields(OldStyleNode)
        assert "data" in fields
