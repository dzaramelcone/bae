"""Graph discovery and execution.

The Graph class discovers topology from Node type hints and handles execution.
"""

import types
from collections import deque
from typing import Annotated, get_args, get_origin, get_type_hints

from bae.lm import LM
from bae.markers import Bind
from bae.node import Node, _has_ellipsis_body
from bae.result import GraphResult


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
    result = await graph.run(AnalyzeRequest(request="Build a web scraper"), lm=lm)
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

        # Check for duplicate Bind types across nodes
        issues.extend(self._validate_bind_uniqueness())

        return issues

    def _validate_bind_uniqueness(self) -> list[str]:
        """Check that each Bind type appears at most once in the graph."""
        issues = []

        # Collect all Bind types -> list of (node_cls, field_name)
        bind_types: dict[type, list[tuple[type[Node], str]]] = {}

        for node_cls in self._nodes:
            hints = get_type_hints(node_cls, include_extras=True)
            for field_name, hint in hints.items():
                if get_origin(hint) is Annotated:
                    args = get_args(hint)
                    base_type = args[0]
                    metadata = args[1:]

                    for meta in metadata:
                        if isinstance(meta, Bind):
                            if base_type not in bind_types:
                                bind_types[base_type] = []
                            bind_types[base_type].append((node_cls, field_name))
                            break

        # Report duplicates
        for bind_type, locations in bind_types.items():
            if len(locations) > 1:
                node_names = [f"{n.__name__}.{f}" for n, f in locations]
                issues.append(
                    f"Duplicate Bind for type {bind_type.__name__}: "
                    f"{', '.join(node_names)}"
                )

        return issues

    def run(
        self,
        start_node: Node,
        lm: LM,
        max_steps: int = 100,
    ) -> GraphResult:
        """Execute the graph starting from the given node.

        Uses auto-routing for nodes with ellipsis body:
        - Union return type -> lm.decide()
        - Single return type -> lm.make()
        - Pure None return -> return None immediately
        - Custom __call__ logic -> call directly (escape hatch)

        Args:
            start_node: Initial node instance with fields populated.
            lm: Language model backend for producing nodes.
            max_steps: Maximum execution steps (prevents infinite loops).

        Returns:
            GraphResult with final node and trace of visited nodes.

        Raises:
            RuntimeError: If max_steps exceeded.
        """
        trace: list[Node] = []
        current: Node | None = start_node
        steps = 0

        while current is not None and steps < max_steps:
            trace.append(current)

            # Determine routing strategy
            strategy = _get_routing_strategy(current.__class__)

            if strategy[0] == "terminal":
                # Ellipsis body with pure None return
                current = None
            elif strategy[0] == "make":
                # Ellipsis body with single return type
                target_type = strategy[1]
                current = lm.make(current, target_type)
            elif strategy[0] == "decide":
                # Ellipsis body with union/optional return type
                current = lm.decide(current)
            else:
                # Custom logic - call directly
                current = current(lm=lm)

            steps += 1

        if steps >= max_steps:
            raise RuntimeError(f"Graph execution exceeded {max_steps} steps")

        return GraphResult(node=current, trace=trace)

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
