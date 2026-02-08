"""Execution result types for bae graphs."""

from dataclasses import dataclass
from typing import Generic, TypeVar

from bae.node import Node

T = TypeVar("T", bound=Node, default=Node)


@dataclass
class GraphResult(Generic[T]):
    """Result of executing a graph.

    Generic over T, the expected terminal node type. When used as
    GraphResult[MyNode], the .result property is typed as MyNode | None,
    giving callers type-safe access to the graph's response.

    Attributes:
        node: The current node after execution, or None if terminated normally.
        trace: Flat list of all nodes in execution order (start + intermediate + terminal).
        result: The terminal node (last in trace). This IS the graph's response.
    """

    node: Node | None
    trace: list[Node]

    @property
    def result(self) -> T | None:
        """The terminal node (graph's response). Last node in trace."""
        return self.trace[-1] if self.trace else None
