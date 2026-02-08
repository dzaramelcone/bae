"""v2 integration tests for Graph.run() field resolution.

Tests the v2 execution loop:
- Dep(callable) fields resolved before __call__
- Recall() fields resolved from trace before __call__
- Custom __call__ reads resolved fields from self
- Ellipsis body nodes route via choose_type/fill
- Error hierarchy (DepError, RecallError) on failures
- Iteration guard (max_iters)
"""

from __future__ import annotations

from typing import Annotated

import pytest

from bae.exceptions import BaeError, DepError
from bae.graph import Graph
from bae.lm import LM
from bae.markers import Dep, Recall
from bae.node import Node
from bae.result import GraphResult


# =============================================================================
# Test Infrastructure
# =============================================================================


class MockV2LM:
    """Mock LM implementing v2 API (choose_type/fill)."""

    def __init__(self, responses: dict[type, Node]):
        self.responses = responses
        self.fill_calls: list[tuple[type, dict, str]] = []
        self.choose_type_calls: list[tuple[list[type], dict]] = []

    def choose_type(self, types: list[type], context: dict) -> type:
        self.choose_type_calls.append((types, context))
        for t in types:
            if t in self.responses:
                return t
        return types[0]

    def fill(self, target: type, context: dict, instruction: str) -> Node:
        self.fill_calls.append((target, context, instruction))
        return self.responses[target]

    # Keep v1 methods as stubs to satisfy Protocol shape
    def make(self, node: Node, target: type) -> Node:
        raise NotImplementedError("v1 API")

    def decide(self, node: Node) -> Node | None:
        raise NotImplementedError("v1 API")


# =============================================================================
# Test helper types - Dep resolution
# =============================================================================


class FetchResult:
    """Result returned by fetch_data dep function."""

    def __init__(self, value: str):
        self.value = value


def fetch_data() -> FetchResult:
    """Simple dep function that returns FetchResult."""
    return FetchResult(value="fetched-data")


class Info:
    """Info type for dep/recall tests."""

    def __init__(self, content: str):
        self.content = content


def fetch_info() -> Info:
    """Dep function that returns Info."""
    return Info(content="gathered-info")


# =============================================================================
# Feature 1: Dep resolution on start node
# =============================================================================


class StartWithDep(Node):
    """Start node with a Dep field."""

    data: Annotated[FetchResult, Dep(fetch_data)]

    def __call__(self) -> None:
        ...


class TestDepResolutionOnStartNode:
    """Feature 1: Dep(callable) fields resolved before __call__."""

    def test_dep_field_resolved_before_call(self):
        """graph.run(StartWithDep) resolves dep field, trace[0] has data populated."""
        graph = Graph(start=StartWithDep)

        result = graph.run(
            StartWithDep.model_construct(),
            lm=MockV2LM(responses={}),
        )

        assert isinstance(result, GraphResult)
        assert len(result.trace) == 1
        start = result.trace[0]
        assert isinstance(start, StartWithDep)
        assert isinstance(start.data, FetchResult)
        assert start.data.value == "fetched-data"


# =============================================================================
# Feature 2: Multi-node with deps and recalls
# =============================================================================


class GatherInfo(Node):
    """Start node that gathers info via dep, passes to bridge via custom __call__."""

    info: Annotated[Info, Dep(fetch_info)]

    def __call__(self) -> InfoBridge:
        # Custom __call__ reads dep-resolved field and produces bridge node
        # with Info as a plain field (recallable)
        return InfoBridge(info=self.info)


class InfoBridge(Node):
    """Bridge node that holds Info as plain field (recallable by Analyze)."""

    info: Info

    def __call__(self) -> Analyze:
        ...


class Analyze(Node):
    """Node that recalls info from trace and produces analysis."""

    prev_info: Annotated[Info, Recall()]
    analysis: str = ""

    def __call__(self) -> None:
        ...


class TestMultiNodeWithDepsAndRecalls:
    """Feature 2: Multi-node graph with dep resolution and trace recall."""

    def test_gather_dep_then_recall(self):
        """GatherInfo dep resolved, InfoBridge holds plain field, Analyze recalls it."""
        graph = Graph(start=GatherInfo)

        # MockV2LM fills Analyze when InfoBridge (ellipsis body) routes
        analyze_node = Analyze.model_construct(
            prev_info=None,
            analysis="deep analysis",
        )
        lm = MockV2LM(responses={Analyze: analyze_node})

        result = graph.run(
            GatherInfo.model_construct(),
            lm=lm,
        )

        assert isinstance(result, GraphResult)
        assert len(result.trace) == 3

        # GatherInfo should have dep resolved
        gather = result.trace[0]
        assert isinstance(gather, GatherInfo)
        assert isinstance(gather.info, Info)
        assert gather.info.content == "gathered-info"

        # InfoBridge should have plain Info field from GatherInfo
        bridge = result.trace[1]
        assert isinstance(bridge, InfoBridge)
        assert isinstance(bridge.info, Info)
        assert bridge.info.content == "gathered-info"

        # Analyze should have recall resolved from trace (finds InfoBridge.info)
        analyze = result.trace[2]
        assert isinstance(analyze, Analyze)
        assert isinstance(analyze.prev_info, Info)
        assert analyze.prev_info.content == "gathered-info"


# =============================================================================
# Feature 3: Custom __call__ with resolved deps
# =============================================================================


class TerminalResult(Node):
    """Terminal node."""

    value: str = ""

    def __call__(self) -> None:
        ...


class CustomWithDep(Node):
    """Node with Dep field + custom __call__ that reads self.data."""

    data: Annotated[FetchResult, Dep(fetch_data)]

    def __call__(self) -> TerminalResult:
        # Custom logic reads resolved dep from self
        return TerminalResult(value=f"got-{self.data.value}")


class TestCustomCallWithResolvedDeps:
    """Feature 3: Custom __call__ can access self.dep_field after resolution."""

    def test_custom_call_reads_resolved_dep(self):
        """Node with Dep field + custom __call__ accesses self.data after resolution."""
        graph = Graph(start=CustomWithDep)

        result = graph.run(
            CustomWithDep.model_construct(),
            lm=MockV2LM(responses={}),
        )

        assert isinstance(result, GraphResult)
        assert len(result.trace) == 2

        # Custom node should have dep resolved before __call__
        custom = result.trace[0]
        assert isinstance(custom, CustomWithDep)
        assert isinstance(custom.data, FetchResult)
        assert custom.data.value == "fetched-data"

        # Terminal node should be produced by custom __call__
        terminal = result.trace[1]
        assert isinstance(terminal, TerminalResult)
        assert terminal.value == "got-fetched-data"


# =============================================================================
# Feature 4: Dep failure raises DepError
# =============================================================================


def failing_fn() -> FetchResult:
    """Dep function that always fails."""
    raise RuntimeError("database connection refused")


class NodeWithFailingDep(Node):
    """Node with a dep that will fail."""

    data: Annotated[FetchResult, Dep(failing_fn)]

    def __call__(self) -> None:
        ...


class TestDepFailureRaisesDepError:
    """Feature 4: DepError raised on dep failures with __cause__ and trace."""

    def test_dep_failure_raises_dep_error(self):
        """graph.run raises DepError when dep function fails."""
        graph = Graph(start=NodeWithFailingDep)

        with pytest.raises(DepError) as exc_info:
            graph.run(
                NodeWithFailingDep.model_construct(),
                lm=MockV2LM(responses={}),
            )

        err = exc_info.value
        assert isinstance(err.__cause__, RuntimeError)
        assert "database connection refused" in str(err.__cause__)
        assert hasattr(err, "trace")
        assert err.trace is not None


# =============================================================================
# Feature 5: Iteration guard
# =============================================================================


class LoopNode(Node):
    """Node that returns self type, creating an infinite loop."""

    counter: int = 0

    def __call__(self) -> LoopNode:
        ...


class CountdownNode(Node):
    """Node that terminates after a few steps via custom __call__."""

    steps_left: int = 3

    def __call__(self) -> CountdownNode | None:
        if self.steps_left <= 0:
            return None
        return CountdownNode(steps_left=self.steps_left - 1)


class TestIterationGuard:
    """Feature 5: max_iters limits execution to prevent infinite loops."""

    def test_max_iters_exceeded_raises_bae_error(self):
        """graph.run with max_iters=5 raises BaeError after 5 iterations."""
        graph = Graph(start=LoopNode)

        loop_node = LoopNode.model_construct(counter=0)
        lm = MockV2LM(responses={LoopNode: loop_node})

        with pytest.raises(BaeError, match="exceeded 5 iterations"):
            graph.run(loop_node, lm=lm, max_iters=5)

    def test_max_iters_zero_means_infinite(self):
        """graph.run with max_iters=0 does NOT raise (sentinel for infinite)."""
        graph = Graph(start=CountdownNode)

        result = graph.run(
            CountdownNode(steps_left=3),
            lm=MockV2LM(responses={}),
            max_iters=0,
        )

        assert isinstance(result, GraphResult)
        # Should have executed: 3, 2, 1, 0 (terminal)
        assert len(result.trace) == 4


# =============================================================================
# Feature 6: Terminal node in trace
# =============================================================================


class SimpleTerminal(Node):
    """A simple terminal node."""

    message: str = "done"

    def __call__(self) -> None:
        ...


class NodeBeforeTerminal(Node):
    """Node that transitions to terminal."""

    def __call__(self) -> SimpleTerminal:
        return SimpleTerminal(message="finished")


class TestTerminalNodeInTrace:
    """Feature 6: Terminal node is included in trace (last element)."""

    def test_terminal_node_in_trace(self):
        """Terminal node (returns None) is included in trace."""
        graph = Graph(start=SimpleTerminal)

        result = graph.run(
            SimpleTerminal(message="the end"),
            lm=MockV2LM(responses={}),
        )

        assert isinstance(result, GraphResult)
        assert len(result.trace) == 1
        assert isinstance(result.trace[-1], SimpleTerminal)
        assert result.trace[-1].message == "the end"

    def test_terminal_node_is_last_in_multi_node_trace(self):
        """In multi-node graph, terminal is last in trace."""
        graph = Graph(start=NodeBeforeTerminal)

        result = graph.run(
            NodeBeforeTerminal(),
            lm=MockV2LM(responses={}),
        )

        assert isinstance(result, GraphResult)
        assert len(result.trace) == 2
        assert isinstance(result.trace[-1], SimpleTerminal)
        assert result.trace[-1].message == "finished"
