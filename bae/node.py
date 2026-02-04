"""Node base class for graph nodes.

Nodes are Pydantic models that:
- Hold state as fields
- Implement __call__ to decide routing and produce next node
- Declare graph topology via return type hints on __call__

Requires Python 3.14+ for PEP 649 (deferred annotation evaluation).
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING, ClassVar, get_type_hints, get_args
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from bae.lm import LM


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
        request: str

        def __call__(self, lm: LM) -> GenerateCode | Clarify:
            # Let LLM decide which path and construct it
            return lm.decide(GenerateCode | Clarify)

    class GenerateCode(Node):
        task: str
        code: str = ""

        def __call__(self, lm: LM) -> Review | None:
            # User logic picks the type, LLM constructs it
            if self.needs_review():
                return lm.make(Review)
            return None
    ```

    Graph topology is derived from return type hints:
    - Return type = outgoing edges (out-degree)
    - Return `None` = terminal node
    """

    model_config: ClassVar[NodeConfig] = NodeConfig()

    def __call__(self, lm: LM) -> Node | None:
        """Execute node logic and return next node.

        Override this to implement custom routing logic.
        Default behavior: let LLM decide based on return type hint.

        Args:
            lm: Language model for producing next node.

        Returns:
            The next node instance, or None if terminal.
        """
        # Default: LLM decides which successor to produce
        return lm.decide(self)

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
