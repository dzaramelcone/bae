"""Execution result types for bae graphs."""

from dataclasses import dataclass

from bae.node import Node


@dataclass
class GraphResult:
    """Result of executing a graph.

    Attributes:
        node: The final node after execution, or None if terminated normally.
        trace: Flat list of nodes in execution order.
    """

    node: Node | None
    trace: list[Node]
