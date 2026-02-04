"""LLM abstraction layer.

Provides a clean interface for LLM backends to produce typed node instances.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar, get_type_hints

if TYPE_CHECKING:
    from bae.node import Node

T = TypeVar("T", bound="Node")


class LM(Protocol):
    """Protocol for language model backends.

    The LM produces typed node instances based on:
    - Current node state (fields)
    - Target type(s) to produce
    """

    def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of a specific node type.

        Use when your logic has already decided which type to produce.

        Args:
            node: Current node (provides context via its fields).
            target: The node type to produce.

        Returns:
            Instance of target type with fields filled by LLM.
        """
        ...

    def decide(self, node: Node) -> Node | None:
        """Let LLM decide which successor to produce based on return type hint.

        Looks at the node's __call__ return type hint to determine
        valid successor types, then picks one and produces it.

        Args:
            node: Current node (provides context and return type hint).

        Returns:
            Instance of one of the valid successor types, or None if terminal.
        """
        ...


class PydanticAIBackend:
    """LLM backend using pydantic-ai."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self._agents: dict[type, object] = {}  # Cache agents per type

    def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of target type using pydantic-ai."""
        # TODO: Use pydantic-ai Agent with:
        # - system prompt from target's docstring
        # - input context from node's fields
        # - output_type = target
        raise NotImplementedError("PydanticAI backend not yet implemented")

    def decide(self, node: Node) -> Node | None:
        """Let LLM pick successor type and produce it."""
        # Get valid successor types from node's return hint
        successors = node.successors()
        is_terminal = node.is_terminal()

        if not successors and is_terminal:
            return None

        # TODO: Use pydantic-ai with union output type
        # output_type = successor1 | successor2 | ... (| None if terminal)
        raise NotImplementedError("PydanticAI backend not yet implemented")


class ClaudeCLIBackend:
    """LLM backend using Claude CLI subprocess."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of target type using Claude CLI."""
        # TODO: Shell out to claude CLI with:
        # - Prompt describing current node state
        # - Schema for target type
        # - Parse JSON response into target type
        raise NotImplementedError("Claude CLI backend not yet implemented")

    def decide(self, node: Node) -> Node | None:
        """Let LLM pick successor type and produce it."""
        # TODO: Shell out with union schema, parse response
        raise NotImplementedError("Claude CLI backend not yet implemented")
