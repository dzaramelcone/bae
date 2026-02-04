"""Node base class for graph nodes.

Nodes are Pydantic models that:
- Define input/output fields (fields with defaults = outputs, without = inputs)
- Implement __call__ to execute logic and return next node
- Declare graph topology via type hints on __call__

Requires Python 3.14+ for PEP 649 (deferred annotation evaluation).
"""

import types
from typing import ClassVar, get_type_hints, get_args
from pydantic import BaseModel, ConfigDict


def _extract_types_from_hint(hint) -> set[type]:
    """Extract concrete types from a type hint, excluding None."""
    if hint is None or hint is type(None):
        return set()

    # X | Y union syntax (types.UnionType)
    if isinstance(hint, types.UnionType):
        return {arg for arg in get_args(hint) if arg is not type(None) and isinstance(arg, type)}

    # Single type
    if isinstance(hint, type):
        return {hint}

    return set()


def _hint_includes_none(hint) -> bool:
    """Check if a type hint includes None (i.e., is optional/terminal)."""
    if hint is None or hint is type(None):
        return True

    if isinstance(hint, types.UnionType):
        return type(None) in get_args(hint)

    return False


class NodeConfig(ConfigDict, total=False):
    """Per-node configuration.

    Extends Pydantic's ConfigDict with node-specific settings.
    """

    model: str
    """LLM model to use for this node (e.g., 'sonnet', 'opus', 'haiku')."""

    temperature: float
    """Temperature for LLM generation."""


class Node(BaseModel):
    """Base class for graph nodes.

    Subclass this to define nodes in your agent graph:

    ```python
    class AnalyzeRequest(Node):
        # Inputs (no default = must be provided)
        request: str

        # Outputs (default = LLM fills these)
        intent: str = ""
        entities: list[str] = []

        def __call__(self, prev: None) -> GenerateCode | Clarify:
            if self.intent == "unclear":
                return Clarify(question="What did you mean?")
            return GenerateCode(task=self.intent)
    ```

    Graph topology is derived from type hints:
    - `prev` parameter type = incoming edges (in-degree)
    - Return type = outgoing edges (out-degree)
    - Return `None` = terminal node
    """

    model_config: ClassVar[NodeConfig] = NodeConfig()

    def __call__(self, prev: Node | None) -> Node | None:
        """Execute node logic and return next node.

        Args:
            prev: The previous node instance (with its outputs populated),
                  or None if this is the start node.

        Returns:
            The next node instance (with inputs set), or None if terminal.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.__call__ not implemented")

    @classmethod
    def predecessors(cls) -> set[type[Node]]:
        """Get node types that can precede this node (from `prev` type hint)."""
        hints = get_type_hints(cls.__call__)
        return _extract_types_from_hint(hints.get("prev"))

    @classmethod
    def successors(cls) -> set[type[Node]]:
        """Get node types that can follow this node (from return type hint)."""
        hints = get_type_hints(cls.__call__)
        return _extract_types_from_hint(hints.get("return"))

    @classmethod
    def is_terminal(cls) -> bool:
        """Check if this node type can be terminal (return None)."""
        hints = get_type_hints(cls.__call__)
        return _hint_includes_none(hints.get("return"))
