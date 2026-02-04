"""Graph discovery and execution.

The Graph class discovers topology from Node type hints and handles execution.
"""

from collections import deque
from typing import Any
from incant import Incanter

from bae.node import Node


class Graph:
    """Agent graph built from Node type hints.

    Usage:
    ```python
    graph = Graph(start=AnalyzeRequest)

    # Run the graph
    result = await graph.run(AnalyzeRequest(request="Build a web scraper"))
    ```

    The graph topology is discovered by walking return type hints from the start node.
    """

    def __init__(
        self,
        start: type[Node],
        incanter: Incanter | None = None,
    ):
        """Initialize the graph.

        Args:
            start: The starting node type.
            incanter: Optional Incanter for dependency injection.
        """
        self.start = start
        self.incanter = incanter or Incanter()
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

        # Check for unreachable nodes (nodes that declare predecessors not in graph)
        for node_cls in self._nodes:
            preds = node_cls.predecessors()
            for pred in preds:
                if pred not in self._nodes and pred is not type(None):
                    issues.append(
                        f"{node_cls.__name__} expects predecessor {pred.__name__} "
                        f"which is not in the graph"
                    )

        # Check for nodes with no terminal path
        # (would cause infinite loops)
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

    async def run(
        self,
        start_node: Node,
        max_steps: int = 100,
        **deps: Any,
    ) -> Node | None:
        """Execute the graph starting from the given node.

        Args:
            start_node: Initial node instance with inputs populated.
            max_steps: Maximum execution steps (prevents infinite loops).
            **deps: Dependencies to register with incanter.

        Returns:
            The final node instance, or None if terminated.
        """
        # Register dependencies
        for name, value in deps.items():
            self.incanter.register_by_name(lambda v=value: v, name=name)

        current: Node | None = start_node
        prev: Node | None = None
        steps = 0

        while current is not None and steps < max_steps:
            # TODO: Here's where we'd invoke the LLM to fill output fields
            # For now, assume outputs are already filled (manual testing)

            # Execute node logic via incanter (injects deps into __call__)
            next_node = self.incanter.compose_and_call(
                current.__call__,
                prev=prev,
            )

            prev = current
            current = next_node
            steps += 1

        if steps >= max_steps:
            raise RuntimeError(f"Graph execution exceeded {max_steps} steps")

        return prev  # Return last executed node

    def to_mermaid(self) -> str:
        """Generate Mermaid diagram of the graph."""
        lines = ["graph TD"]

        for node_cls, successors in self._nodes.items():
            node_name = node_cls.__name__

            if not successors or node_cls.is_terminal():
                # Terminal node styling
                if node_cls.is_terminal() and successors:
                    # Can be terminal but also has successors
                    lines.append(f"    {node_name}[/{node_name}/]")
                elif not successors:
                    # Pure terminal
                    lines.append(f"    {node_name}[({node_name})]")

            for succ in successors:
                succ_name = succ.__name__
                lines.append(f"    {node_name} --> {succ_name}")

        return "\n".join(lines)
