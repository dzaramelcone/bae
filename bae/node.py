"""Node base class for graph nodes.

Nodes are Pydantic models that:
- Define input/output fields (fields with defaults = outputs, without = inputs)
- Implement __call__ to execute logic and return next node
- Declare graph topology via type hints on __call__
"""

import sys
import types
from typing import Any, ClassVar, get_type_hints, get_origin, get_args, Union
from pydantic import BaseModel, ConfigDict


def _is_union(hint) -> bool:
    """Check if a type hint is a Union (typing.Union or types.UnionType)."""
    origin = get_origin(hint)
    # Python 3.10+ uses types.UnionType for X | Y syntax
    # typing.Union is used for Union[X, Y] syntax
    return origin is Union or origin is types.UnionType or isinstance(hint, types.UnionType)


def _get_type_hints_with_module(func, cls: type) -> dict[str, Any]:
    """Get type hints, resolving forward refs against the class's module."""
    module = sys.modules.get(cls.__module__, None)
    globalns = getattr(module, "__dict__", {}) if module else {}
    # Include the class itself and its bases for self-references
    localns = {cls.__name__: cls}
    # Also include any classes defined in the same module
    for name, obj in globalns.items():
        if isinstance(obj, type):
            localns[name] = obj
    try:
        return get_type_hints(func, globalns=globalns, localns=localns)
    except NameError:
        # If we still can't resolve, return empty - caller handles gracefully
        return {}


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

        def __call__(self, prev: None) -> "GenerateCode | Clarify":
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

    def __call__(self, prev: "Node | None") -> "Node | None":
        """Execute node logic and return next node.

        Args:
            prev: The previous node instance (with its outputs populated),
                  or None if this is the start node.

        Returns:
            The next node instance (with inputs set), or None if terminal.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.__call__ not implemented")

    @classmethod
    def input_fields(cls) -> dict[str, Any]:
        """Get fields that are inputs (no default value)."""
        return {
            name: field
            for name, field in cls.model_fields.items()
            if field.is_required()
        }

    @classmethod
    def output_fields(cls) -> dict[str, Any]:
        """Get fields that are outputs (have default value)."""
        return {
            name: field
            for name, field in cls.model_fields.items()
            if not field.is_required()
        }

    @classmethod
    def predecessors(cls) -> set[type["Node"]]:
        """Get node types that can precede this node (from `prev` type hint)."""
        hints = _get_type_hints_with_module(cls.__call__, cls)
        prev_hint = hints.get("prev")

        if prev_hint is None:
            return set()

        # Handle None type
        if prev_hint is type(None):
            return set()

        # Handle Union types (e.g., NodeA | NodeB | None)
        if _is_union(prev_hint):
            args = get_args(prev_hint)
            return {arg for arg in args if arg is not type(None) and isinstance(arg, type)}

        # Single type
        if isinstance(prev_hint, type):
            return {prev_hint}

        return set()

    @classmethod
    def successors(cls) -> set[type["Node"]]:
        """Get node types that can follow this node (from return type hint)."""
        hints = _get_type_hints_with_module(cls.__call__, cls)
        return_hint = hints.get("return")

        if return_hint is None:
            return set()

        # Handle None type (terminal)
        if return_hint is type(None):
            return set()

        # Handle Union types (e.g., NodeA | NodeB | None)
        if _is_union(return_hint):
            args = get_args(return_hint)
            return {arg for arg in args if arg is not type(None) and isinstance(arg, type)}

        # Single type
        if isinstance(return_hint, type):
            return {return_hint}

        return set()

    @classmethod
    def is_terminal(cls) -> bool:
        """Check if this node type can be terminal (return None)."""
        hints = _get_type_hints_with_module(cls.__call__, cls)
        return_hint = hints.get("return")

        if return_hint is None or return_hint is type(None):
            return True

        if _is_union(return_hint):
            args = get_args(return_hint)
            return type(None) in args

        return False
