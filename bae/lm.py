"""LLM abstraction layer.

Provides a clean interface over different LLM backends.
"""

from typing import Protocol, TypeVar

from bae.node import Node

T = TypeVar("T", bound=Node)


class LM(Protocol):
    """Protocol for language model backends.

    The LLM's job is to execute a node's __call__:
    - Input: current node (self) with its fields
    - Output: next node (return value of __call__)
    """

    async def execute(self, node: T) -> Node | None:
        """Execute a node's __call__ using the LLM.

        The LLM should:
        1. Look at the node's fields (current state)
        2. Look at the return type hint (what it can produce)
        3. Decide which successor to return and construct it

        Args:
            node: Current node instance with fields populated.

        Returns:
            Next node instance, or None if terminal.
        """
        ...


class PydanticAIBackend:
    """LLM backend using pydantic-ai."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    async def execute(self, node: T) -> Node | None:
        """Execute node using pydantic-ai."""
        # TODO: Use pydantic-ai Agent with:
        # - Input: node's fields as context
        # - Output type: union of node's successor types
        raise NotImplementedError("PydanticAI backend not yet implemented")


class ClaudeCLIBackend:
    """LLM backend using Claude CLI subprocess."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    async def execute(self, node: T) -> Node | None:
        """Execute node using Claude CLI."""
        # TODO: Shell out to claude CLI with:
        # - Prompt describing current node state
        # - Schema for possible return types
        # - Parse response into appropriate node type
        raise NotImplementedError("Claude CLI backend not yet implemented")
