"""Graph discovery and execution.

The Graph class discovers topology from Node type hints and handles execution.
"""

from collections import deque

from bae.node import Node
from bae.lm import LM


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

        return issues

    def run(
        self,
        start_node: Node,
        lm: LM,
        max_steps: int = 100,
    ) -> Node | None:
        """Execute the graph starting from the given node.

        Args:
            start_node: Initial node instance with fields populated.
            lm: Language model backend for producing nodes.
            max_steps: Maximum execution steps (prevents infinite loops).

        Returns:
            None if terminated normally, or raises if max_steps exceeded.
        """
        current: Node | None = start_node
        steps = 0

        while current is not None and steps < max_steps:
            # Call node's __call__ with injected LM
            next_node = current(lm=lm)
            current = next_node
            steps += 1

        if steps >= max_steps:
            raise RuntimeError(f"Graph execution exceeded {max_steps} steps")

        return current

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
