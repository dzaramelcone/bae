"""Graph discovery and execution.

The Graph class discovers topology from Node type hints and handles execution.
"""

import inspect
import types
from collections import deque
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from incant import Incanter

from bae.exceptions import BaeError
from bae.lm import LM
from bae.markers import Bind, Dep
from bae.node import Node, _has_ellipsis_body
from bae.result import GraphResult


def _is_dep_annotated(param: inspect.Parameter) -> bool:
    """Check if a parameter has a Dep annotation."""
    hint = param.annotation
    if get_origin(hint) is Annotated:
        args = get_args(hint)
        for arg in args[1:]:
            if isinstance(arg, Dep):
                return True
    return False


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


def _create_dep_hook_factory(dep_registry: dict[type, Any]):
    """Create a hook factory that looks up deps by base type."""

    def dep_hook_factory(param: inspect.Parameter):
        base_type = _get_base_type(param.annotation)
        if base_type not in dep_registry:
            raise TypeError(f"Missing dependency: {base_type.__name__}")

        def factory():
            return dep_registry[base_type]

        return factory

    return dep_hook_factory


def _capture_bind_fields(node: Node, dep_registry: dict[type, Any]) -> None:
    """Capture Bind-annotated fields from a node into the dep registry."""
    hints = get_type_hints(node.__class__, include_extras=True)
    for field_name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            metadata = args[1:]

            for meta in metadata:
                if isinstance(meta, Bind):
                    # Get the field value from the node
                    value = getattr(node, field_name, None)
                    if value is not None:
                        # Extract the non-None base type for registration
                        base_type = _get_base_type(hint)
                        dep_registry[base_type] = value
                    break


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
        **kwargs: Any,
    ) -> GraphResult:
        """Execute the graph starting from the given node.

        Uses auto-routing for nodes with ellipsis body:
        - Union return type -> lm.decide()
        - Single return type -> lm.make()
        - Pure None return -> return None immediately
        - Custom __call__ logic -> call directly (escape hatch)

        External dependencies can be passed as kwargs and will be injected
        into node __call__ methods via Dep-annotated parameters.

        Args:
            start_node: Initial node instance with fields populated.
            lm: Language model backend for producing nodes.
            max_steps: Maximum execution steps (prevents infinite loops).
            **kwargs: External dependencies to inject (matched by type).

        Returns:
            GraphResult with final node and trace of visited nodes.

        Raises:
            RuntimeError: If max_steps exceeded.
            BaeError: If a required dependency is missing.
        """
        trace: list[Node] = []
        current: Node | None = start_node
        steps = 0

        # Initialize dependency registry with external deps
        dep_registry: dict[type, Any] = {}
        for value in kwargs.values():
            dep_registry[type(value)] = value

        # Create incanter for this run with dep injection hook
        incanter = Incanter()
        incanter.register_hook_factory(_is_dep_annotated, _create_dep_hook_factory(dep_registry))

        while current is not None and steps < max_steps:
            trace.append(current)

            # Determine routing strategy
            strategy = _get_routing_strategy(current.__class__)

            try:
                if strategy[0] == "terminal":
                    # Ellipsis body with pure None return
                    next_node = None
                elif strategy[0] == "make":
                    # Ellipsis body with single return type
                    target_type = strategy[1]
                    next_node = lm.make(current, target_type)
                elif strategy[0] == "decide":
                    # Ellipsis body with union/optional return type
                    next_node = lm.decide(current)
                else:
                    # Custom logic - call with incant injection
                    next_node = incanter.compose_and_call(
                        current.__call__, lm=lm
                    )
            except TypeError as e:
                if "Missing dependency" in str(e):
                    raise BaeError(str(e), cause=e) from e
                raise

            # Capture Bind fields after node execution
            _capture_bind_fields(current, dep_registry)

            current = next_node
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
