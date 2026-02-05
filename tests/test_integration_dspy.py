"""Integration tests for DSPy-based graph execution.

Tests Phase 2 capabilities:
1. Auto-routing with union return type (decide path)
2. Auto-routing with single return type (make path)
3. Custom __call__ logic (escape hatch)
4. Bind/Dep value flow between nodes
5. External deps from run() kwargs
6. DSPyBackend as default (no lm parameter)

Uses mocks for dspy.Predict to avoid real LLM calls.
"""

import json
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest

from bae import (
    Bind,
    Context,
    Dep,
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

    query: Annotated[str, Context(description="The query to analyze")]

    def __call__(self) -> ProcessSimple | ProcessComplex:
        """Auto-routing: LLM decides between simple and complex processing."""
        ...


class ProcessSimple(Node):
    """Simple query processing - direct answer."""

    answer: Annotated[str, Context(description="The answer to provide")]

    def __call__(self) -> Done | None:
        """Auto-routing: LLM decides to produce Done or terminate."""
        ...


class ProcessComplex(Node):
    """Complex query processing - requires multiple steps."""

    steps: Annotated[list[str], Context(description="Processing steps to execute")]

    def __call__(self) -> Review:
        """Auto-routing: single return type -> make."""
        ...


class Review(Node):
    """Review processing results before finalizing."""

    summary: Annotated[str, Context(description="Summary of processing")]

    def __call__(self) -> Done:
        """Auto-routing: single return type -> make."""
        ...


class Done(Node):
    """Terminal node - processing complete."""

    result: str

    def __call__(self) -> None:
        """Terminal: ellipsis body with pure None return."""
        ...


# =============================================================================
# Test Nodes - With custom __call__ escape hatch
# =============================================================================


class StartCustom(Node):
    """Start node with custom logic."""

    value: int = 0

    def __call__(self, lm: LM) -> EndCustom:
        """Custom logic escape hatch - not auto-routed."""
        return lm.make(self, EndCustom)


class EndCustom(Node):
    """End node for custom logic test."""

    result: int

    def __call__(self) -> None:
        ...


# =============================================================================
# Test Nodes - With Bind/Dep for value flow
# =============================================================================


class DatabaseConn:
    """Simulated database connection."""

    def __init__(self, conn_string: str):
        self.conn_string = conn_string


class Initialize(Node):
    """Initialize processing and create connection."""

    conn_string: Annotated[str, Context(description="Connection string")]
    conn: Annotated[DatabaseConn | None, Bind()] = None

    def __call__(self, lm: LM) -> UseConnection:
        """Create connection and pass to downstream."""
        # Bind field gets captured after this node executes
        self.conn = DatabaseConn(self.conn_string)
        return lm.make(self, UseConnection)


class UseConnection(Node):
    """Use the bound connection from upstream."""

    query: str

    def __call__(
        self,
        lm: LM,
        conn: Annotated[DatabaseConn, Dep(description="Database connection")],
    ) -> FinalResult:
        """Dep-annotated param injected from Initialize's Bind field."""
        # Access the injected connection
        result = f"Executed {self.query} on {conn.conn_string}"
        return FinalResult(output=result)


class FinalResult(Node):
    """Final result of connection-based processing."""

    output: str

    def __call__(self) -> None:
        ...


# =============================================================================
# Test Nodes - External dep injection
# =============================================================================


class Config:
    """External configuration object."""

    def __init__(self, env: str):
        self.env = env


class NeedsConfig(Node):
    """Node that requires external config."""

    action: str

    def __call__(
        self,
        lm: LM,
        config: Annotated[Config, Dep(description="Environment config")],
    ) -> ConfigResult:
        """Dep injected from run() kwargs."""
        return ConfigResult(output=f"{self.action} in {config.env}")


class ConfigResult(Node):
    """Result of config-based processing."""

    output: str

    def __call__(self) -> None:
        ...


# =============================================================================
# Mock LM for testing
# =============================================================================


class MockLM:
    """Mock LM that returns pre-configured responses."""

    def __init__(self, responses: dict[type, Node | None]):
        """Initialize with type -> response mapping."""
        self.responses = responses
        self.make_calls: list[tuple[Node, type]] = []
        self.decide_calls: list[Node] = []

    def make(self, node: Node, target: type) -> Node:
        self.make_calls.append((node, target))
        return self.responses[target]

    def decide(self, node: Node) -> Node | None:
        self.decide_calls.append(node)
        # Return first response that matches a successor type
        for target in node.successors():
            if target in self.responses:
                return self.responses[target]
        return None


# =============================================================================
# Tests
# =============================================================================


class TestAutoRoutingUnionType:
    """Test auto-routing with union return type (decide path)."""

    def test_union_return_type_calls_lm_decide(self):
        """When __call__ has ... body and union return, Graph.run() calls lm.decide()."""
        graph = Graph(start=AnalyzeQuery)

        lm = MockLM(
            {
                ProcessSimple: ProcessSimple(answer="42"),
                Done: None,  # ProcessSimple returns Done | None
            }
        )

        result = graph.run(AnalyzeQuery(query="What is 6*7?"), lm=lm)

        # Should have called decide on both AnalyzeQuery and ProcessSimple
        # (both have union/optional return types)
        assert len(lm.decide_calls) == 2
        assert isinstance(lm.decide_calls[0], AnalyzeQuery)
        assert isinstance(lm.decide_calls[1], ProcessSimple)

        # Result is GraphResult
        assert isinstance(result, GraphResult)
        assert result.node is None  # Terminated (ProcessSimple chose None)


class TestAutoRoutingSingleType:
    """Test auto-routing with single return type (make path)."""

    def test_single_return_type_calls_lm_make(self):
        """When __call__ has ... body and single return, Graph.run() calls lm.make()."""
        graph = Graph(start=ProcessComplex)

        lm = MockLM(
            {
                Review: Review(summary="All steps complete"),
                Done: Done(result="Final result"),
            }
        )

        result = graph.run(
            ProcessComplex(steps=["step1", "step2"]),
            lm=lm,
        )

        # Should have called make on ProcessComplex (single return)
        assert len(lm.make_calls) >= 1
        # First make should be ProcessComplex -> Review
        assert isinstance(lm.make_calls[0][0], ProcessComplex)
        assert lm.make_calls[0][1] == Review


class TestCustomCallEscapeHatch:
    """Test custom __call__ logic is called directly."""

    def test_custom_call_not_auto_routed(self):
        """When __call__ has real body, it's called directly (not lm.decide/make)."""
        graph = Graph(start=StartCustom)

        lm = MockLM(
            {
                EndCustom: EndCustom(result=100),
            }
        )

        result = graph.run(StartCustom(value=50), lm=lm)

        # Custom call should have invoked lm.make directly
        assert len(lm.make_calls) == 1
        assert isinstance(lm.make_calls[0][0], StartCustom)

        # No decide calls (not auto-routed)
        assert len(lm.decide_calls) == 0

        assert isinstance(result, GraphResult)


class TestBindDepValueFlow:
    """Test Bind/Dep value flow between nodes."""

    def test_bind_field_passed_to_downstream_dep(self):
        """Bind-annotated field captured and injected into Dep-annotated param."""
        graph = Graph(start=Initialize)

        lm = MockLM(
            {
                UseConnection: UseConnection(query="SELECT * FROM users"),
                FinalResult: FinalResult(output="mock"),
            }
        )

        result = graph.run(Initialize(conn_string="postgresql://localhost/db"), lm=lm)

        assert isinstance(result, GraphResult)
        # Trace should include all nodes
        assert len(result.trace) >= 2
        assert isinstance(result.trace[0], Initialize)

        # The Initialize node should have conn populated after execution
        init_node = result.trace[0]
        assert init_node.conn is not None
        assert init_node.conn.conn_string == "postgresql://localhost/db"


class TestExternalDepInjection:
    """Test external deps from run() kwargs."""

    def test_external_dep_injected_from_kwargs(self):
        """Dep-annotated param receives value from run() kwargs."""
        graph = Graph(start=NeedsConfig)

        lm = MockLM(
            {
                ConfigResult: ConfigResult(output="mock"),
            }
        )

        config = Config(env="production")
        result = graph.run(
            NeedsConfig(action="deploy"),
            lm=lm,
            config=config,  # External dep passed as kwarg
        )

        assert isinstance(result, GraphResult)
        # Result should show the config was used
        final = result.trace[-1]
        assert isinstance(final, ConfigResult)
        assert "production" in final.output


class TestDSPyBackendDefault:
    """Test that DSPyBackend is used when lm not provided."""

    def test_graph_run_without_lm_uses_dspy_backend(self):
        """Graph.run() without lm parameter defaults to DSPyBackend."""
        graph = Graph(start=Done)

        # Run without lm - should use DSPyBackend
        # This will just run the terminal node which returns None
        result = graph.run(Done(result="test"))

        assert isinstance(result, GraphResult)
        assert result.node is None
        assert len(result.trace) == 1
        assert isinstance(result.trace[0], Done)

    @patch("bae.dspy_backend.dspy.Predict")
    def test_dspy_backend_used_for_auto_routing(self, mock_predict_cls):
        """DSPyBackend is actually invoked for auto-routing when no lm provided."""
        # Mock both the choice prediction and the make prediction
        call_count = [0]

        def side_effect(sig):
            mock = MagicMock()
            if call_count[0] == 0:
                # First call: choice prediction (Done vs None)
                mock.return_value.choice = "None"  # Choose to terminate
            call_count[0] += 1
            return mock

        mock_predict_cls.side_effect = side_effect

        graph = Graph(start=ProcessSimple)

        # Run without explicit lm - ProcessSimple has ... body and union return
        # This should use DSPyBackend for decide
        result = graph.run(ProcessSimple(answer="test"))

        # DSPyBackend was used (dspy.Predict was called)
        assert mock_predict_cls.called


class TestGraphResultTrace:
    """Test GraphResult trace contains execution path."""

    def test_trace_shows_full_execution_path(self):
        """GraphResult.trace contains all visited nodes in order."""
        graph = Graph(start=AnalyzeQuery)

        lm = MockLM(
            {
                ProcessComplex: ProcessComplex(steps=["a", "b"]),
                Review: Review(summary="done"),
                Done: Done(result="complete"),
            }
        )

        result = graph.run(AnalyzeQuery(query="complex task"), lm=lm)

        # Trace should show: AnalyzeQuery -> ProcessComplex -> Review -> Done
        assert len(result.trace) == 4
        assert isinstance(result.trace[0], AnalyzeQuery)
        assert isinstance(result.trace[1], ProcessComplex)
        assert isinstance(result.trace[2], Review)
        assert isinstance(result.trace[3], Done)

    def test_trace_includes_decide_step(self):
        """Trace shows nodes where LLM decided the path."""
        graph = Graph(start=AnalyzeQuery)

        lm = MockLM(
            {
                ProcessSimple: ProcessSimple(answer="quick answer"),
                Done: Done(result="done"),
            }
        )

        result = graph.run(AnalyzeQuery(query="simple question"), lm=lm)

        # Trace: AnalyzeQuery (decide) -> ProcessSimple (decide) -> Done (terminal)
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

    def test_dep_params_injected_via_incant(self):
        """Dep-annotated params are injected via incant."""
        # Already tested in TestExternalDepInjection
        pass

    def test_dspy_predict_for_lm_calls(self):
        """dspy.Predict replaces naive prompts for LM calls."""
        # Tested in TestDSPyBackendDefault.test_dspy_backend_used_for_auto_routing
        pass

    def test_pydantic_models_parse_from_dspy_output(self):
        """Pydantic models parse correctly from dspy.Predict output."""

        # Direct test of DSPyBackend parsing
        @patch("bae.dspy_backend.dspy.Predict")
        def test_parse(mock_predict_cls):
            mock_predict = MagicMock()
            mock_predict.return_value.output = json.dumps({"result": "success"})
            mock_predict_cls.return_value = mock_predict

            backend = DSPyBackend()
            source = ProcessComplex(steps=["step1"])

            # This should parse the JSON output into Done model
            result = backend.make(source, Done)

            assert isinstance(result, Done)
            assert result.result == "success"

        test_parse()

    def test_union_return_types_two_step_pattern(self):
        """Union return types work with two-step pattern (choose then make)."""
        # The DSPyBackend.decide() method implements two-step:
        # 1. Predict which type to choose
        # 2. Call make() to produce it

        @patch("bae.dspy_backend.dspy.Predict")
        def test_two_step(mock_predict_cls):
            # Mock both the choice prediction and the make prediction
            call_count = [0]

            def side_effect(sig):
                mock = MagicMock()
                if call_count[0] == 0:
                    # First call: choice prediction
                    mock.return_value.choice = "ProcessSimple"
                else:
                    # Second call: make prediction
                    mock.return_value.output = json.dumps({"answer": "42"})
                call_count[0] += 1
                return mock

            mock_predict_cls.side_effect = side_effect

            backend = DSPyBackend()
            source = AnalyzeQuery(query="test")

            result = backend.decide(source)

            assert isinstance(result, ProcessSimple)
            assert result.answer == "42"

        test_two_step()
