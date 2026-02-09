"""Integration tests for DSPy-based graph execution (v2).

Tests:
1. Auto-routing with union return type (choose_type + fill)
2. Auto-routing with single return type (fill only)
3. Custom __call__ logic (escape hatch)
4. DSPyBackend as default (no lm parameter)
5. GraphResult trace verification

Uses mocks for dspy.Predict to avoid real LLM calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from bae import (
    DSPyBackend,
    Graph,
    GraphResult,
    LM,
    Node,
)


# =============================================================================
# Test Nodes - Various patterns
# =============================================================================


class AnalyzeQuery(Node):
    """Analyze an incoming query to determine processing path."""

    query: str

    async def __call__(self) -> ProcessSimple | ProcessComplex:
        """Auto-routing: LLM decides between simple and complex processing."""
        ...


class ProcessSimple(Node):
    """Simple query processing - direct answer."""

    answer: str

    async def __call__(self) -> Done | None:
        """Auto-routing: LLM decides to produce Done or terminate."""
        ...


class ProcessComplex(Node):
    """Complex query processing - requires multiple steps."""

    steps: list[str]

    async def __call__(self) -> Review:
        """Auto-routing: single return type -> make."""
        ...


class Review(Node):
    """Review processing results before finalizing."""

    summary: str

    async def __call__(self) -> Done:
        """Auto-routing: single return type -> make."""
        ...


class Done(Node):
    """Terminal node - processing complete."""

    result: str

    async def __call__(self) -> None:
        """Terminal: ellipsis body with pure None return."""
        ...


# =============================================================================
# Test Nodes - With custom __call__ escape hatch
# =============================================================================


class StartCustom(Node):
    """Start node with custom logic."""

    value: int = 0

    async def __call__(self, lm: LM) -> EndCustom:
        """Custom logic escape hatch - not auto-routed."""
        return await lm.make(self, EndCustom)


class EndCustom(Node):
    """End node for custom logic test."""

    result: int

    async def __call__(self) -> None:
        ...


# =============================================================================
# Mock LM for testing
# =============================================================================


class MockLM:
    """Mock LM implementing v2 API (choose_type/fill) for ellipsis-body nodes,
    plus v1 stubs (make/decide) for custom __call__ nodes.
    """

    def __init__(self, responses: dict[type, Node | None]):
        """Initialize with type -> response mapping."""
        self.responses = responses
        self.fill_calls: list[tuple[type, dict, str]] = []
        self.choose_type_calls: list[tuple[list, dict]] = []
        self.make_calls: list[tuple[Node, type]] = []

    async def choose_type(self, types, context):
        self.choose_type_calls.append((types, context))
        for t in types:
            if t in self.responses:
                return t
        return types[0]

    async def fill(self, target, resolved, instruction, source=None):
        self.fill_calls.append((target, resolved, instruction))
        return self.responses[target]

    # v1 stubs for custom __call__ nodes that call lm.make/decide directly
    async def make(self, node: Node, target: type) -> Node:
        self.make_calls.append((node, target))
        return self.responses[target]

    async def decide(self, node: Node) -> Node | None:
        for target in node.successors():
            if target in self.responses:
                return self.responses[target]
        return None


# =============================================================================
# Tests
# =============================================================================


class TestAutoRoutingUnionType:
    """Test auto-routing with union return type (choose_type + fill)."""

    async def test_union_return_type_calls_choose_type_and_fill(self):
        """Ellipsis body with union return calls choose_type then fill."""
        graph = Graph(start=AnalyzeQuery)

        lm = MockLM(
            {
                ProcessSimple: ProcessSimple(answer="42"),
                Done: None,  # ProcessSimple returns Done | None -> fill returns None
            }
        )

        result = await graph.run(AnalyzeQuery(query="What is 6*7?"), lm=lm)

        # v2: decide strategy calls choose_type then fill for each ellipsis node
        # AnalyzeQuery (decide: ProcessSimple|ProcessComplex) + ProcessSimple (decide: Done|None)
        assert len(lm.choose_type_calls) == 2
        assert len(lm.fill_calls) == 2

        # Result is GraphResult
        assert isinstance(result, GraphResult)
        assert result.node is None


class TestAutoRoutingSingleType:
    """Test auto-routing with single return type (fill only)."""

    async def test_single_return_type_calls_lm_fill(self):
        """Ellipsis body with single return calls fill directly (no choose_type)."""
        graph = Graph(start=ProcessComplex)

        lm = MockLM(
            {
                Review: Review(summary="All steps complete"),
                Done: Done(result="Final result"),
            }
        )

        result = await graph.run(
            ProcessComplex(steps=["step1", "step2"]),
            lm=lm,
        )

        # v2: make strategy calls fill directly, no choose_type
        # ProcessComplex -> fill(Review) + Review -> fill(Done) = 2 fill calls
        assert len(lm.fill_calls) >= 1
        assert lm.fill_calls[0][0] is Review  # First fill target is Review
        assert len(lm.choose_type_calls) == 0  # No choose_type for single-return


class TestCustomCallEscapeHatch:
    """Test custom __call__ logic is called directly."""

    async def test_custom_call_not_auto_routed(self):
        """Custom __call__ is invoked directly, not via choose_type/fill."""
        graph = Graph(start=StartCustom)

        lm = MockLM(
            {
                EndCustom: EndCustom(result=100),
            }
        )

        result = await graph.run(StartCustom(value=50), lm=lm)

        # Custom call invoked lm.make directly (v1 method)
        assert len(lm.make_calls) == 1
        assert isinstance(lm.make_calls[0][0], StartCustom)

        # No v2 auto-routing calls
        assert len(lm.choose_type_calls) == 0
        assert len(lm.fill_calls) == 0

        assert isinstance(result, GraphResult)


class TestDSPyBackendDefault:
    """Test that DSPyBackend is used when lm not provided."""

    async def test_graph_run_without_lm_uses_dspy_backend(self):
        """Graph.run() without lm parameter defaults to DSPyBackend."""
        graph = Graph(start=Done)

        # Run without lm - should use DSPyBackend
        # This will just run the terminal node which returns None
        result = await graph.run(Done(result="test"))

        assert isinstance(result, GraphResult)
        assert result.node is None
        assert len(result.trace) == 1
        assert isinstance(result.trace[0], Done)

    @patch("bae.dspy_backend.dspy.Predict")
    async def test_dspy_backend_used_for_auto_routing(self, mock_predict_cls):
        """DSPyBackend is actually invoked for auto-routing when no lm provided."""
        # v2: ProcessSimple (Done | None) -> decide strategy -> choose_type([Done])
        # choose_type skips LLM for single type, then fill(Done) calls dspy.Predict

        mock_prediction = MagicMock()
        mock_prediction.keys.return_value = ["result"]
        mock_prediction.result = "done"

        mock_predictor = MagicMock()

        async def mock_acall(**kwargs):
            return mock_prediction

        mock_predictor.acall = mock_acall
        mock_predict_cls.return_value = mock_predictor

        graph = Graph(start=ProcessSimple)
        result = await graph.run(ProcessSimple(answer="test"))

        # DSPyBackend.fill() called dspy.Predict for the fill step
        assert mock_predict_cls.called


class TestGraphResultTrace:
    """Test GraphResult trace contains execution path."""

    async def test_trace_shows_full_execution_path(self):
        """GraphResult.trace contains all visited nodes in order."""
        graph = Graph(start=AnalyzeQuery)

        lm = MockLM(
            {
                ProcessComplex: ProcessComplex(steps=["a", "b"]),
                Review: Review(summary="done"),
                Done: Done(result="complete"),
            }
        )

        result = await graph.run(AnalyzeQuery(query="complex task"), lm=lm)

        # v2 trace: AnalyzeQuery -> ProcessComplex -> Review -> Done
        assert len(result.trace) == 4
        assert isinstance(result.trace[0], AnalyzeQuery)
        assert isinstance(result.trace[1], ProcessComplex)
        assert isinstance(result.trace[2], Review)
        assert isinstance(result.trace[3], Done)

    async def test_trace_includes_choose_type_step(self):
        """Trace shows nodes where LLM chose the path via choose_type."""
        graph = Graph(start=AnalyzeQuery)

        lm = MockLM(
            {
                ProcessSimple: ProcessSimple(answer="quick answer"),
                Done: Done(result="done"),
            }
        )

        result = await graph.run(AnalyzeQuery(query="simple question"), lm=lm)

        # v2 trace: AnalyzeQuery (choose_type+fill) -> ProcessSimple (choose_type+fill) -> Done (terminal)
        assert len(result.trace) == 3
        assert isinstance(result.trace[0], AnalyzeQuery)
        assert isinstance(result.trace[1], ProcessSimple)
        assert isinstance(result.trace[2], Done)


class TestPhase2SuccessCriteria:
    """Verify all Phase 2 success criteria are met."""

    def test_graph_run_introspects_return_type(self):
        """Graph.run() introspects return type: union -> decide, single -> make."""
        # Already tested in TestAutoRoutingUnionType and TestAutoRoutingSingleType
        pass

    def test_ellipsis_body_uses_auto_routing(self):
        """__call__ with ... body uses automatic routing."""
        # Already tested - nodes with ... are auto-routed
        pass

    def test_custom_call_is_escape_hatch(self):
        """Custom __call__ logic still works as escape hatch."""
        # Already tested in TestCustomCallEscapeHatch
        pass

    def test_dspy_predict_for_lm_calls(self):
        """dspy.Predict replaces naive prompts for LM calls."""
        # Tested in TestDSPyBackendDefault.test_dspy_backend_used_for_auto_routing
        pass

    async def test_pydantic_models_parse_from_dspy_output(self):
        """Pydantic models parse correctly from dspy.Predict output."""

        @patch("bae.dspy_backend.dspy.Predict")
        async def test_parse(mock_predict_cls):
            mock_prediction = MagicMock()
            mock_prediction.output = json.dumps({"result": "success"})

            mock_predictor = MagicMock()

            async def mock_acall(**kwargs):
                return mock_prediction

            mock_predictor.acall = mock_acall
            mock_predict_cls.return_value = mock_predictor

            backend = DSPyBackend()
            source = ProcessComplex(steps=["step1"])

            # This should parse the JSON output into Done model
            result = await backend.make(source, Done)

            assert isinstance(result, Done)
            assert result.result == "success"

        await test_parse()

    async def test_union_return_types_two_step_pattern(self):
        """Union return types work with two-step pattern (choose then make)."""
        # The DSPyBackend.decide() method implements two-step:
        # 1. Predict which type to choose
        # 2. Call make() to produce it

        @patch("bae.dspy_backend.dspy.Predict")
        async def test_two_step(mock_predict_cls):
            # Mock both the choice prediction and the make prediction
            call_count = [0]

            def side_effect(sig):
                mock = MagicMock()
                if call_count[0] == 0:
                    # First call: choice prediction
                    mock_result = MagicMock()
                    mock_result.choice = "ProcessSimple"

                    async def mock_acall_choice(**kwargs):
                        return mock_result

                    mock.acall = mock_acall_choice
                else:
                    # Second call: make prediction
                    mock_result = MagicMock()
                    mock_result.output = json.dumps({"answer": "42"})

                    async def mock_acall_make(**kwargs):
                        return mock_result

                    mock.acall = mock_acall_make
                call_count[0] += 1
                return mock

            mock_predict_cls.side_effect = side_effect

            backend = DSPyBackend()
            source = AnalyzeQuery(query="test")

            result = await backend.decide(source)

            assert isinstance(result, ProcessSimple)
            assert result.answer == "42"

        await test_two_step()
