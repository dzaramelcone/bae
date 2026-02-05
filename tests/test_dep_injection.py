"""TDD tests for dependency injection via incant.

Tests:
1. External deps from run() kwargs are injectable via Dep marker
2. Bind fields captured after node execution
3. Dep params injected by type matching via incant
4. Deps accumulate through the run
5. Missing deps raise appropriate error
"""

from typing import Annotated

import pytest

from bae.exceptions import BaeError
from bae.graph import Graph
from bae.lm import LM
from bae.markers import Bind, Context, Dep
from bae.node import Node
from bae.result import GraphResult


# =============================================================================
# Test Infrastructure
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


# =============================================================================
# Test Types - External Dependencies
# =============================================================================


class DatabaseConn:
    """External database connection dependency."""

    def __init__(self, name: str):
        self.name = name


class CacheClient:
    """External cache client dependency."""

    def __init__(self, host: str):
        self.host = host


# =============================================================================
# Feature 1: External Deps via run() kwargs
# =============================================================================


class TerminalNode(Node):
    """Terminal node for ending graph execution."""

    result: str = "done"

    def __call__(self, lm: LM) -> None:
        ...


class NodeNeedingDb(Node):
    """Node that needs a database connection injected."""

    query: Annotated[str, Context(description="Query to run")]

    def __call__(
        self, lm: LM, db: Annotated[DatabaseConn, Dep(description="Database connection")]
    ) -> TerminalNode:
        # Custom logic to verify injection works
        return TerminalNode(result=f"queried {db.name}")


class NodeNeedingMultipleDeps(Node):
    """Node that needs multiple external dependencies."""

    data: Annotated[str, Context(description="Data to process")]

    def __call__(
        self,
        lm: LM,
        db: Annotated[DatabaseConn, Dep(description="Database")],
        cache: Annotated[CacheClient, Dep(description="Cache")],
    ) -> TerminalNode:
        return TerminalNode(result=f"db={db.name}, cache={cache.host}")


class TestExternalDepsFromRunKwargs:
    """Feature 1: External deps from run() kwargs are injectable."""

    def test_single_external_dep_injected(self):
        """run(node, db=conn) -> Dep[DatabaseConn] receives conn."""
        graph = Graph(start=NodeNeedingDb)
        lm = MockLM(sequence=[None])  # NodeNeedingDb returns TerminalNode directly

        db = DatabaseConn(name="testdb")
        result = graph.run(NodeNeedingDb(query="SELECT *"), lm=lm, db=db)

        assert isinstance(result, GraphResult)
        # The terminal node should have the result from NodeNeedingDb
        assert len(result.trace) >= 1

    def test_multiple_external_deps_injected(self):
        """run(node, db=conn, cache=redis) -> multiple deps available."""
        graph = Graph(start=NodeNeedingMultipleDeps)
        lm = MockLM(sequence=[None])

        db = DatabaseConn(name="proddb")
        cache = CacheClient(host="localhost")
        result = graph.run(
            NodeNeedingMultipleDeps(data="test"), lm=lm, db=db, cache=cache
        )

        assert isinstance(result, GraphResult)
        assert len(result.trace) >= 1

    def test_missing_external_dep_raises_error(self):
        """run(node) with node needing Dep[X] raises BaeError."""
        graph = Graph(start=NodeNeedingDb)
        lm = MockLM(sequence=[])

        # No db provided - should raise
        with pytest.raises(BaeError, match="Missing dependency.*DatabaseConn"):
            graph.run(NodeNeedingDb(query="SELECT *"), lm=lm)


# =============================================================================
# Feature 2: Bind Field Capture
# =============================================================================


class ConnectionInfo:
    """Type that will be bound and consumed downstream."""

    def __init__(self, url: str):
        self.url = url


class NodeThatBinds(Node):
    """Node that binds a value for downstream nodes."""

    input_data: Annotated[str, Context(description="Input")]
    # This field will be captured after execution
    conn: Annotated[ConnectionInfo, Bind()]

    def __call__(self, lm: LM) -> NodeThatConsumes:
        # Set the Bind field during execution
        self.conn = ConnectionInfo(url=f"conn-from-{self.input_data}")
        return NodeThatConsumes()


class NodeThatConsumes(Node):
    """Node that consumes a bound value via Dep."""

    consumed: str = ""

    def __call__(
        self, lm: LM, conn: Annotated[ConnectionInfo, Dep(description="Connection")]
    ) -> TerminalNode:
        # Use the injected connection
        self.consumed = conn.url
        return TerminalNode(result=f"used {conn.url}")


class TestBindFieldCapture:
    """Feature 2: Bind fields captured after node execution."""

    def test_bind_field_captured_after_execution(self):
        """Bind-annotated field value captured and available downstream."""
        graph = Graph(start=NodeThatBinds)
        lm = MockLM(sequence=[TerminalNode(), None])

        result = graph.run(NodeThatBinds(input_data="test"), lm=lm)

        assert isinstance(result, GraphResult)
        # Should have executed: NodeThatBinds -> NodeThatConsumes -> TerminalNode
        assert len(result.trace) >= 2

    def test_bind_value_passed_to_downstream_dep(self):
        """Downstream node receives the bound value via Dep injection."""
        graph = Graph(start=NodeThatBinds)

        # NodeThatBinds returns NodeThatConsumes directly (custom logic)
        # NodeThatConsumes needs ConnectionInfo injected from bind
        # We need to verify the injection happened

        # Use a capturing terminal node
        class CapturingTerminal(Node):
            captured_url: str = ""

            def __call__(self, lm: LM) -> None:
                ...

        class BindingNode(Node):
            conn: Annotated[ConnectionInfo, Bind()]

            def __call__(self, lm: LM) -> ConsumingNode:
                self.conn = ConnectionInfo(url="bound-value")
                return ConsumingNode()

        class ConsumingNode(Node):
            received: str = ""

            def __call__(
                self,
                lm: LM,
                conn: Annotated[ConnectionInfo, Dep(description="Connection")],
            ) -> CapturingTerminal:
                self.received = conn.url
                return CapturingTerminal(captured_url=conn.url)

        graph = Graph(start=BindingNode)
        lm = MockLM(sequence=[CapturingTerminal(), None])

        result = graph.run(BindingNode(), lm=lm)

        # The ConsumingNode should have received the bound value
        assert len(result.trace) >= 2
        consuming_node = result.trace[1]
        assert isinstance(consuming_node, ConsumingNode)
        assert consuming_node.received == "bound-value"


# =============================================================================
# Feature 3: Dep Param Injection via Incant
# =============================================================================


class TestDepInjectionViaIncant:
    """Feature 3: Dep params injected by incant type matching."""

    def test_dep_param_injected_from_registry(self):
        """__call__(self, lm, db: Dep[Conn]) -> db injected from registry."""
        graph = Graph(start=NodeNeedingDb)
        lm = MockLM(sequence=[None])

        db = DatabaseConn(name="injected-db")
        result = graph.run(NodeNeedingDb(query="test"), lm=lm, db=db)

        # Node executed successfully with injected db
        assert isinstance(result, GraphResult)

    def test_no_dep_params_no_injection_needed(self):
        """__call__(self, lm) -> no injection needed, works normally."""

        class SimpleNode(Node):
            data: str = ""

            def __call__(self, lm: LM) -> TerminalNode:
                return TerminalNode(result=f"simple-{self.data}")

        graph = Graph(start=SimpleNode)
        lm = MockLM(sequence=[None])

        result = graph.run(SimpleNode(data="test"), lm=lm)

        assert isinstance(result, GraphResult)
        assert len(result.trace) >= 1


# =============================================================================
# Feature 4: Deps Accumulate Through Run
# =============================================================================


class SessionId:
    """Session identifier type."""

    def __init__(self, value: str):
        self.value = value


class RequestData:
    """Request data type."""

    def __init__(self, body: str):
        self.body = body


class NodeA(Node):
    """First node that binds SessionId."""

    session: Annotated[SessionId, Bind()]

    def __call__(self, lm: LM) -> NodeB:
        self.session = SessionId(value="sess-123")
        return NodeB()


class NodeB(Node):
    """Second node that binds RequestData and consumes SessionId."""

    request: Annotated[RequestData, Bind()]
    received_session: str = ""

    def __call__(
        self, lm: LM, session: Annotated[SessionId, Dep(description="Session")]
    ) -> NodeC:
        self.received_session = session.value
        self.request = RequestData(body=f"req-for-{session.value}")
        return NodeC()


class NodeC(Node):
    """Third node that consumes both SessionId and RequestData."""

    final_result: str = ""

    def __call__(
        self,
        lm: LM,
        session: Annotated[SessionId, Dep(description="Session")],
        request: Annotated[RequestData, Dep(description="Request")],
    ) -> TerminalNode:
        self.final_result = f"session={session.value}, request={request.body}"
        return TerminalNode(result=self.final_result)


class TestDepsAccumulateThroughRun:
    """Feature 4: Deps accumulate through the run."""

    def test_deps_accumulate_across_nodes(self):
        """Values bound by earlier nodes available to later nodes."""
        graph = Graph(start=NodeA)
        lm = MockLM(sequence=[TerminalNode(), None])

        result = graph.run(NodeA(), lm=lm)

        # Verify chain executed
        assert isinstance(result, GraphResult)
        assert len(result.trace) >= 3

        # Verify NodeB received SessionId from NodeA
        node_b = result.trace[1]
        assert isinstance(node_b, NodeB)
        assert node_b.received_session == "sess-123"

        # Verify NodeC received both SessionId and RequestData
        node_c = result.trace[2]
        assert isinstance(node_c, NodeC)
        assert "session=sess-123" in node_c.final_result
        assert "request=req-for-sess-123" in node_c.final_result

    def test_external_and_bound_deps_coexist(self):
        """External deps from run() kwargs and bound deps both available."""

        class ExternalConfig:
            def __init__(self, env: str):
                self.env = env

        class BoundToken:
            def __init__(self, value: str):
                self.value = value

        class StartNode(Node):
            token: Annotated[BoundToken, Bind()]

            def __call__(
                self,
                lm: LM,
                config: Annotated[ExternalConfig, Dep(description="Config")],
            ) -> EndNode:
                self.token = BoundToken(value=f"token-{config.env}")
                return EndNode()

        class EndNode(Node):
            result: str = ""

            def __call__(
                self,
                lm: LM,
                config: Annotated[ExternalConfig, Dep(description="Config")],
                token: Annotated[BoundToken, Dep(description="Token")],
            ) -> TerminalNode:
                self.result = f"env={config.env}, token={token.value}"
                return TerminalNode()

        graph = Graph(start=StartNode)
        lm = MockLM(sequence=[TerminalNode(), None])

        config = ExternalConfig(env="production")
        result = graph.run(StartNode(), lm=lm, config=config)

        assert isinstance(result, GraphResult)
        end_node = result.trace[1]
        assert isinstance(end_node, EndNode)
        assert "env=production" in end_node.result
        assert "token=token-production" in end_node.result


# =============================================================================
# Feature 5: Missing Deps Raise Appropriate Error
# =============================================================================


class TestMissingDepsRaiseError:
    """Feature 5: Missing deps raise BaeError."""

    def test_missing_external_dep_raises_bae_error(self):
        """Missing external dep raises BaeError with clear message."""
        graph = Graph(start=NodeNeedingDb)
        lm = MockLM(sequence=[])

        with pytest.raises(BaeError) as exc_info:
            graph.run(NodeNeedingDb(query="test"), lm=lm)

        assert "DatabaseConn" in str(exc_info.value)
        assert "Missing dependency" in str(exc_info.value)

    def test_missing_bound_dep_raises_bae_error(self):
        """Missing bound dep (node didn't set Bind field) raises BaeError."""

        class NodeThatForgotsToBind(Node):
            conn: Annotated[ConnectionInfo, Bind()]

            def __call__(self, lm: LM) -> NodeThatNeedsConn:
                # Oops, forgot to set self.conn!
                return NodeThatNeedsConn()

        class NodeThatNeedsConn(Node):
            def __call__(
                self,
                lm: LM,
                conn: Annotated[ConnectionInfo, Dep(description="Connection")],
            ) -> TerminalNode:
                return TerminalNode()

        graph = Graph(start=NodeThatForgotsToBind)
        lm = MockLM(sequence=[TerminalNode(), None])

        with pytest.raises(BaeError) as exc_info:
            graph.run(NodeThatForgotsToBind(), lm=lm)

        assert "ConnectionInfo" in str(exc_info.value)
