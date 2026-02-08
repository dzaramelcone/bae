"""Node base class for graph nodes.

Nodes are Pydantic models that:
- Hold state as fields
- Implement __call__ to decide routing and produce next node
- Declare graph topology via return type hints on __call__

Requires Python 3.14+ for PEP 649 (deferred annotation evaluation).
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import types
from typing import TYPE_CHECKING, ClassVar, TypedDict, get_type_hints, get_args
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from bae.lm import LM


def _has_ellipsis_body(method) -> bool:
    """Check if a method body consists only of `...` (Ellipsis).

    This signals "use automatic routing" vs custom logic.

    Args:
        method: A method (function) to inspect.

    Returns:
        True if body is just `...`, False otherwise.
    """
    try:
        source = inspect.getsource(method)
        source = textwrap.dedent(source)
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError, IndentationError):
        return False

    # Find the function definition
    func_def = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_def = node
            break

    if func_def is None:
        return False

    # Check if body is just `...` (with optional docstring)
    # Body can be: [Ellipsis] or [docstring, Ellipsis]
    body = func_def.body

    # Skip leading docstring if present
    start_idx = 0
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        start_idx = 1

    # After docstring, should be exactly one statement: Ellipsis
    remaining = body[start_idx:]
    if len(remaining) != 1:
        return False

    stmt = remaining[0]
    if not isinstance(stmt, ast.Expr):
        return False

    # Check for Ellipsis constant
    if isinstance(stmt.value, ast.Constant) and stmt.value.value is ...:
        return True

    return False


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


def _wants_lm(method) -> bool:
    """Check if a method declares an 'lm' parameter (besides self).

    Used to detect whether a node's __call__ opts in to LM injection.

    Args:
        method: A method (function) to inspect.

    Returns:
        True if the method has a parameter named 'lm', False otherwise.
    """
    sig = inspect.signature(method)
    return "lm" in sig.parameters


class NodeConfig(TypedDict, total=False):
    """Per-node configuration for bae-specific settings.

    Standalone TypedDict -- NOT extending Pydantic's ConfigDict.
    Pydantic config lives in model_config; node behavior config lives here.
    """

    lm: LM
    """LM instance pinned to this node class (overrides graph-level LM)."""


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

    model_config = ConfigDict(arbitrary_types_allowed=True)
    node_config: ClassVar[NodeConfig] = NodeConfig()

    def __call__(self, lm: LM, *_args: object, **_kwargs: object) -> Node | None:
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
