"""Graph discovery and execution.

The Graph class discovers topology from Node type hints and handles execution.
"""

import logging
import types
from collections import deque
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from bae.exceptions import BaeError, DepError, RecallError
from bae.lm import LM
from bae.node import Node, _has_ellipsis_body, _wants_lm
from bae.resolver import resolve_fields
from bae.result import GraphResult

logger = logging.getLogger(__name__)


def _get_base_type(hint: Any) -> type:
    """Extract base type from Annotated or return hint as-is.

    For union types like `X | None`, returns the non-None type.
    """
    if get_origin(hint) is Annotated:
        hint = get_args(hint)[0]

    # Handle union types (X | None) - extract the non-None type
    if isinstance(hint, types.UnionType):
        args = get_args(hint)
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            return non_none_types[0]
        # Multiple non-None types - return first one (edge case)
        if non_none_types:
            return non_none_types[0]

    return hint


def _build_context(node: Node) -> dict[str, object]:
    """Build context dict from node fields for LM fill."""
    return {
        name: getattr(node, name)
        for name in node.__class__.model_fields
        if hasattr(node, name)
    }


def _build_instruction(target_type: type) -> str:
    """Build instruction string from class name + optional docstring."""
    instruction = target_type.__name__
    if target_type.__doc__:
        instruction += f": {target_type.__doc__.strip()}"
    return instruction


def _get_routing_strategy(
    node_cls: type[Node],
) -> tuple[str, ...] | tuple[str, type] | tuple[str, list[type]]:
    """Determine the routing strategy for a node class.

    Returns:
        - ("custom",) - node has custom __call__ logic
        - ("terminal",) - node has ellipsis body with pure None return
        - ("make", target_type) - node has ellipsis body with single return type
        - ("decide", types_list) - node has ellipsis body with union or optional return
    """
    # Check if node has custom logic (non-ellipsis body)
    if not _has_ellipsis_body(node_cls.__call__):
        return ("custom",)

    # Get return type hints
    hints = get_type_hints(node_cls.__call__)
    return_hint = hints.get("return")

    # Pure None return
    if return_hint is None or return_hint is type(None):
        return ("terminal",)

    # Handle union types (X | Y | None)
    if isinstance(return_hint, types.UnionType):
        args = get_args(return_hint)
        concrete_types = [arg for arg in args if arg is not type(None) and isinstance(arg, type)]
        is_optional = type(None) in args

        # No concrete types -> terminal
        if not concrete_types:
            return ("terminal",)

        # Single type, not optional -> make
        if len(concrete_types) == 1 and not is_optional:
            return ("make", concrete_types[0])

        # Multiple types or optional -> decide
        return ("decide", concrete_types)

    # Single type (not union)
    if isinstance(return_hint, type):
        return ("make", return_hint)

    return ("terminal",)


class Graph:
    """Agent graph built from Node type hints.

    Usage:
    ```python
    graph = Graph(start=AnalyzeRequest)

    # Run the graph with an LM backend
    lm = PydanticAIBackend()
    result = graph.run(AnalyzeRequest(request="Build a web scraper"), lm=lm)
    ```

    The graph topology is discovered by walking return type hints from the start node.
    """

    def __init__(self, start: type[Node]):
        """Initialize the graph.

        Args:
            start: The starting node type.
        """
        self.start = start
        self._nodes: dict[type[Node], set[type[Node]]] = {}
        self._discover()

    def _discover(self) -> None:
        """Discover all nodes reachable from start via type hints."""
        visited: set[type[Node]] = set()
        queue: deque[type[Node]] = deque([self.start])

        while queue:
            node_cls = queue.popleft()
            if node_cls in visited:
                continue
            visited.add(node_cls)

            successors = node_cls.successors()
            self._nodes[node_cls] = successors

            for successor in successors:
                if successor not in visited:
                    queue.append(successor)

    @property
    def nodes(self) -> set[type[Node]]:
        """All node types in the graph."""
        return set(self._nodes.keys())

    @property
    def edges(self) -> dict[type[Node], set[type[Node]]]:
        """Adjacency list: node type -> set of successor types."""
        return self._nodes.copy()

    @property
    def terminal_nodes(self) -> set[type[Node]]:
        """Node types that can terminate the graph."""
        return {n for n in self._nodes if n.is_terminal()}

    def validate(self) -> list[str]:
        """Validate graph structure. Returns list of warnings/errors."""
        issues = []

        # Check for nodes with no terminal path (would cause infinite loops)
        nodes_with_terminal_path = set()
        for node_cls in self._nodes:
            if node_cls.is_terminal():
                nodes_with_terminal_path.add(node_cls)

        # Propagate backwards: if a node can reach a terminal, it has a terminal path
        changed = True
        while changed:
            changed = False
            for node_cls, successors in self._nodes.items():
                if node_cls in nodes_with_terminal_path:
                    continue
                if any(s in nodes_with_terminal_path for s in successors):
                    nodes_with_terminal_path.add(node_cls)
                    changed = True

        for node_cls in self._nodes:
            if node_cls not in nodes_with_terminal_path:
                issues.append(
                    f"{node_cls.__name__} has no path to a terminal node "
                    f"(potential infinite loop)"
                )

        return issues

    def run(
        self,
        start_node: Node,
        lm: LM | None = None,
        max_iters: int = 10,
    ) -> GraphResult:
        """Execute the graph starting from the given node.

        Uses v2 execution loop:
        1. resolve_fields() resolves Dep and Recall fields on each node
        2. Resolved values set on self via object.__setattr__
        3. Routing via _get_routing_strategy:
           - Terminal: exit loop
           - Custom __call__: invoke directly (LM passed if _wants_lm)
           - Ellipsis body: route via lm.choose_type/fill (v2 LM API)

        Args:
            start_node: Initial node instance with fields populated.
            lm: Language model backend for producing nodes.
            max_iters: Maximum iterations (0 = infinite). Default 10.

        Returns:
            GraphResult with trace of visited nodes.

        Raises:
            BaeError: If max_iters exceeded.
            DepError: If a dependency function fails.
            RecallError: If recall finds no matching field in trace.
        """
        # Default to DSPyBackend if no LM provided
        if lm is None:
            from bae.dspy_backend import DSPyBackend

            lm = DSPyBackend()

        trace: list[Node] = []
        dep_cache: dict = {}
        current: Node | None = start_node
        iters = 0

        while current is not None:
            # Iteration guard
            if max_iters and iters >= max_iters:
                err = BaeError(f"Graph execution exceeded {max_iters} iterations")
                err.trace = trace
                raise err

            # 1. Resolve deps and recalls
            try:
                resolved = resolve_fields(current.__class__, trace, dep_cache)
            except RecallError:
                raise  # Already correct type
            except Exception as e:
                err = DepError(
                    f"{e} failed on {current.__class__.__name__}",
                    node_type=current.__class__,
                    cause=e,
                )
                err.trace = trace
                raise err from e

            # 2. Set resolved values on self
            for field_name, value in resolved.items():
                object.__setattr__(current, field_name, value)

            logger.debug(
                "Resolved %d fields on %s",
                len(resolved),
                current.__class__.__name__,
            )

            # 3. Append to trace (after resolution, before __call__)
            trace.append(current)

            # 4. Determine routing and execute
            strategy = _get_routing_strategy(current.__class__)

            if strategy[0] == "terminal":
                # Terminal node -- already in trace, exit
                current = None
            elif strategy[0] == "custom":
                # Custom __call__ logic
                if _wants_lm(current.__class__.__call__):
                    current = current(lm)
                else:
                    current = current()
            else:
                # Ellipsis body -- LM routing via v2 API
                if strategy[0] == "make":
                    target_type = strategy[1]
                elif strategy[0] == "decide":
                    types_list = list(strategy[1])
                    context = _build_context(current)
                    target_type = lm.choose_type(types_list, context)
                else:
                    current = None
                    iters += 1
                    continue

                # Resolve target's dep/recall fields before fill
                target_resolved = resolve_fields(target_type, trace, dep_cache)
                instruction = _build_instruction(target_type)
                current = lm.fill(
                    target_type, target_resolved, instruction, source=current
                )

            iters += 1

        return GraphResult(node=None, trace=trace)

    def to_mermaid(self) -> str:
        """Generate Mermaid diagram of the graph."""
        lines = ["graph TD"]

        for node_cls, successors in self._nodes.items():
            node_name = node_cls.__name__

            # Style terminal nodes differently
            if node_cls.is_terminal():
                if successors:
                    # Can be terminal but also has successors
                    lines.append(f"    {node_name}{{{{`{node_name}`}}}}")
                else:
                    # Pure terminal (no successors)
                    lines.append(f"    {node_name}(({node_name}))")

            for succ in successors:
                succ_name = succ.__name__
                lines.append(f"    {node_name} --> {succ_name}")

        return "\n".join(lines)
